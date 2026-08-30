#!/usr/bin/env python3
"""Medición C87: la carrera de verdad, no la sonda barata.

La sonda (2 puntos, 3,5x de rango) confirmó que decode tok/s no cae con el
contexto. Esto repite la idea con MÁS puntos y MÁS rango (10x, no 3,5x) para
que la tendencia se vea, no solo dos extremos, y de paso mide el ancho de
banda de prefill en cada punto —el hallazgo lateral de la sonda (prefill casi
tan lento como decode) merece su propia cifra, no quedarse en anécdota.
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai.cerebro.base import Mensaje
from genai.cerebro.local_gguf import CerebroGGUF

N_DECODE = 20
PUNTOS_PALABRAS = [150, 400, 800, 1600]


def _relleno(n_palabras: int) -> str:
    random.seed(42)
    palabras = ["gato", "perro", "árbol", "camino", "piedra", "río", "montaña",
               "cielo", "pan", "agua", "fuego", "tierra", "viento", "luz",
               "sombra", "puerta"]
    return " ".join(random.choice(palabras) for _ in range(n_palabras))


def _medir(cerebro: CerebroGGUF, n_palabras_contexto: int) -> dict:
    mensajes = [Mensaje("usuario",
                        f"Cuenta hasta veinte. Ignora esto: {_relleno(n_palabras_contexto)}")]
    tiempos: list[float] = []
    cerebro.al_token = lambda _trozo: tiempos.append(time.time())
    t0 = time.time()
    r = cerebro.generar(mensajes, [], max_tokens=N_DECODE, pensar=False)
    total_seg = r.uso.segundos
    n_entrada = r.uso.tokens_entrada
    n_salida = r.uso.tokens_salida
    prefill_seg = (tiempos[0] - t0) if tiempos else total_seg
    decode_seg = total_seg - prefill_seg
    tokens_decode = max(1, n_salida - 1)
    tps_decode = tokens_decode / decode_seg if decode_seg > 0 else -1.0
    tps_prefill = n_entrada / prefill_seg if prefill_seg > 0 else -1.0
    return {"n_entrada": n_entrada, "prefill_seg": prefill_seg,
           "tps_decode": tps_decode, "tps_prefill": tps_prefill}


def main() -> None:
    print("cargando el cerebro gguf...", file=sys.stderr, flush=True)
    cerebro = CerebroGGUF()

    print("calentamiento...", file=sys.stderr, flush=True)
    _medir(cerebro, 30)
    if hasattr(cerebro, "olvidar"):
        cerebro.olvidar()

    filas = []
    for n_palabras in PUNTOS_PALABRAS:
        print(f"midiendo con ~{n_palabras} palabras de contexto...",
             file=sys.stderr, flush=True)
        d = _medir(cerebro, n_palabras)
        filas.append(d)
        print(f"  {d['n_entrada']} tok entrada · prefill {d['prefill_seg']:.1f} s "
             f"({d['tps_prefill']:.2f} tok/s) · decode {d['tps_decode']:.3f} tok/s",
             file=sys.stderr, flush=True)
        if hasattr(cerebro, "olvidar"):
            cerebro.olvidar()

    for i, (n_pal, d) in enumerate(zip(PUNTOS_PALABRAS, filas)):
        print(f"CIFRA entrada_tok_p{i} {d['n_entrada']}")
        print(f"CIFRA tps_decode_p{i} {d['tps_decode']:.4f}")
        print(f"CIFRA tps_prefill_p{i} {d['tps_prefill']:.4f}")

    tps_c, tps_l = filas[0]["tps_decode"], filas[-1]["tps_decode"]
    caida_pct = 100.0 * (1 - tps_l / tps_c) if tps_c > 0 else float("nan")
    print(f"CIFRA caida_pct {caida_pct:.2f}")

    # pendiente de tok/s de decodificación frente a tokens de entrada (regresión
    # simple): si es ~0, decode es independiente del contexto en todo el rango,
    # no solo en los dos extremos.
    xs = [d["n_entrada"] for d in filas]
    ys = [d["tps_decode"] for d in filas]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    pendiente = num / den
    print(f"CIFRA pendiente_tps_por_tok {pendiente:.6f}")

    # tendencia del ancho de banda de prefill: ¿decae con el contexto o se mantiene?
    tps_prefill_p0 = filas[0]["tps_prefill"]
    tps_prefill_pN = filas[-1]["tps_prefill"]
    caida_prefill_pct = (100.0 * (1 - tps_prefill_pN / tps_prefill_p0)
                        if tps_prefill_p0 > 0 else float("nan"))
    print(f"CIFRA caida_prefill_pct {caida_prefill_pct:.2f}")


if __name__ == "__main__":
    main()
