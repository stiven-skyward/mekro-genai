#!/usr/bin/env python3
"""tejer_traslaciones.py — H1: el árbol de traslaciones entre cúmulos.

LA IDEA, QUE ES LA DE C12 UN NIVEL MÁS ARRIBA
----------------------------------------------
C14 midió que entre dos cúmulos la misma diferencia se repite cientos de veces (242
frente a 2 del control): esa diferencia dominante es `d_AB = C1[i_A] − C1[i_B]`, el
desplazamiento que lleva un trasladado de C2 al otro.

Si eso es cierto, los desplazamientos **tienen que componer**:

    d_AB + d_BC = d_AC     para cualquier triángulo de cúmulos.

Es exactamente la prueba que validó las escalas en C12 —allí el grafo era de filas unidas
por duplicados, aquí de cúmulos unidos por traslaciones— y tiene la misma virtud: son
cientos de comprobaciones independientes que **ninguna explicación posterior puede
acomodar**. Un triángulo que cierra a 0,01 cuando el control cierra a 1 no lo produce el
azar.

Y si cierran, `C1` queda recuperado salvo una traslación global: se toma un cúmulo de
referencia y se propaga por el árbol, igual que se propagó `log β` en C12.
"""
from __future__ import annotations

# Las carreras van desatendidas con nohup: si la salida se bufferiza, el monitor que la
# vigila queda CIEGO y una carrera de media hora no emite una sola línea. Lección del
# 2026-08-23, con C16 corriendo 27 min sin señal. Se fuerza el vaciado en cada print.
import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse
import itertools
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

from recuperar_escalas import matriz                    # noqa: E402
from recuperar_libros import escalas                    # noqa: E402
from sondear_estructura import kmeans_cpu               # noqa: E402
from sondear_traslacion import asignar_todo             # noqa: E402


def traslacion_dominante(A, B, delta=0.25, semilla=17):
    """Devuelve (vector de la traslación más repetida, su multiplicidad)."""
    d = (A[:, None, :] - B[None, :, :]).reshape(-1, A.shape[1])
    paso = (d.abs().median().clamp_min(1e-12)) * delta
    gen = torch.Generator().manual_seed(semilla)
    peso = torch.randint(1, 2**31, (d.shape[1],), generator=gen, dtype=torch.int64)
    clave = (torch.round(d / paso).to(torch.int64) * peso).sum(1)
    orden = torch.argsort(clave)
    c = clave[orden]
    cambio = torch.ones(c.numel(), dtype=torch.bool)
    cambio[1:] = c[1:] != c[:-1]
    ini = cambio.nonzero().squeeze(1)
    fin = torch.cat([ini[1:], torch.tensor([c.numel()])])
    k = int((fin - ini).argmax())
    sel = orden[ini[k]:fin[k]]
    return d[sel].mean(0), int(sel.numel())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=30)
    p.add_argument("--tensor", default="mlp.gate_proj")
    p.add_argument("--g", type=int, default=16)
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--n-kmeans", type=int, default=400000)
    p.add_argument("--cumulos", type=int, default=10, help="cuántos cúmulos se tejen")
    p.add_argument("--tope-cumulo", type=int, default=1200)
    p.add_argument("--min-mult", type=int, default=20, help="arista válida")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()
    gen = torch.Generator().manual_seed(11)
    res = {"capa": a.capa, "tensor": a.tensor, "cumulos": a.cumulos, "fuentes": {}}

    for fuente, ruta in (("campeon", CAMPEON), ("bf16", GRANDE)):
        W = matriz(ruta, a.capa, a.tensor)
        filas, cols = W.shape
        ng = cols // a.g
        if fuente == "campeon":
            beta, _, _ = escalas(W, a.g)
        else:
            beta = W.reshape(filas, -1).pow(2).mean(1).sqrt()
        U = (W / beta[:, None]).reshape(filas * ng, a.g).contiguous()
        sel = torch.randperm(U.shape[0], generator=gen)[:a.n_kmeans]
        C1, _ = kmeans_cpu(U[sel].contiguous(), a.k, iters=8, semilla=5)
        idx = asignar_todo(U, C1)
        cuenta = torch.bincount(idx, minlength=a.k)
        mayores = cuenta.argsort(descending=True)[:a.cumulos].tolist()
        grupos = [U[idx == c][:a.tope_cumulo].contiguous() for c in mayores]
        print(f"[{fuente}] {a.cumulos} cúmulos de "
              f"{[gr.shape[0] for gr in grupos]} puntos · {time.time()-t0:.0f}s")

        D, M = {}, {}
        for x, y in itertools.combinations(range(a.cumulos), 2):
            d, m = traslacion_dominante(grupos[x], grupos[y])
            D[(x, y)] = d; M[(x, y)] = m
            D[(y, x)] = -d; M[(y, x)] = m
        mults = sorted((M[(x, y)] for x, y in itertools.combinations(range(a.cumulos), 2)),
                       reverse=True)
        print(f"[{fuente}] multiplicidades de las {len(mults)} aristas: {mults[:6]} …")

        # LA PRUEBA: los triángulos tienen que cerrar
        cierres = []
        for x, y, z in itertools.combinations(range(a.cumulos), 3):
            if min(M[(x, y)], M[(y, z)], M[(x, z)]) < a.min_mult:
                continue
            r = (D[(x, y)] + D[(y, z)] - D[(x, z)]).norm() / D[(x, z)].norm().clamp_min(1e-12)
            cierres.append(float(r))
        t = torch.tensor(cierres) if cierres else torch.tensor([9.9])
        res["fuentes"][fuente] = {
            "tam_cumulos": [gr.shape[0] for gr in grupos],
            "multiplicidades": mults,
            "aristas_validas": sum(1 for v in mults if v >= a.min_mult),
            "triangulos": len(cierres),
            "cierre_mediano": round(float(t.median()), 5),
            "cierre_p90": round(float(t.quantile(0.9)), 5),
            "segundos": round(time.time() - t0, 1)}
        print(f"[{fuente}] {len(cierres)} triángulos · cierre mediano "
              f"{float(t.median()):.5f} · p90 {float(t.quantile(0.9)):.5f}\n")
        del W, U

    c, b = res["fuentes"]["campeon"], res["fuentes"]["bf16"]
    res["segundos"] = round(time.time() - t0, 1)
    print(f"CIFRA cierre_traslaciones_mediano {c['cierre_mediano']}")
    print(f"CIFRA cierre_traslaciones_control {b['cierre_mediano']}")
    print(f"CIFRA triangulos {c['triangulos']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_tejido.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
