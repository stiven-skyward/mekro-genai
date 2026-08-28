#!/usr/bin/env python3
"""medir_ancho_banda.py — el techo físico de la vía densa, medido y reproducible.

Correr un modelo de 52 GB en una máquina de 30 GB es, ante todo, un problema de **mover
bytes**. Cada token de decodificación exige leer TODOS los pesos. Así que la velocidad
máxima alcanzable no depende del modelo ni del código: depende de tres anchos de banda,
y conviene saberlos antes de diseñar nada encima.

    t_token ≥ (bytes que hay que leer) / (ancho de banda de donde estén)

Mide: 9p (`/mnt/e`), NVMe en ext4 con O_DIRECT y varias profundidades de cola, y RAM.

    python3 scripts/medir_ancho_banda.py --ext4 /home/forge/bench/grande.bin
"""
from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

import torch

BLOQUE = 16 * 1024 * 1024


def leer_directo(fichero: Path, hilos: int) -> float:
    """GB/s con O_DIRECT y `hilos` lectores. O_DIRECT esquiva la caché de página: mide
    el dispositivo, no la RAM. Los offsets van alineados al bloque o `dd` da EINVAL —y
    un `dd` que falla al instante parece rapidísimo."""
    tot = (fichero.stat().st_size // BLOQUE) * BLOQUE
    c = (tot // BLOQUE // hilos) * BLOQUE
    ps, t0 = [], time.time()
    for i in range(hilos):
        ps.append(subprocess.Popen(
            ["dd", f"if={fichero}", "of=/dev/null", "bs=16M",
             "iflag=direct,skip_bytes,count_bytes", f"skip={i * c}", f"count={c}"],
            stderr=subprocess.DEVNULL))
    codigos = {p.wait() for p in ps}
    dt = time.time() - t0
    if codigos != {0}:
        raise SystemExit(f"algún dd falló (códigos {codigos}): la medida no vale")
    return c * hilos / 1e9 / dt


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--nueve-p", default="/mnt/e/QuantModels/modelos/qwen3.8-27b/"
                                        "model-00001-of-00018.safetensors")
    p.add_argument("--ext4", default="/home/forge/bench/grande.bin",
                   help="fichero grande en ext4 (debe superar la RAM del anfitrión)")
    p.add_argument("--modelo-gb", type=float, default=52.0)
    a = p.parse_args()

    print("== anchos de banda ==")

    n9 = Path(a.nueve_p)
    if n9.exists():
        gb9 = leer_directo(n9, 1)
        print(f"  9p /mnt/e            {gb9:6.2f} GB/s")
    else:
        gb9 = float("nan")
        print("  9p /mnt/e            (no encontrado)")

    ext4 = Path(a.ext4)
    mejor = float("nan")
    if ext4.exists():
        for h in (1, 2, 4, 8):
            v = leer_directo(ext4, h)
            mejor = v if v != v or (mejor != mejor or v > mejor) else mejor
            print(f"  NVMe ext4 · {h} hilos {v:6.2f} GB/s")
    else:
        print(f"  NVMe ext4            (falta {ext4}; créalo con cat de varios shards)")

    torch.set_num_threads(os.cpu_count() or 8)
    n = 2_000_000_000 // 4
    x = torch.ones(n, dtype=torch.float32)
    y = torch.empty_like(x)
    float(x.sum()); t0 = time.time()
    for _ in range(5):
        float(x.sum())
    ram_lect = n * 4 / 1e9 / ((time.time() - t0) / 5)
    y.copy_(x); t0 = time.time()
    for _ in range(5):
        y.copy_(x)
    ram_copia = n * 8 / 1e9 / ((time.time() - t0) / 5)
    print(f"  RAM lectura          {ram_lect:6.2f} GB/s")
    print(f"  RAM copia            {ram_copia:6.2f} GB/s")

    print()
    print(f"CIFRA gbs_9p {gb9:.3f}")
    print(f"CIFRA gbs_nvme {mejor:.3f}")
    print(f"CIFRA gbs_ram {ram_lect:.3f}")
    if mejor == mejor:
        print(f"CIFRA seg_por_pase_nvme {a.modelo_gb / mejor:.3f}")
        print()
        print(f"── un pase por los {a.modelo_gb:.0f} GB del modelo: "
              f"{a.modelo_gb / gb9:.0f} s desde 9p · {a.modelo_gb / mejor:.1f} s desde NVMe "
              f"· {a.modelo_gb / ram_lect:.1f} s desde RAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
