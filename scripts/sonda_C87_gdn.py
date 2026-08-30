#!/usr/bin/env python3
"""Sonda C87: ¿el coste de decodificación por token depende del tamaño del contexto?

Si las 48 capas GatedDeltaNet (estado O(1) por capa) dominan el coste por token
frente a las 16 de atención (cuyo coste SÍ crece con el contexto, por el KV que
recorren), alargar el contexto no debería frenar mucho la decodificación pura.
Se separa prefill de decodificación con el propio callback de streaming —el
primer trozo que llega marca el fin del prefill—, porque `generar()` mide ambos
juntos y llama-cpp-python 0.3.35 no expone perfilado por operación.

Un calentamiento previo evita que la carga del modelo (mmap de 9 GB, ~3-6 s)
contamine la primera medida real.
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai.cerebro.base import Mensaje
from genai.cerebro.local_gguf import CerebroGGUF

N_DECODE = 14


def _relleno(n_palabras: int) -> str:
    random.seed(42)
    palabras = ["gato", "perro", "árbol", "camino", "piedra", "río", "montaña",
               "cielo", "pan", "agua", "fuego", "tierra", "viento", "luz",
               "sombra", "puerta"]
    return " ".join(random.choice(palabras) for _ in range(n_palabras))


def _medir(cerebro: CerebroGGUF, n_palabras_contexto: int) -> tuple[float, float, int]:
    mensajes = [Mensaje("usuario",
                        f"Cuenta hasta veinte. Ignora esto: {_relleno(n_palabras_contexto)}")]
    tiempos: list[float] = []
    cerebro.al_token = lambda _trozo: tiempos.append(time.time())
    t0 = time.time()
    r = cerebro.generar(mensajes, [], max_tokens=N_DECODE, pensar=False)
    total_seg = r.uso.segundos
    n_salida = r.uso.tokens_salida
    if not tiempos or n_salida < 2:
        return total_seg, 0.0, n_salida
    prefill_seg = tiempos[0] - t0
    decode_seg = total_seg - prefill_seg
    tokens_decode = max(1, n_salida - 1)
    tps_decode = tokens_decode / decode_seg if decode_seg > 0 else -1.0
    return prefill_seg, tps_decode, n_salida


def main() -> None:
    print("cargando el cerebro gguf...", file=sys.stderr, flush=True)
    cerebro = CerebroGGUF()

    print("calentamiento (para que el mmap del modelo no contamine la 1a medida)...",
         file=sys.stderr, flush=True)
    _medir(cerebro, 30)
    if hasattr(cerebro, "olvidar"):
        cerebro.olvidar()

    print("midiendo con contexto CORTO (~150 palabras)...", file=sys.stderr, flush=True)
    pre_c, tps_c, n_c = _medir(cerebro, 150)
    print(f"  prefill {pre_c:.2f} s · decode {tps_c:.3f} tok/s · {n_c} tokens generados",
         file=sys.stderr, flush=True)

    if hasattr(cerebro, "olvidar"):
        cerebro.olvidar()

    print("midiendo con contexto LARGO (~550 palabras)...", file=sys.stderr, flush=True)
    pre_l, tps_l, n_l = _medir(cerebro, 550)
    print(f"  prefill {pre_l:.2f} s · decode {tps_l:.3f} tok/s · {n_l} tokens generados",
         file=sys.stderr, flush=True)

    caida_pct = 100.0 * (1 - tps_l / tps_c) if tps_c > 0 else float("nan")

    print(f"CIFRA tps_decode_corto {tps_c:.4f}")
    print(f"CIFRA tps_decode_largo {tps_l:.4f}")
    print(f"CIFRA caida_pct {caida_pct:.2f}")
    print(f"CIFRA prefill_corto_s {pre_c:.2f}")
    print(f"CIFRA prefill_largo_s {pre_l:.2f}")


if __name__ == "__main__":
    main()
