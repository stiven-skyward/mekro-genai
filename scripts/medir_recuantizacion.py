#!/usr/bin/env python3
"""medir_recuantizacion.py — C17: qué cuesta en PPL la salida (c).

Re-cuantiza las matrices del checkpoint deshecho con un RVQ propio —libros que
GENERAMOS y por tanto podemos guardar— y mide la perplejidad resultante contra la del
deshecho sin tocar. No necesita recuperar nada ni GPU.

El error de peso del campeón frente al BF16 ya es 0,4929 (medido 2026-08-23): la
cuantización original perturba los pesos la mitad de su magnitud. Nuestro RVQ añade 0,123,
que en cuadratura sube el total a 0,5080, un 3,1 % más. La pregunta es qué le hace eso a
la PPL, porque el criterio de M1 es +1 %, no una norma.

El CONTROL es la misma carrera sin re-cuantizar: mismas ventanas, mismos tokens.
"""
from __future__ import annotations

import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse, json, os, sys, time
from pathlib import Path
import torch
import torch.nn.functional as F

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ / "scripts"))
CAMPEON = Path(os.environ.get("MG_CAMPEON_EXT4", "/home/forge/modelos/qwen38-h13b"))

from medir_aceptacion import _corpus, _ventanas, _deposito, _cabeza    # noqa: E402
from sondear_estructura import kmeans_cpu                              # noqa: E402


def ensuciar(W, eps, semilla=5):
    """Ruido gaussiano de magnitud relativa `eps`. No es error de cuantización —no está
    correlacionado con los pesos— y por eso el experimento lleva su propia validación:
    al nivel del RVQ real debe reproducir su daño, o el proxy no vale."""
    gen = torch.Generator().manual_seed(semilla)
    r = torch.randn(W.shape, generator=gen)
    r = r / r.norm() * W.norm() * eps
    return W + r, float(r.norm() / W.norm())


def recuantizar(W, g=16, k=4096, n=100000, iters=5, semilla=5):
    """RVQ de dos etapas sobre los grupos de `g` columnas. Devuelve la reconstrucción
    y el error relativo. Los libros son NUESTROS: se pueden guardar."""
    filas, cols = W.shape
    if cols % g:
        return W, 0.0
    V = W.reshape(-1, g)
    gen = torch.Generator().manual_seed(semilla)
    sel = torch.randperm(V.shape[0], generator=gen)[:min(n, V.shape[0])]
    M = V[sel].contiguous()
    C1, _ = kmeans_cpu(M, k, iters=iters, semilla=semilla)
    i1 = torch.cdist(M, C1).argmin(1)
    C2, _ = kmeans_cpu((M - C1[i1]).contiguous(), k, iters=iters, semilla=semilla + 1)
    # asignación de TODOS los grupos, por trozos
    rec = torch.empty_like(V)
    for a in range(0, V.shape[0], 16384):
        b = min(a + 16384, V.shape[0])
        u = V[a:b]
        j1 = torch.cdist(u, C1).argmin(1)
        j2 = torch.cdist(u - C1[j1], C2).argmin(1)
        rec[a:b] = C1[j1] + C2[j2]
    err = float((rec - V).norm() / V.norm())
    return rec.reshape(filas, cols), err


@torch.no_grad()
def pase(ids, capas_rq, dtype, cfg_kw, log=print):
    from transformers import AutoConfig, AutoModelForCausalLM
    from transformers.masking_utils import create_causal_mask
    try:
        from transformers.masking_utils import create_recurrent_attention_mask
    except ImportError:
        create_recurrent_attention_mask = lambda **kw: None
    t0 = time.time()
    dep = _deposito(CAMPEON); base = dep.prefijo_base()
    cfg = AutoConfig.from_pretrained(str(CAMPEON))
    with torch.device("meta"):
        modelo = AutoModelForCausalLM.from_config(cfg)
    cfg_txt = getattr(cfg, "text_config", cfg)
    W, T = ids.shape
    emb = dep.tensores(base + "embed_tokens.", dtype=dtype)["weight"]
    flujo = emb[ids].clone(); del emb
    rotary = type(modelo.model.rotary_emb)(cfg_txt, device="cpu")
    pos = torch.arange(T)[None]
    errores = []
    for i in range(dep.num_capas()):
        pesos = dep.capa(i, device="cpu", dtype=dtype)
        if i in capas_rq:
            for nombre, t in list(pesos.items()):
                if t.dim() == 2 and t.shape[1] % 16 == 0 and t.numel() > 1_000_000:
                    rec, e = (ensuciar(t.float(), cfg_kw["eps"])
                              if "eps" in cfg_kw else recuantizar(t.float(), **cfg_kw))
                    pesos[nombre] = rec.to(dtype); errores.append(e)
            log(f"    capa {i} re-cuantizada · err {errores[-1]:.4f} · {time.time()-t0:.0f}s")
        capa = modelo.model.layers[i]
        capa.load_state_dict(pesos, strict=True, assign=True); del pesos
        tipo = cfg_txt.layer_types[i]
        for w in range(W):
            x = flujo[w:w + 1]
            cs = rotary(x, pos[None].expand(3, 1, -1))
            kw = dict(config=cfg_txt, inputs_embeds=x, attention_mask=None,
                      past_key_values=None, position_ids=pos)
            m = (create_causal_mask(**kw) if tipo == "full_attention"
                 else create_recurrent_attention_mask(**kw))
            s = capa(x, position_embeddings=cs, attention_mask=m, position_ids=pos)
            flujo[w:w + 1] = s[0] if isinstance(s, tuple) else s
        capa.to("meta")
    norma = modelo.model.norm
    norma.load_state_dict(dep.tensores(base + "norm.", device="cpu", dtype=dtype),
                          strict=True, assign=True)
    Wc = _cabeza(CAMPEON, dtype)
    nll, n = 0.0, 0
    for w in range(W):
        x = norma(flujo[w])[:-1]
        obj = ids[w, 1:]
        for a in range(0, x.shape[0], 64):
            b = min(a + 64, x.shape[0])
            lg = F.linear(x[a:b], Wc).float()
            nll += F.cross_entropy(lg, obj[a:b], reduction="sum").item(); n += b - a
            del lg
    return nll / n, (sum(errores) / len(errores) if errores else 0.0), time.time() - t0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ventana", type=int, default=512)
    p.add_argument("--ventanas", type=int, default=1)
    p.add_argument("--capas", default="20,30,40,50", help="capas a re-cuantizar")
    p.add_argument("--n-ajuste", type=int, default=100000)
    p.add_argument("--iters", type=int, default=5)
    p.add_argument("--ruido", default="",
                   help="niveles de error relativo separados por comas: en vez de "
                        "re-cuantizar, inyecta ruido gaussiano de esa magnitud. Mide el "
                        "EXPONENTE con que el daño crece con el error de peso, sin pagar "
                        "el ajuste RVQ. Se valida solo: al nivel 0,3765 debe reproducir "
                        "los 0,02176 nats/capa que midió el RVQ real (C17).")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(CAMPEON))
    ids, etq = _ventanas(_corpus(RAIZ), tok, a.ventana, a.ventanas)
    capas = [int(x) for x in a.capas.split(",")]
    print(f"corpus {ids.shape} · capas a re-cuantizar {capas} · hilos {torch.get_num_threads()}")

    print("[control] el deshecho sin tocar")
    nll0, _, s0 = pase(ids, set(), torch.bfloat16, {})
    print(f"    nll {nll0:.5f} · ppl {torch.tensor(nll0).exp():.4f} · {s0:.0f}s")

    if a.ruido:
        niveles = [float(x) for x in a.ruido.split(",")]
        curva = []
        for eps in niveles:
            nll_e, err_e, s_e = pase(ids, set(capas), torch.bfloat16, dict(eps=eps))
            d_e = (nll_e - nll0) / len(capas)
            curva.append({"eps": eps, "nll": round(nll_e, 5),
                          "delta_nats_por_capa": round(d_e, 6)})
            print(f"    eps {eps:.4f} · nll {nll_e:.5f} · Δ/capa {d_e:.6f} · {s_e:.0f}s")
        import math
        pts = [(math.log(c["eps"]), math.log(max(c["delta_nats_por_capa"], 1e-9)))
               for c in curva if c["delta_nats_por_capa"] > 0]
        if len(pts) >= 2:
            mx = sum(x for x, _ in pts) / len(pts); my = sum(y for _, y in pts) / len(pts)
            expo = (sum((x - mx) * (y - my) for x, y in pts) /
                    max(sum((x - mx) ** 2 for x, _ in pts), 1e-12))
        else:
            expo = 0.0
        # validación: al nivel del RVQ real (0,3765) el ruido debe dar ~0,02176 nats/capa
        cerca = min(curva, key=lambda c: abs(c["eps"] - 0.3765))
        razon = cerca["delta_nats_por_capa"] / 0.02176
        res = {"capas": capas, "nll_control": round(nll0, 5), "curva": curva,
               "exponente": round(expo, 4), "nivel_validacion": cerca["eps"],
               "razon_ruido_vs_rvq": round(razon, 4), "segundos": round(time.time(), 0)}
        print("\n" + json.dumps(res, indent=2, ensure_ascii=False))
        print(f"CIFRA exponente {res['exponente']}")
        print(f"CIFRA razon_ruido_vs_rvq {res['razon_ruido_vs_rvq']}")
        destino = Path(a.salida) if a.salida else (
            RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_exponente.json")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nregistro: {destino}")
        return 0

    print(f"[2/2] re-cuantizando {len(capas)} capas")
    nll1, err, s1 = pase(ids, set(capas), torch.bfloat16,
                         dict(n=a.n_ajuste, iters=a.iters))
    print(f"    nll {nll1:.5f} · ppl {torch.tensor(nll1).exp():.4f} · {s1:.0f}s")

    d = (nll1 - nll0) / len(capas)
    razon_total = float(torch.tensor(nll0 + d * 64).exp() / torch.tensor(nll0).exp())
    res = {"capas_recuantizadas": capas, "err_rvq_medio": round(err, 4),
           "nll_control": round(nll0, 5), "nll_recuantizado": round(nll1, 5),
           "ppl_control": round(float(torch.tensor(nll0).exp()), 4),
           "ppl_recuantizado": round(float(torch.tensor(nll1).exp()), 4),
           "delta_nats_por_capa": round(d, 6),
           "razon_ppl_extrapolada_64": round(razon_total, 4),
           "segundos": round(s0 + s1, 1)}
    print("\n" + json.dumps(res, indent=2, ensure_ascii=False))
    print(f"CIFRA razon_ppl {res['razon_ppl_extrapolada_64']}")
    print(f"CIFRA delta_nats_por_capa {res['delta_nats_por_capa']}")
    print(f"CIFRA err_rvq_medio {res['err_rvq_medio']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_recuant.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
