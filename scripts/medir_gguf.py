#!/usr/bin/env python3
"""medir_gguf.py — el cerebro de trabajo: PPL y tokens/s del GGUF en CPU.

Mide sobre EL MISMO corpus que el resto del proyecto (código + español de este
repositorio, ventanas de 512) para que las cifras sean comparables con las que ya hay:

    BF16 sin cuantizar ......... PPL  5,764 (código) · 4,839 (español)
    campeón v13 a 1,9995 bits ... PPL 15,967 (código) · 17,518 (español)

Esto NO es M1: es el cerebro de trabajo que META.md autoriza para avanzar el arnés
mientras H1 no exista. Se identifica siempre por su fichero y su cuantización.
"""
from __future__ import annotations

import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse, json, math, os, sys, time
import numpy as np
from pathlib import Path

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ / "scripts"))
from medir_aceptacion import _corpus                                   # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default="/home/forge/modelos/gguf/Qwen3.8-27B-UD-Q2_K_XL.gguf")
    p.add_argument("--ventana", type=int, default=512)
    p.add_argument("--ventanas", type=int, default=4, help="por dominio")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--generar", type=int, default=64, help="tokens para medir tok/s")
    p.add_argument("--solo-velocidad", action="store_true",
                   help="sin logits_all: el flag existe para la perplejidad y arruina la "
                        "velocidad, porque obliga a calcular los 248.320 logits en CADA "
                        "posición. Medir tok/s con él puesto no mide el modelo, mide el flag.")
    p.add_argument("--salida", default="")
    a = p.parse_args()
    hilos = a.hilos or os.cpu_count() or 8
    from llama_cpp import Llama
    t0 = time.time()
    print(f"cargando {Path(a.modelo).name} · {os.path.getsize(a.modelo)/2**30:.2f} GB · "
          f"{hilos} hilos · n_gpu_layers=0")
    llm = Llama(model_path=a.modelo, n_ctx=a.ventana + 8, n_threads=hilos,
                n_gpu_layers=0, logits_all=not a.solo_velocidad, verbose=False)
    print(f"cargado en {time.time()-t0:.0f}s")

    res = {"modelo": a.modelo, "gb": round(os.path.getsize(a.modelo)/2**30, 2),
           "hilos": hilos, "ventana": a.ventana, "logits_all": not a.solo_velocidad,
           "por_dominio": {}}
    for dom, texto in ({} if a.solo_velocidad else _corpus(RAIZ)).items():
        ids = llm.tokenize(texto.encode("utf-8"), add_bos=False)
        n_v = min(a.ventanas, len(ids) // a.ventana)
        nll, n = 0.0, 0
        for w in range(n_v):
            trozo = ids[w * a.ventana:(w + 1) * a.ventana]
            llm.reset(); llm.eval(trozo)
            # vectorizado: recorrer 248.320 logits por posición en Python puro serían
            # 127 millones de operaciones por ventana y la carrera no terminaría nunca
            sc = np.asarray(llm.scores[:len(trozo)], dtype=np.float32)
            m = sc.max(axis=1, keepdims=True)
            lse = (m[:, 0] + np.log(np.exp(sc - m).sum(axis=1)))
            obj = np.asarray(trozo[1:], dtype=np.int64)
            nll += float((lse[:-1] - sc[np.arange(len(trozo) - 1), obj]).sum())
            n += len(trozo) - 1
        res["por_dominio"][dom] = {"ventanas": n_v, "tokens": n,
                                   "nll": round(nll / n, 5),
                                   "ppl": round(math.exp(nll / n), 4)}
        print(f"  {dom}: {n_v} ventanas · {n} tokens · PPL {math.exp(nll/n):.4f}")

    # tokens/s: prefill corto y generación, que es lo que mide META.md
    llm.reset()
    prompt = llm.tokenize(b"def sumar(a, b):\n    return", add_bos=True)
    t1 = time.time(); llm.eval(prompt); t_prefill = time.time() - t1
    t2 = time.time(); n_gen = 0
    tok = llm.sample()
    for _ in range(a.generar):
        llm.eval([tok]); tok = llm.sample(); n_gen += 1
        if tok == llm.token_eos(): break
    dt = time.time() - t2
    res["prefill_seg"] = round(t_prefill, 3)
    res["tokens_generados"] = n_gen
    res["seg_por_token"] = round(dt / max(n_gen, 1), 4)
    res["tokens_por_s"] = round(n_gen / dt, 3)
    print(f"  generación: {n_gen} tokens en {dt:.1f}s = {n_gen/dt:.3f} tok/s")

    for dom, d in res["por_dominio"].items():
        print(f"CIFRA ppl_{dom} {d['ppl']}")
    print(f"CIFRA tokens_por_s {res['tokens_por_s']}")
    print(f"CIFRA gb_residentes {res['gb']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_gguf.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
