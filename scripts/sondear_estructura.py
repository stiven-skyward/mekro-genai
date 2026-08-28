#!/usr/bin/env python3
"""sondear_estructura.py — ¿sigue estando la estructura RVQ dentro de los pesos deshechos?

LA PREGUNTA
-----------
`qwen38-h13b` guarda los pesos ya expandidos a bf16: los índices y los libros de códigos
no se escribieron nunca (ver docs/cerebro-2bit.md). Pero los números **no son
arbitrarios**: por construcción, cada grupo de g pesos vale

    W[fila, grupo] = α[fila] · ( C1[i] + C2[j] ),   |C1| = |C2| = 4096

Si esa estructura sigue siendo legible, el campeón se puede empaquetar a ~8 GB **en CPU y
sin volver a cuantizar nada**, y con ello cae M1. Si no, hay que ir al plan B (re-cuantizar
y medir cuánta calidad cuesta).

Esta sonda contesta esa pregunta sobre UNA matriz, en minutos, en CPU. Es la comprobación
barata que zanja antes de gastar la cara (CLAUDE.md §reglas).

POR QUÉ ES ATACABLE
-------------------
Porque el act-order de `hermetic3.py:134` permuta **grupos enteros**, no columnas sueltas:
los grupos son bloques de g columnas CONTIGUAS en el orden original. Si hubiera barajado
columnas, habría además que recuperar una permutación de 17.408 elementos y esto no sería
viable.

QUÉ IMPRIME (contrato de ciclo.py)
----------------------------------
    CIFRA razon_residuo   ‖v − C1[i]‖ / ‖v‖ tras la etapa 1. Si hay estructura RVQ, la
                          etapa 2 codifica un residuo PEQUEÑO → esto debe ser << 1.
    CIFRA err_relativo    error de reconstrucción con los libros recuperados, relativo al
                          RMS de la matriz. Si la recuperación es exacta → ~0.
    CIFRA frac_exacta     fracción de grupos reconstruidos dentro de la resolución de bf16.
                          El 1 % de columnas salientes (frac_saliente=0.01) NO está en el
                          retículo: no se espera 1,000, se espera ~0,99.

USO
---
    python3 scripts/sondear_estructura.py                     # capa 30, mlp.up_proj
    python3 scripts/sondear_estructura.py --capa 30 --g 16 --muestra 200000
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import torch

CAMPEON = Path(os.environ.get("MG_CAMPEON", "/mnt/e/QuantModels/modelos/qwen38-h13b"))
# La cadena v13 usó g=8 en estas capas y g=16 en el resto (`lanzar_v13.sh --capas-g8`).
# Sondear una capa con el g equivocado da un resultado falso negativo.
CAPAS_G8 = {0, 1, 2, 3, 58, 59, 60, 61, 62, 63}


def kmeans_cpu(X: torch.Tensor, k: int, iters: int = 12, semilla: int = 0,
               trozo: int = 4096) -> tuple[torch.Tensor, torch.Tensor]:
    """k-means L2 en CPU, con asignación por trozos.

    Por trozos y no de golpe porque la matriz de distancias de 200.000 × 4096 son 3,2 GB:
    en una máquina de 30 GB donde el objetivo es meter 8 GB de pesos, reventar la RAM en
    la sonda sería irónico.
    """
    gen = torch.Generator().manual_seed(semilla)
    n = X.shape[0]
    C = X[torch.randperm(n, generator=gen)[:k]].clone()
    idx = torch.zeros(n, dtype=torch.long)
    for it in range(iters):
        for a in range(0, n, trozo):
            b = min(a + trozo, n)
            idx[a:b] = torch.cdist(X[a:b], C).argmin(1)
        nuevo = torch.zeros_like(C).index_add_(0, idx, X)
        cuenta = torch.bincount(idx, minlength=k).clamp(min=1).unsqueeze(1)
        nuevo = nuevo / cuenta
        # Cúmulos vacíos: se resiembran en los puntos peor servidos. Dejarlos muertos
        # falsearía a la baja el número de códigos realmente usados.
        vacios = torch.bincount(idx, minlength=k) == 0
        if vacios.any():
            d = (X - C[idx]).pow(2).sum(1)
            peores = d.topk(int(vacios.sum())).indices
            nuevo[vacios] = X[peores]
        C = nuevo
    for a in range(0, n, trozo):
        b = min(a + trozo, n)
        idx[a:b] = torch.cdist(X[a:b], C).argmin(1)
    return C, idx


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default=str(CAMPEON))
    p.add_argument("--capa", type=int, default=30)
    p.add_argument("--tensor", default="mlp.up_proj.weight")
    p.add_argument("--g", type=int, default=0, help="0 = deducir de la capa")
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--muestra", type=int, default=120_000, help="grupos a muestrear")
    p.add_argument("--hilos", type=int, default=0)
    a = p.parse_args()

    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    g = a.g or (8 if a.capa in CAPAS_G8 else 16)
    ruta = Path(a.modelo)
    fichero = ruta / f"capa-{a.capa:02d}.safetensors"
    if not fichero.exists():
        raise SystemExit(f"no existe {fichero}")

    from safetensors import safe_open
    t0 = time.time()
    with safe_open(fichero, framework="pt") as f:
        nombre = next(k for k in f.keys() if k.endswith(a.tensor))
        W = f.get_tensor(nombre).float()
    print(f"tensor {nombre}  {tuple(W.shape)}  g={g}  "
          f"({time.time() - t0:.1f} s de disco)", flush=True)

    if W.shape[1] % g:
        raise SystemExit(f"la dimensión de entrada {W.shape[1]} no es múltiplo de g={g}")

    # α por fila. La cuantización la inicializó al RMS de la fila; el afinado (--afinar 60)
    # la movió, pero poco: si esta estimación no sirve, la sonda lo dirá en err_relativo.
    alfa = W.pow(2).mean(1, keepdim=True).sqrt().clamp(min=1e-12)
    grupos = (W / alfa).reshape(-1, g)
    total = grupos.shape[0]

    gen = torch.Generator().manual_seed(0)
    sel = torch.randperm(total, generator=gen)[:min(a.muestra, total)]
    X = grupos[sel].contiguous()
    print(f"{total} grupos en la matriz · {X.shape[0]} muestreados", flush=True)

    t1 = time.time()
    C1, i1 = kmeans_cpu(X, a.k, semilla=0)
    R = X - C1[i1]
    razon = (R.pow(2).sum(1).mean().sqrt() / X.pow(2).sum(1).mean().sqrt()).item()
    print(f"etapa 1: {time.time() - t1:.0f} s · razón del residuo {razon:.4f}", flush=True)

    t2 = time.time()
    C2, i2 = kmeans_cpu(R, a.k, semilla=1)
    rec = C1[i1] + C2[i2]
    err = (X - rec).pow(2).sum(1).sqrt()
    rms = X.pow(2).mean().sqrt()
    # `err` es la norma L2 de un vector de g dimensiones y `rms` es por escalar:
    # sin el √g la cifra saldría inflada ×4 y parecería un desastre que no es.
    err_rel = (err.mean() / (rms * g ** 0.5)).item()
    # bf16 tiene 8 bits de mantisa: por debajo de ~2^-8 relativo, dos números son el
    # mismo número guardado. Ese, y no cero, es el listón de «exacto».
    umbral = 4e-3 * rms.item() * (g ** 0.5)
    frac = (err < umbral).float().mean().item()
    print(f"etapa 2: {time.time() - t2:.0f} s", flush=True)

    print()
    print(f"CIFRA razon_residuo {razon:.6f}")
    print(f"CIFRA err_relativo {err_rel:.6f}")
    print(f"CIFRA frac_exacta {frac:.6f}")
    print()
    print(f"── {time.time() - t0:.0f} s en total, {torch.get_num_threads()} hilos, CPU")
    if frac > 0.95:
        print("LECTURA: la estructura RVQ es recuperable. Empaquetar sin re-cuantizar "
              "es viable → seguir por la salida (a) de docs/cerebro-2bit.md.")
    elif razon < 0.6:
        print("LECTURA: hay estructura (el residuo cae), pero la recuperación no es "
              "exacta. Sospecha de α: el afinado por capa la movió. Probar estimando α "
              "conjuntamente antes de descartar la salida (a).")
    else:
        print("LECTURA: no se ve el retículo. Ir a la salida (c): re-cuantizar en CPU y "
              "MEDIR cuánta calidad cuesta contra PPL 7,46.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
