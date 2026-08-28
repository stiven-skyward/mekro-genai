#!/usr/bin/env python3
"""sondear_ventana.py — la sonda de C26: ¿qué cuesta doblar la ventana a 16.384?

Dos cargas del GGUF (mmap, ~un minuto) leyendo lo que el propio llama.cpp imprime al
reservar sus buffers, más el RSS real del proceso. Nada de aritmética de papel: la cifra
es la reserva que hace el motor.

    CIFRA kv_gb <GB de buffers de memoria/KV a n_ctx=16384>   — la que decide
    CIFRA rss_gb <RSS del proceso a 16384>
"""
from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stderr

from llama_cpp import Llama

GGUF = "/home/forge/modelos/gguf/Qwen3.8-27B-UD-Q2_K_XL.gguf"


def rss_gb() -> float:
    with open("/proc/self/status") as f:
        for linea in f:
            if linea.startswith("VmRSS:"):
                return int(linea.split()[1]) / 1024 / 1024
    return 0.0


def medir(n_ctx: int) -> float:
    """Carga con esa ventana y suma los buffers de memoria que el motor declara."""
    parlanchin = io.StringIO()
    with redirect_stderr(parlanchin):
        llm = Llama(model_path=GGUF, n_ctx=n_ctx, n_threads=8, n_gpu_layers=0,
                    seed=0, verbose=True)
    dicho = parlanchin.getvalue()
    del llm
    mib = 0.0
    for linea in dicho.splitlines():
        # cubre «KV buffer size», «memory buffer size» y variantes por tipo de caché
        m = re.search(r"(KV|memory|recurrent|kv).*buffer size\s*=?\s*([\d.]+)\s*MiB",
                      linea, re.IGNORECASE)
        if m:
            mib += float(m.group(2))
            print(f"   [{n_ctx}] {linea.strip()}")
    return mib / 1024


def main() -> int:
    print("── carga a 8192 (la ventana de hoy)")
    kv8 = medir(8192)
    print(f"   buffers de memoria: {kv8:.2f} GB")

    print("── carga a 16384 (la doblada)")
    kv16 = medir(16384)
    r16 = rss_gb()
    print(f"   buffers de memoria: {kv16:.2f} GB · RSS {r16:.1f} GB")

    print(f"\nCIFRA kv_gb {kv16:.2f}")
    print(f"CIFRA rss_gb {r16:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
