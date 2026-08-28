#!/usr/bin/env python3
"""sondear_tessera.py — las suposiciones de TESSERA-KV, medidas en vez de discutidas.

QUÉ SE MIDE Y POR QUÉ
---------------------
TESSERA-KV cifra un 95 % de ahorro en Keys suponiendo que `K(t)` es **suave** en el índice
de token: 4-6 coeficientes de Chebyshev por bloque de 128. Toda la cifra depende de esa
suposición, así que se mide sobre K REALES de una capa de atención de verdad.

EL CONTROL, que es lo que hace legible el número (lección de C16): el mismo ajuste sobre
la misma secuencia con los tokens **barajados**. Barajar destruye la suavidad temporal y
deja intacta la estadística de los vectores. Si el error real se parece al barajado, K no
es suave y el ahorro no existe. Se añade un tercer punto de referencia: la **media del
bloque** (grado 0), que es el ajuste más tonto posible.

También se mide, sobre los mismos K, la pieza que sí parece sólida: **ancla + residuo
ternario** aprovechando la invarianza por traslación del softmax.
"""
from __future__ import annotations
import builtins as _b
_p = _b.print
print = lambda *a, **k: _p(*a, **{**k, "flush": True})

import argparse, json, os, sys, time
from pathlib import Path
import numpy as np
import torch

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ / "scripts"))
GRANDE = Path(os.environ.get("MG_BF16", "/home/forge/modelos/qwen3.8-27b"))
from medir_aceptacion import _corpus, _ventanas, _deposito                # noqa: E402
from recuperar_escalas import matriz                                      # noqa: E402


def cheby(Y, grado):
    """Ajuste por mínimos cuadrados de Chebyshev sobre el eje del token.
    Y: [L, d]. Devuelve el error relativo de reconstrucción."""
    L = Y.shape[0]
    t = np.linspace(-1, 1, L)
    B = np.polynomial.chebyshev.chebvander(t, grado)      # [L, grado+1]
    C, *_ = np.linalg.lstsq(B, Y, rcond=None)
    R = B @ C
    return float(np.linalg.norm(R - Y) / np.linalg.norm(Y))


@torch.no_grad()
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capa", type=int, default=3, help="primera de atención completa")
    ap.add_argument("--bloque", type=int, default=128)
    ap.add_argument("--grado", type=int, default=5)
    ap.add_argument("--ventana", type=int, default=512)
    ap.add_argument("--salida", default="")
    a = ap.parse_args()
    torch.set_num_threads(os.cpu_count() or 8)
    t0 = time.time()

    # 1 · el flujo residual hasta la capa de atención elegida
    from transformers import AutoConfig, AutoModelForCausalLM
    from transformers.masking_utils import create_causal_mask
    try:
        from transformers.masking_utils import create_recurrent_attention_mask
    except ImportError:
        create_recurrent_attention_mask = lambda **kw: None
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(GRANDE))
    ids, _ = _ventanas(_corpus(RAIZ), tok, a.ventana, 1)
    dep = _deposito(GRANDE); base = dep.prefijo_base()
    cfg = AutoConfig.from_pretrained(str(GRANDE))
    with torch.device("meta"):
        modelo = AutoModelForCausalLM.from_config(cfg)
    ct = getattr(cfg, "text_config", cfg)
    emb = dep.tensores(base + "embed_tokens.", dtype=torch.bfloat16)["weight"]
    x = emb[ids[:1]].clone(); del emb
    rot = type(modelo.model.rotary_emb)(ct, device="cpu")
    pos = torch.arange(a.ventana)[None]
    for i in range(a.capa):
        capa = modelo.model.layers[i]
        capa.load_state_dict(dep.capa(i, device="cpu", dtype=torch.bfloat16),
                             strict=True, assign=True)
        kw = dict(config=ct, inputs_embeds=x, attention_mask=None,
                  past_key_values=None, position_ids=pos)
        m = (create_causal_mask(**kw) if ct.layer_types[i] == "full_attention"
             else create_recurrent_attention_mask(**kw))
        s = capa(x, position_embeddings=rot(x, pos[None].expand(3, 1, -1)),
                 attention_mask=m, position_ids=pos)
        x = s[0] if isinstance(s, tuple) else s
        capa.to("meta")
    print(f"flujo residual hasta la capa {a.capa} · {time.time()-t0:.0f}s")

    # 2 · las Keys de esa capa: K = norm(x) @ W_k^T
    pesos = dep.capa(a.capa, device="cpu", dtype=torch.bfloat16)
    nk = [k for k in pesos if k.endswith("k_proj.weight")]
    if not nk:
        nk = [k for k in pesos if "k_proj" in k and k.endswith("weight")]
    if not nk:
        raise SystemExit(f"no encuentro k_proj en la capa {a.capa}: {sorted(pesos)[:12]}")
    Wk = pesos[nk[0]].float()
    xf = x[0].detach().float()
    xf = xf / xf.pow(2).mean(-1, keepdim=True).add(1e-6).sqrt()   # RMSNorm sin el peso
    K = (xf @ Wk.T).detach().numpy()
    print(f"K real: {K.shape} de {nk[0]}")

    # 3 · el ajuste, con sus dos controles
    rng = np.random.default_rng(7)
    res = {"capa": a.capa, "bloque": a.bloque, "grado": a.grado, "forma_K": list(K.shape),
           "bloques": [], }
    reales, barajados, medias = [], [], []
    for b0 in range(0, K.shape[0] - a.bloque + 1, a.bloque):
        Y = K[b0:b0 + a.bloque]
        e_real = cheby(Y, a.grado)
        e_baraj = cheby(Y[rng.permutation(a.bloque)], a.grado)
        e_media = float(np.linalg.norm(Y - Y.mean(0)) / np.linalg.norm(Y))
        reales.append(e_real); barajados.append(e_baraj); medias.append(e_media)
        res["bloques"].append({"desde": b0, "real": round(e_real, 4),
                               "barajado": round(e_baraj, 4), "media": round(e_media, 4)})
    r, s, m = np.mean(reales), np.mean(barajados), np.mean(medias)
    res.update({"err_real": round(float(r), 4), "err_barajado": round(float(s), 4),
                "err_media_bloque": round(float(m), 4),
                "razon_cheby_vs_barajado": round(float(r / s), 4)})
    print(f"\nChebyshev grado {a.grado} sobre bloques de {a.bloque}:")
    print(f"  error real      {r:.4f}")
    print(f"  error BARAJADO  {s:.4f}   <- el control: destruye el orden temporal")
    print(f"  media del bloque{m:.4f}   <- el ajuste más tonto posible (grado 0)")

    # 4 · la otra pieza: ancla + residuo ternario
    anc = K.mean(0, keepdims=True)
    D = K - anc
    esc = np.abs(D).mean() * 1.5
    Dq = np.clip(np.round(D / max(esc, 1e-9)), -1, 1) * esc
    err_tern = float(np.linalg.norm(anc + Dq - K) / np.linalg.norm(K))
    err_sin = float(np.linalg.norm(np.clip(np.round(K / max(np.abs(K).mean()*1.5, 1e-9)), -1, 1)
                                   * np.abs(K).mean()*1.5 - K) / np.linalg.norm(K))
    res.update({"err_ancla_ternario": round(err_tern, 4),
                "err_ternario_sin_ancla": round(err_sin, 4)})
    print(f"\nAncla + ternario: err {err_tern:.4f}   (ternario SIN ancla: {err_sin:.4f})")

    res["segundos"] = round(time.time() - t0, 1)
    print(f"\nCIFRA razon_cheby_vs_barajado {res['razon_cheby_vs_barajado']}")
    print(f"CIFRA err_cheby_real {res['err_real']}")
    print(f"CIFRA err_ancla_ternario {res['err_ancla_ternario']}")
    d = Path(a.salida) if a.salida else RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_tessera.json"
    d.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"registro: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
