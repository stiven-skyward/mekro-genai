#!/usr/bin/env python3
"""medir_aceptacion.py — C4: cuántos tokens se aceptan de verdad.

QUÉ MIDE Y POR QUÉ NO HACE FALTA H8 PARA MEDIRLO
------------------------------------------------
La tabla de `docs/densa-en-cpu.md` proyecta 0,71 / 1,43 / 2,86 tok/s según se acepten
4 / 8 / 16 tokens por pase del modelo grande. Las tres primeras filas están medidas
(9p→ext4 ×33, lote 8 a 0,879×, compresión ×1,4627); **el divisor no**. Este script lo
mide, y lo hace SIN escribir la decodificación especulativa (H8), que es cara y todavía
está bloqueada por H2.

El truco es que la tasa de aceptación no depende del bucle: depende solo de cuánto se
parecen las dos distribuciones en cada posición. Con *teacher forcing* sobre texto real
—exactamente lo que ya sabe hacer `quant/perplejidad.py`— se obtienen las dos
distribuciones en las mismas posiciones con **dos pases por disco**, uno por modelo, en
vez de un pase por token.

  · greedy (temperatura 0, que es como genera el arnés): se acepta la propuesta si
    argmax(q) == argmax(p). El acuerdo se mide token a token, exacto.
  · temperatura 1: la probabilidad de aceptar del muestreo especulativo es
    Σ_x min(p(x), q(x)) = 1 − TV(p, q). También exacto, sin muestrear nada.

Y los tokens por pase NO se estiman con la fórmula i.i.d. (1−α^(γ+1))/(1−α), que supone
que las aceptaciones son independientes. En código no lo son: llegan a ráfagas (cierres
de bloque, sangrado, nombres ya vistos). Se **simula el bucle** sobre la secuencia real
de aciertos, que es lo que de verdad va a pasar.

LO QUE ESTE MÉTODO NO MIDE, Y HAY QUE DECIRLO
---------------------------------------------
En la especulativa de verdad el borrador propone condicionado al prefijo **generado por
el modelo**, no al del corpus. Aquí ambos modelos ven el mismo prefijo humano. Es el
estimador estándar de la literatura y es el que se puede pagar hoy, pero es un proxy:
la cifra real puede desviarse. Queda escrito en la lección del ciclo.

USO
---
  python3 scripts/medir_aceptacion.py --ventana 512 --ventanas 8 --gamma 8
  python3 scripts/medir_aceptacion.py --ventana 128 --ventanas 1 --capas 4   # sonda
"""
from __future__ import annotations

# Las carreras van desatendidas con nohup: si la salida se bufferiza, el monitor que la
# vigila queda CIEGO y una carrera de media hora no emite una sola línea. Lección del
# 2026-08-23, con C16 corriendo 27 min sin señal. Se fuerza el vaciado en cada print.
import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
QUANTMODELS = Path(os.environ.get("MG_QUANTMODELS", "/mnt/e/QuantModels"))
GRANDE = Path(os.environ.get("MG_BF16", "/home/forge/modelos/qwen3.8-27b"))
BORRADOR = Path(os.environ.get("MG_CAMPEON_EXT4", "/home/forge/modelos/qwen38-h13b"))


def _deposito(ruta: Path):
    if str(QUANTMODELS) not in sys.path:
        sys.path.insert(0, str(QUANTMODELS))
    from quant.carga import DepositoPesos          # type: ignore
    return DepositoPesos(ruta)


# ── el corpus: el dominio de trabajo real, no wikitext ──────────────────────
# H8 deja escrito el aviso: un borrador que acierta el 80 % en prosa puede acertar el
# 40 % en código, y el número que importa es el segundo. Así que el corpus es el propio
# repositorio: su código Python y su prosa española.
def _corpus(raiz: Path) -> dict[str, str]:
    # EL CORPUS ES EL PROPIO REPOSITORIO, Y EL REPOSITORIO CAMBIA MIENTRAS SE MIDE.
    # El 2026-08-23 el BF16 dio PPL 5,764 por la mañana y el GGUF 4,7124 por la tarde
    # sobre «el mismo» corpus — pero entre medias se habían añadido siete scripts, así
    # que la comparación no valía nada. Desde entonces se lee la copia CONGELADA si
    # existe, y su huella va en cada registro. Para volver a congelarlo hay que borrarla
    # a mano, que es justo la fricción que debe tener.
    congelado = raiz / "registros" / "corpus-congelado.json"
    if congelado.exists():
        return json.loads(congelado.read_text(encoding="utf-8"))["grupos"]
    codigo, espanol = [], []
    for p in sorted(raiz.glob("genai/**/*.py")) + sorted(raiz.glob("scripts/*.py")):
        codigo.append(p.read_text(encoding="utf-8", errors="ignore"))
    for p in sorted(raiz.glob("docs/*.md")) + [raiz / "CLAUDE.md", raiz / "META.md",
                                               raiz / "CONTINUIDAD.md"]:
        if p.exists():
            espanol.append(p.read_text(encoding="utf-8", errors="ignore"))
    return {"codigo": "\n\n".join(codigo), "espanol": "\n\n".join(espanol)}


def _ventanas(grupos: dict[str, str], tok, ventana: int, n_por_grupo: int):
    ids, etiquetas = [], []
    for grupo, texto in grupos.items():
        t = tok(texto)["input_ids"]
        n = min(n_por_grupo, len(t) // ventana)
        if n == 0:
            raise SystemExit(f"grupo {grupo!r}: {len(t)} tokens < 1 ventana de {ventana}")
        for i in range(n):
            ids.append(t[i * ventana:(i + 1) * ventana])
            etiquetas.append(grupo)
    return torch.tensor(ids, dtype=torch.long), etiquetas


# ── un pase por disco: [W,T] de ids -> [W,T,H] de estados ya normalizados ───
@torch.no_grad()
def flujo_final(ruta: Path, ids: torch.Tensor, dtype, capas_max: int | None, log=print):
    from transformers import AutoConfig, AutoModelForCausalLM
    from transformers.masking_utils import create_causal_mask
    try:
        from transformers.masking_utils import create_recurrent_attention_mask
    except ImportError:                                   # pragma: no cover
        create_recurrent_attention_mask = lambda **kw: None

    t0 = time.time()
    dep = _deposito(ruta)
    base = dep.prefijo_base()
    cfg = AutoConfig.from_pretrained(str(ruta))
    with torch.device("meta"):
        modelo = AutoModelForCausalLM.from_config(cfg)
    cfg_txt = getattr(cfg, "text_config", cfg)

    W, T = ids.shape
    emb = dep.tensores(base + "embed_tokens.", dtype=dtype)["weight"]
    flujo = emb[ids].clone()                              # [W,T,H] en RAM
    del emb

    rotary = type(modelo.model.rotary_emb)(cfg_txt, device="cpu")
    pos = torch.arange(T)[None]                           # [1,T]
    n = capas_max or dep.num_capas()
    for i in range(n):
        capa = modelo.model.layers[i]
        capa.load_state_dict(dep.capa(i, device="cpu", dtype=dtype), strict=True, assign=True)
        tipo = cfg_txt.layer_types[i]
        for w in range(W):
            x = flujo[w:w + 1]
            cos_sin = rotary(x, pos[None].expand(3, 1, -1))
            kw = dict(config=cfg_txt, inputs_embeds=x, attention_mask=None,
                      past_key_values=None, position_ids=pos)
            masc = (create_causal_mask(**kw) if tipo == "full_attention"
                    else create_recurrent_attention_mask(**kw))
            s = capa(x, position_embeddings=cos_sin, attention_mask=masc, position_ids=pos)
            flujo[w:w + 1] = s[0] if isinstance(s, tuple) else s
        capa.to("meta")
        if i % 8 == 0 or i == n - 1:
            log(f"    capa {i + 1}/{n} · {time.time() - t0:.0f}s")

    norma = modelo.model.norm
    norma.load_state_dict(dep.tensores(base + "norm.", device="cpu", dtype=dtype),
                          strict=True, assign=True)
    for w in range(W):
        flujo[w] = norma(flujo[w])
    log(f"    pase completo en {time.time() - t0:.0f}s")
    return flujo, time.time() - t0


def _cabeza(ruta: Path, dtype):
    """La matriz de salida. Los modelos pequeños de la familia (0,8B, 2B) traen
    `tie_word_embeddings: true`: su `lm_head` NO está en el checkpoint porque es la
    tabla de embeddings reutilizada. Se detecta, no se supone."""
    dep = _deposito(ruta)
    try:
        return dep.tensores("lm_head.", device="cpu", dtype=dtype)["weight"]
    except KeyError:
        return dep.tensores(dep.prefijo_base() + "embed_tokens.",
                            device="cpu", dtype=dtype)["weight"]


# ── simular el bucle especulativo sobre la secuencia real de aciertos ───────
def tokens_por_pase(acierto: torch.Tensor, gamma: int) -> tuple[float, int, int]:
    """`acierto[t]` = ¿el borrador propuso lo mismo que el grande en la posición t?
    Devuelve (tokens emitidos / pases del grande, tokens, pases). Un pase emite los
    k aciertos consecutivos (tope gamma) MÁS el token que corrige el grande."""
    n = acierto.numel()
    t = pases = emitidos = 0
    while t < n:
        k = 0
        while k < gamma and t + k < n and bool(acierto[t + k]):
            k += 1
        pases += 1
        emitidos += min(k + 1, n - t)      # los k aceptados + el corregido/extra
        t += k + 1
    return emitidos / pases, emitidos, pases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ventana", type=int, default=512)
    ap.add_argument("--ventanas", type=int, default=8, help="por dominio")
    ap.add_argument("--gamma", type=int, default=8)
    ap.add_argument("--capas", type=int, default=0, help="0 = todas; <64 sólo para sondas")
    ap.add_argument("--hilos", type=int, default=0)
    ap.add_argument("--trozo", type=int, default=64, help="posiciones por trozo de logits")
    ap.add_argument("--salida", default="")
    ap.add_argument("--borrador", default="", help="ruta del candidato a borrador")
    ap.add_argument("--cache", default="",
                    help="fichero donde guardar/leer las distribuciones del GRANDE")
    ap.add_argument("--topk", type=int, default=1024)
    a = ap.parse_args()
    borrador = Path(a.borrador) if a.borrador else BORRADOR

    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    dtype = torch.bfloat16
    t0 = time.time()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(GRANDE))
    ids, etiquetas = _ventanas(_corpus(RAIZ), tok, a.ventana, a.ventanas)
    W, T = ids.shape
    print(f"corpus: {W} ventanas de {T} tokens · {dict((g, etiquetas.count(g)) for g in set(etiquetas))}")
    print(f"hilos={torch.get_num_threads()} capas={a.capas or 64} gamma={a.gamma}")

    # ── el pase del GRANDE se paga UNA vez y se guarda ──────────────────────
    # De cada posición se conservan el argmax (exacto) y el top-K de p con su masa de
    # cola. Con eso, Σ min(p,q) queda ACOTADO —no estimado—: el término que falta es a
    # lo sumo min(masa de cola de p, masa que q pone fuera del top-K). Así cada
    # candidato a borrador cuesta su propio pase y no el del modelo de 52 GB.
    cache = Path(a.cache) if a.cache else None
    huella = hashlib.sha256(ids.numpy().tobytes()).hexdigest()[:16]
    C = None
    if cache and cache.exists():
        C = torch.load(cache)
        if C["huella"] != huella:
            raise SystemExit(f"la caché {cache} es de otro corpus ({C['huella']} != {huella}): bórrala")
        print(f"[1/3] GRANDE leído de la caché {cache} ({C['segundos']:.0f}s ahorrados)")
        seg_g = C["segundos"]
    else:
        print(f"[1/3] pase del GRANDE  {GRANDE}")
        fg, seg_g = flujo_final(GRANDE, ids, dtype, a.capas or None)
        Wg = _cabeza(GRANDE, dtype)
        arg, tid, tpr, cola, nll_g = [], [], [], [], []
        for w in range(W):
            for s0 in range(0, T - 1, a.trozo):
                e = min(s0 + a.trozo, T - 1)
                lg = F.linear(fg[w, s0:e], Wg).float().softmax(-1)
                v, i = lg.topk(a.topk, dim=-1)
                arg.append(i[:, 0].clone()); tid.append(i.clone()); tpr.append(v.half())
                cola.append((1 - v.sum(-1)).clamp_min(0))
                nll_g.append(-lg.gather(-1, ids[w, s0 + 1:e + 1, None]).log().squeeze(-1))
                del lg, v, i
        C = {"huella": huella, "argmax": torch.cat(arg), "topk_ids": torch.cat(tid),
             "topk_probs": torch.cat(tpr), "cola": torch.cat(cola),
             "nll": torch.cat(nll_g), "segundos": seg_g, "topk": a.topk}
        del fg, Wg
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            torch.save(C, cache)
            print(f"    caché del GRANDE escrita en {cache}")

    print(f"[2/3] pase del BORRADOR {borrador}")
    fb, seg_b = flujo_final(borrador, ids, dtype, a.capas or None)

    print("[3/3] cabeza del borrador y acuerdo")
    Wb = _cabeza(borrador, dtype)
    acuerdos, alfas, alfas_alto, nlls, nlls_g = {}, {}, {}, {}, {}
    k = 0
    for w in range(W):
        ac, al, ah, nb, ng = [], [], [], [], []
        for s0 in range(0, T - 1, a.trozo):
            e = min(s0 + a.trozo, T - 1)
            n = e - s0
            q = F.linear(fb[w, s0:e], Wb).float().softmax(-1)
            pid, ppr, cola = C["topk_ids"][k:k + n], C["topk_probs"][k:k + n].float(), C["cola"][k:k + n]
            qk = q.gather(-1, pid)
            ac.append(q.argmax(-1) == C["argmax"][k:k + n])
            base = torch.minimum(ppr, qk).sum(-1)
            al.append(base)                                   # cota inferior
            ah.append(base + torch.minimum(cola, (1 - qk.sum(-1)).clamp_min(0)))
            nb.append(-q.gather(-1, ids[w, s0 + 1:e + 1, None]).log().squeeze(-1))
            ng.append(C["nll"][k:k + n])
            k += n
            del q, qk
        g = etiquetas[w]
        acuerdos.setdefault(g, []).append(torch.cat(ac))
        alfas.setdefault(g, []).append(torch.cat(al))
        alfas_alto.setdefault(g, []).append(torch.cat(ah))
        nlls.setdefault(g, []).append(torch.cat(nb))
        nlls_g.setdefault(g, []).append(torch.cat(ng))

    res = {"ventana": T, "ventanas": W, "gamma": a.gamma, "capas": a.capas or 64,
           "hilos": torch.get_num_threads(), "borrador": str(borrador),
           "grande": str(GRANDE), "topk": C["topk"],
           "segundos": {"grande": round(seg_g, 1), "borrador": round(seg_b, 1),
                        "total": round(time.time() - t0, 1)},
           "por_dominio": {}}
    for g in acuerdos:
        acierto = torch.cat(acuerdos[g])
        alfa1 = torch.cat(alfas[g]).mean().item()
        alfa1_alto = torch.cat(alfas_alto[g]).mean().item()
        alfa0 = acierto.float().mean().item()
        nb = torch.cat(nlls[g])
        ng = torch.cat(nlls_g[g])
        d = {"tokens": int(acierto.numel()), "acuerdo_greedy": round(alfa0, 4),
             "alfa_t1": round(alfa1, 4), "alfa_t1_cota_alta": round(alfa1_alto, 4),
             "ppl_grande": round(float(ng.mean().exp()), 3),
             "ppl_borrador": round(float(nb.mean().exp()), 3)}
        for gam in sorted({a.gamma, 4, 8, 16}):
            tpp, em, pa = tokens_por_pase(acierto, gam)
            d[f"tokens_por_pase_g{gam}"] = round(tpp, 3)
            # la i.i.d. de la literatura, para ver cuánto se equivoca al ignorar ráfagas
            iid = (1 - alfa0 ** (gam + 1)) / (1 - alfa0) if alfa0 < 1 else gam + 1
            d[f"iid_g{gam}"] = round(iid, 3)
        res["por_dominio"][g] = d

    print("\n" + json.dumps(res["por_dominio"], indent=2, ensure_ascii=False))
    for g, d in res["por_dominio"].items():
        print(f"CIFRA acuerdo_greedy_{g} {d['acuerdo_greedy']}")
        print(f"CIFRA alfa_t1_{g} {d['alfa_t1']}")
        print(f"CIFRA tokens_por_pase_{g} {d[f'tokens_por_pase_g{a.gamma}']}")
        print(f"CIFRA ppl_grande_{g} {d['ppl_grande']}")
        print(f"CIFRA ppl_borrador_{g} {d['ppl_borrador']}")
    print(f"CIFRA segundos_pase_grande {round(seg_g, 1)}")

    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_C4-aceptacion.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
