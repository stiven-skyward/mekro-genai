#!/usr/bin/env python3
"""recuperar_libros.py — H1, último paso: separar el sumset C1 ⊕ C2.

DÓNDE ESTAMOS
-------------
C11 midió que el retículo sigue en los pesos deshechos y que su libro tiene 15,73 M ≈
4096² entradas. C12 **recuperó** `β_fila` leyéndola de los puentes de duplicados (cierre
de ciclos 0,0034-0,0040 contra 0,33-0,52 del control). Con eso, los grupos desescalados de
**todas** las filas viven en el MISMO retículo de 16,8 M puntos:

    U[r, grupo] = W[r, grupo] / β_r = C1[i] + C2[j]

Falta separar el sumset. Se hace con el mismo procedimiento que usó el cuantizador
original —RVQ codicioso de dos etapas— pero sabiendo algo que él no sabía: **existe una
solución con error exactamente cero**.

EL SUELO DEL AZAR, QUE ES LO QUE NO MIRÓ C1
--------------------------------------------
En 16 dimensiones con 4096 códigos, la cota tasa-distorsión da residuo ≈0,60 por etapa
sobre **cualquier** nube. Dos etapas ⇒ ≈0,36. Ese 0,36 no es señal: es el suelo. C1 midió
0,248 con la escala equivocada y aun así no significaba nada. Por eso aquí la cifra va
siempre con **control**: el mismo ajuste, mismo k, mismas iteraciones, sobre la MISMA
matriz del BF16 sin cuantizar, donde no hay retículo que encontrar.

USO
---
  python3 scripts/recuperar_libros.py --capa 45 --tensor mlp.up_proj --n 200000 --iters 6
"""
from __future__ import annotations

# Las carreras van desatendidas con nohup: si la salida se bufferiza, el monitor que la
# vigila queda CIEGO y una carrera de media hora no emite una sola línea. Lección del
# 2026-08-23, con C16 corriendo 27 min sin señal. Se fuerza el vaciado en cada print.
import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ / "scripts"))
CAMPEON = Path(os.environ.get("MG_CAMPEON_EXT4", "/home/forge/modelos/qwen38-h13b"))
GRANDE = Path(os.environ.get("MG_BF16", "/home/forge/modelos/qwen3.8-27b"))

from recuperar_escalas import matriz, puentes, arbol_y_cierre     # noqa: E402
from sondear_estructura import kmeans_cpu                          # noqa: E402


def escalas(W: torch.Tensor, g: int, bits=20, rondas=3, vecinos=4, eps=0.015):
    """β por fila leída de los puentes de duplicados (C12). Devuelve (β, cierre)."""
    filas, cols = W.shape
    ng = cols // g
    V = W.reshape(filas * ng, g)
    normas = V.norm(dim=1)
    idx = (normas > 0).nonzero().squeeze(1)
    D = V[idx] / normas[idx, None]
    fila_de = idx // ng
    A, B = [], []
    for r in range(rondas):
        x, y = puentes(D, normas, fila_de, bits, 100 + r, eps, vecinos)
        A.append(x); B.append(y)
    A, B = torch.cat(A), torch.cat(B)
    logr = normas[idx[A]].log() - normas[idx[B]].log()
    logbeta, _, residuo = arbol_y_cierre(fila_de[A], fila_de[B], logr, filas)
    beta = logbeta.exp()
    beta[torch.isnan(beta)] = 1.0                     # filas aisladas: escala neutra
    cierre = float(residuo.median()) if residuo.numel() else 9.9
    return beta, cierre, int((~torch.isnan(logbeta)).sum())


def asignar(U, C1, C2, trozo=8192):
    """Asignación codiciosa, la misma que hace un RVQ: primero la etapa 1, luego la 2
    sobre el residuo. No se busca el mejor par (i,j) de los 16,8 M: se reproduce el
    procedimiento del cuantizador, que es el que generó estos pesos."""
    n = U.shape[0]
    i1 = torch.empty(n, dtype=torch.long)
    i2 = torch.empty(n, dtype=torch.long)
    for a in range(0, n, trozo):
        b = min(a + trozo, n)
        u = U[a:b]
        i1[a:b] = torch.cdist(u, C1).argmin(1)
        i2[a:b] = torch.cdist(u - C1[i1[a:b]], C2).argmin(1)
    return i1, i2


def _media_por_codigo(X, idx, k, previo):
    suma = torch.zeros_like(previo).index_add_(0, idx, X)
    cuenta = torch.bincount(idx, minlength=k).clamp(min=1).unsqueeze(1)
    nuevo = suma / cuenta
    vacio = torch.bincount(idx, minlength=k) == 0
    nuevo[vacio] = previo[vacio]                      # códigos muertos: se dejan quietos
    return nuevo


def ajustar(U, k, iters, semilla, log=print):
    """RVQ de dos etapas con alternancia. Devuelve (C1, C2, err_relativo, traza)."""
    C1, i1 = kmeans_cpu(U, k, iters=8, semilla=semilla)
    R = U - C1[i1]
    C2, i2 = kmeans_cpu(R, k, iters=8, semilla=semilla + 1)
    norma_media = U.norm(dim=1).mean()
    traza = []
    for it in range(iters):
        i1, i2 = asignar(U, C1, C2)
        # reestimar cada libro dejando fijo el otro: mínimos cuadrados por bloques
        C1 = _media_por_codigo(U - C2[i2], i1, k, C1)
        C2 = _media_por_codigo(U - C1[i1], i2, k, C2)
        err = float((U - C1[i1] - C2[i2]).norm(dim=1).mean() / norma_media)
        traza.append(round(err, 5))
        log(f"    iter {it + 1}/{iters} · err_relativo {err:.5f}")
    return C1, C2, traza[-1], traza


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=45)
    p.add_argument("--tensor", default="mlp.up_proj")
    p.add_argument("--g", type=int, default=16)
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--n", type=int, default=200000, help="grupos para el ajuste")
    p.add_argument("--iters", type=int, default=6)
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()

    res = {"capa": a.capa, "tensor": a.tensor, "g": a.g, "k": a.k, "n": a.n,
           "iters": a.iters, "fuentes": {}}
    gen = torch.Generator().manual_seed(11)
    for fuente, ruta in (("campeon", CAMPEON), ("bf16", GRANDE)):
        W = matriz(ruta, a.capa, a.tensor)
        filas, cols = W.shape
        ng = cols // a.g
        if fuente == "campeon":
            beta, cierre, conectadas = escalas(W, a.g)
            print(f"[{fuente}] β leída de los puentes · cierre {cierre:.5f} · "
                  f"{conectadas}/{filas} filas · {time.time()-t0:.0f}s")
        else:
            # El control NO tiene retículo, luego no tiene β que leer. Se le da la
            # ventaja de una escala por fila estimada (RMS): si aun así no baja de 0,36,
            # el suelo del azar queda demostrado y no supuesto.
            beta = W.reshape(filas, -1).pow(2).mean(1).sqrt()
            cierre, conectadas = float("nan"), filas
            print(f"[{fuente}] control · β = RMS de fila (la ventaja se la doy yo)")
        U_todo = (W / beta[:, None]).reshape(filas * ng, a.g)
        sel = torch.randperm(U_todo.shape[0], generator=gen)[:a.n]
        U = U_todo[sel].contiguous()
        print(f"[{fuente}] ajustando k={a.k} sobre {U.shape[0]:,} grupos")
        C1, C2, err, traza = ajustar(U, a.k, a.iters, semilla=5)
        # validación fuera de la muestra: grupos que el ajuste no vio
        sel2 = torch.randperm(U_todo.shape[0], generator=gen)[:min(50000, U_todo.shape[0])]
        Uv = U_todo[sel2].contiguous()
        j1, j2 = asignar(Uv, C1, C2)
        err_fuera = float((Uv - C1[j1] - C2[j2]).norm(dim=1).mean() / Uv.norm(dim=1).mean())
        res["fuentes"][fuente] = {
            "err_relativo": round(err, 5), "err_fuera_de_muestra": round(err_fuera, 5),
            "traza": traza, "cierre_beta": None if cierre != cierre else round(cierre, 5),
            "filas_conectadas": conectadas, "segundos": round(time.time() - t0, 1)}
        print(f"[{fuente}] err_relativo {err:.5f} · fuera de muestra {err_fuera:.5f}\n")
        del W, U_todo, U

    c, b = res["fuentes"]["campeon"], res["fuentes"]["bf16"]
    res["suelo_azar_teorico"] = 0.36
    res["segundos"] = round(time.time() - t0, 1)
    print(f"CIFRA err_relativo {c['err_relativo']}")
    print(f"CIFRA err_relativo_control {b['err_relativo']}")
    print(f"CIFRA err_fuera_de_muestra {c['err_fuera_de_muestra']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_libros.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
