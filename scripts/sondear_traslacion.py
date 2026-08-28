#!/usr/bin/env python3
"""sondear_traslacion.py — H1: el sumset por sus TRASLACIONES, no por sus cúmulos.

POR QUÉ NO SIRVE EL k-MEANS (C13)
----------------------------------
Con `β` recuperada, el ajuste RVQ codicioso baja a err_relativo 0,12275 frente a 0,39906
del control — el retículo se nota — pero no lo separa, y H1 no necesita 0,05: necesita
**cero**. El descenso por coordenadas converge a un RVQ *válido pero distinto* del
original, porque hay muchas factorizaciones de la misma nube y cae en la más cercana a su
inicialización aleatoria.

LA ESTRUCTURA QUE EL k-MEANS IGNORA
------------------------------------
Para un `i` fijo, `{C1[i] + C2[j] : j}` es un **trasladado de C2**. Luego dos cúmulos
verdaderos, el de `i` y el de `i'`, **son el mismo conjunto desplazado** por
`d = C1[i] − C1[i']`. Y eso tiene una consecuencia que se puede contar:

    entre dos cúmulos verdaderos, la MISMA diferencia `d` aparece una vez por cada `j`
    que los dos usan — cientos de veces. Entre dos nubes cualesquiera, cada diferencia
    aparece una vez.

Es la palanca de C11 y C12 otra vez: **contar coincidencias en vez de reconstruir**.

LO QUE MIDE ESTA SONDA
----------------------
Multiplicidad máxima de una diferencia entre los dos cúmulos mayores. Con ~1.360 puntos
por cúmulo y 4096 códigos en la segunda etapa, los `j` compartidos son ≈1360²/4096 ≈ 450,
así que un cúmulo razonablemente puro debe dar centenares. El **control** es el mismo
procedimiento sobre la misma matriz del BF16, donde no hay traslación que encontrar.
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

from recuperar_escalas import matriz                    # noqa: E402
from recuperar_libros import escalas                    # noqa: E402
from sondear_estructura import kmeans_cpu               # noqa: E402


def asignar_todo(U, C1, trozo=16384):
    idx = torch.empty(U.shape[0], dtype=torch.long)
    for a in range(0, U.shape[0], trozo):
        b = min(a + trozo, U.shape[0])
        idx[a:b] = torch.cdist(U[a:b], C1).argmin(1)
    return idx


def multiplicidad(A, B, delta=0.25, offsets=3, semilla=17, topn=5):
    """Diferencia más repetida entre dos conjuntos, por REJILLA sobre el vector entero.

    La firma de signos de C12 NO sirve aquí y el primer intento lo demostró: las
    diferencias entre dos cúmulos apuntan casi todas en la misma dirección —la que une
    los centroides—, así que una firma que sólo mira orientación mete 10.096 de 2,25 M
    en el mismo cubo y no discrimina nada.

    Lo que sí sirve es cuantizar el vector COMPLETO a una rejilla y contar la celda más
    poblada. En 16 dimensiones eso es seguro por dos lados a la vez: la rejilla puede ser
    gruesa —basta que sea mayor que el ruido de bf16, ~0,002 relativo— porque el espacio
    tiene tantas celdas (≈30¹⁶ ≈ 4·10²³ para esta nube) que dos diferencias distintas no
    coinciden jamás por azar. Con varios desplazamientos aleatorios de la rejilla se evita
    que una traslación verdadera caiga justo en una frontera.
    """
    d = (A[:, None, :] - B[None, :, :]).reshape(-1, A.shape[1])
    escala = d.abs().median().clamp_min(1e-12)
    paso = delta * escala
    gen = torch.Generator().manual_seed(semilla)
    peso = torch.randint(1, 2**31, (d.shape[1],), generator=gen, dtype=torch.int64)
    mejor, tops = 0, []
    for o in range(offsets):
        des = torch.rand(d.shape[1], generator=gen) if o else torch.zeros(d.shape[1])
        q = torch.round(d / paso + des).to(torch.int64)
        clave = (q * peso).sum(1)
        clave, _ = clave.sort()
        cambio = torch.ones(clave.numel(), dtype=torch.bool)
        cambio[1:] = clave[1:] != clave[:-1]
        ini = cambio.nonzero().squeeze(1)
        fin = torch.cat([ini[1:], torch.tensor([clave.numel()])])
        tam = (fin - ini)
        mejor = max(mejor, int(tam.max()))
        tops.append(sorted(tam.tolist(), reverse=True)[:topn])
    return mejor, tops, int(d.shape[0]), float(escala)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=45)
    p.add_argument("--tensor", default="mlp.up_proj")
    p.add_argument("--g", type=int, default=16)
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--n-kmeans", type=int, default=600000)
    p.add_argument("--tope-cumulo", type=int, default=2000)
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()
    gen = torch.Generator().manual_seed(11)
    res = {"capa": a.capa, "tensor": a.tensor, "g": a.g, "k": a.k, "fuentes": {}}

    for fuente, ruta in (("campeon", CAMPEON), ("bf16", GRANDE)):
        W = matriz(ruta, a.capa, a.tensor)
        filas, cols = W.shape
        ng = cols // a.g
        if fuente == "campeon":
            beta, cierre, _ = escalas(W, a.g)
        else:
            beta = W.reshape(filas, -1).pow(2).mean(1).sqrt()
            cierre = float("nan")
        U = (W / beta[:, None]).reshape(filas * ng, a.g).contiguous()
        sel = torch.randperm(U.shape[0], generator=gen)[:a.n_kmeans]
        print(f"[{fuente}] k-means k={a.k} sobre {a.n_kmeans:,} · {time.time()-t0:.0f}s")
        C1, _ = kmeans_cpu(U[sel].contiguous(), a.k, iters=8, semilla=5)
        print(f"[{fuente}] asignando los {U.shape[0]:,} grupos · {time.time()-t0:.0f}s")
        idx = asignar_todo(U, C1)
        cuenta = torch.bincount(idx, minlength=a.k)
        dos = cuenta.argsort(descending=True)[:2].tolist()
        A = U[idx == dos[0]][:a.tope_cumulo].contiguous()
        B = U[idx == dos[1]][:a.tope_cumulo].contiguous()
        t_a, t_b = int(cuenta[dos[0]]), int(cuenta[dos[1]])
        print(f"[{fuente}] cúmulos {dos} de {t_a} y {t_b} puntos · "
              f"usados {A.shape[0]} y {B.shape[0]}")
        mult, tops, ndif, escala = multiplicidad(A, B)
        res["fuentes"][fuente] = {
            "cumulos": dos, "tam_cumulos": [t_a, t_b],
            "usados": [A.shape[0], B.shape[0]], "diferencias": ndif,
            "multiplicidad_max": mult, "top_por_desplazamiento": tops,
            "escala_rejilla": round(escala, 6),
            "cierre_beta": None if cierre != cierre else round(cierre, 5),
            "segundos": round(time.time() - t0, 1)}
        print(f"[{fuente}] multiplicidad máxima {mult} · top {tops[0]} "
              f"sobre {ndif:,} diferencias · {time.time()-t0:.0f}s\n")
        del W, U

    c, b = res["fuentes"]["campeon"], res["fuentes"]["bf16"]
    res["segundos"] = round(time.time() - t0, 1)
    print(f"CIFRA multiplicidad_max_campeon {c['multiplicidad_max']}")
    print(f"CIFRA multiplicidad_max_control {b['multiplicidad_max']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_traslacion.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
