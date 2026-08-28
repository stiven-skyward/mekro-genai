"""motor.py — generación autoregresiva capa a capa desde disco. Esto es H2.

QUÉ RESUELVE
------------
`quant/perplejidad.py` de QuantModels evalúa en *teacher forcing*: mete todas las ventanas
por cada capa y suma NLL. Generar es lo contrario —cada token depende del anterior— y
además necesita **estado entre pasos**: caché KV en las 16 capas de atención y estado
recurrente en las 48 GatedDeltaNet. Ese código no existía en ninguno de los dos proyectos.

EL DISEÑO
---------
El modelo (52 GB) no cabe en los ~20 GB de RAM de esta máquina, así que **los pesos se
traen capa a capa y se sueltan**; lo que persiste entre pasos no son los pesos sino la
caché, que es pequeña. Un token = un pase completo por el disco.

Y de ahí sale la única cifra que importa: **s/token = bytes_del_modelo / ancho_de_banda**.
Por eso el checkpoint tiene que estar en ext4 y no en `/mnt/e` (0,20 GB/s frente a 6,77
medidos: ×33). Ver docs/densa-en-cpu.md.

Lo que se reutiliza de QuantModels es `DepositoPesos` —que ya sabe abrir estos safetensors
en modo perezoso y deducir el prefijo de las capas sin suponerlo— y tres lecciones caras
que costaron NLL desviada allí y que aquí se respetan al pie de la letra:

1. **El rotary se instancia de verdad.** En `meta` sus búferes son basura.
2. **Las posiciones de Qwen3.5 son mrope**: `[4, B, T]` — la 0 es la textual y las tres
   siguientes van al rotary. Con posiciones 2D los cos/sin salen distintos.
3. **Se usan los MÓDULOS del esqueleto, no aritmética a mano.** La RMSNorm de Qwen3.5 es
   *zero-centered* (multiplica por `1 + weight`); reimplementarla «estándar» produce
   logits uniformes.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch

QUANTMODELS = Path(os.environ.get("MG_QUANTMODELS", "/mnt/e/QuantModels"))


@dataclass
class Traza:
    """Lo que costó cada token. Sin esto no hay cifra que enseñar."""
    segundos: list[float] = field(default_factory=list)
    prefill_seg: float = 0.0
    tokens_prompt: int = 0

    @property
    def seg_por_token(self) -> float:
        return sum(self.segundos) / len(self.segundos) if self.segundos else 0.0


class MotorDenso:
    """El modelo BF16 completo, servido capa a capa desde disco, en CPU."""

    def __init__(self, ruta: str | Path, hilos: int = 0, verboso: bool = True):
        self.ruta = Path(ruta)
        self.verboso = verboso
        torch.set_num_threads(hilos or os.cpu_count() or 8)
        if str(QUANTMODELS) not in sys.path:
            sys.path.insert(0, str(QUANTMODELS))

        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        from quant.carga import DepositoPesos                      # type: ignore

        self.dep = DepositoPesos(self.ruta)
        self.base = self.dep.prefijo_base()
        self.tok = AutoTokenizer.from_pretrained(str(self.ruta))
        cfg = AutoConfig.from_pretrained(str(self.ruta))
        with torch.device("meta"):
            self.modelo = AutoModelForCausalLM.from_config(cfg)
        self.tm = self.modelo.model
        self.cfg = self.tm.config
        self.n_capas = self.cfg.num_hidden_layers

        # El rotary, REAL: en meta sus búferes son basura y los cos/sin salen ruido.
        self.rotary = type(self.tm.rotary_emb)(self.cfg)

        # Embed, norma final y lm_head se quedan residentes: hacen falta en CADA token y
        # son ~5 GB de los 52. Recargarlos por token sería pagar dos veces por lo mismo.
        self._decir("cargando embed + norma + lm_head (residentes)…")
        t0 = time.time()
        self.embed = self.dep.tensores(self.base + "embed_tokens.")["weight"]
        self.tm.norm.load_state_dict(
            self.dep.tensores(self.base + "norm."), strict=True, assign=True)
        self.modelo.lm_head.load_state_dict(
            self.dep.tensores("lm_head."), strict=True, assign=True)
        self._decir(f"  {time.time() - t0:.1f} s")

    def _decir(self, msg: str) -> None:
        if self.verboso:
            print(msg, flush=True)

    # ── un pase completo por las 64 capas ───────────────────────────────────
    def _pase(self, x: torch.Tensor, cache, desde: int) -> torch.Tensor:
        from transformers.masking_utils import create_causal_mask, create_recurrent_attention_mask

        B, T, _ = x.shape
        pos_txt = torch.arange(desde, desde + T).view(1, -1).expand(B, -1)
        # [4, B, T]: la fila 0 es la textual; las tres siguientes son las de mrope.
        pos4 = pos_txt.unsqueeze(0).expand(4, B, T)
        cos_sin = self.rotary(x, pos4[1:])

        kw = dict(config=self.cfg, inputs_embeds=x, attention_mask=None,
                  past_key_values=cache, position_ids=pos_txt)
        mascaras = {"full_attention": create_causal_mask(**kw),
                    "linear_attention": create_recurrent_attention_mask(**kw)}

        for i in range(self.n_capas):
            capa = self.tm.layers[i]
            capa.load_state_dict(self.dep.capa(i), strict=True, assign=True)
            x = capa(x, position_embeddings=cos_sin,
                     attention_mask=mascaras[self.cfg.layer_types[i]],
                     position_ids=pos_txt, past_key_values=cache)
            if isinstance(x, tuple):
                x = x[0]
            capa.to("meta")            # suelta los ~730 MB de esta capa
        return x

    def _logits(self, x: torch.Tensor) -> torch.Tensor:
        return self.modelo.lm_head(self.tm.norm(x[:, -1:]))[:, -1].float()

    # ── la API ──────────────────────────────────────────────────────────────
    @torch.no_grad()
    def generar(self, prompt: str, max_tokens: int = 32, temperatura: float = 0.0,
                al_token=None) -> tuple[str, Traza]:
        from transformers import DynamicCache

        ids = self.tok(prompt, return_tensors="pt")["input_ids"]
        traza = Traza(tokens_prompt=int(ids.shape[1]))
        cache = DynamicCache(config=self.cfg)

        t0 = time.time()
        x = self._pase(self.embed[ids], cache, 0)
        traza.prefill_seg = time.time() - t0
        self._decir(f"prefill: {traza.tokens_prompt} tokens en {traza.prefill_seg:.1f} s")

        salida: list[int] = []
        for paso in range(max_tokens):
            logits = self._logits(x)
            if temperatura > 0:
                sig = int(torch.multinomial(
                    torch.softmax(logits / temperatura, -1), 1).item())
            else:
                sig = int(logits.argmax(-1).item())
            if sig in (self.tok.eos_token_id, getattr(self.tok, "pad_token_id", None)):
                break
            salida.append(sig)
            if al_token:
                al_token(self.tok.decode([sig]), paso, traza)

            t0 = time.time()
            x = self._pase(self.embed[torch.tensor([[sig]])], cache,
                           traza.tokens_prompt + len(salida) - 1)
            traza.segundos.append(time.time() - t0)

        return self.tok.decode(salida), traza
