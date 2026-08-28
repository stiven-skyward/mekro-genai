#!/usr/bin/env python3
"""medir_computo.py — ¿cuánto cómputo sobra cuando el cuello de botella es mover bytes?

LA PREGUNTA
-----------
Decodificar un token con pesos densos es una operación de **intensidad aritmética
ridícula**: por cada peso leído se hace una multiplicación y una suma. El hardware está
diseñado para lo contrario. Consecuencia: al decodificar de uno en uno, la CPU pasa casi
todo el tiempo esperando memoria.

Si eso es cierto, procesar 8 tokens a la vez debería costar **casi lo mismo** que procesar
uno: los pesos se leen una sola vez y se reutilizan ocho. Y si es casi gratis, entonces la
**decodificación especulativa** —que verifica K tokens candidatos en un solo pase— es la
palanca central de la vía densa. Es además rigurosamente **sin pérdida**: el algoritmo de
muestreo especulativo produce exactamente la distribución del modelo grande.

Esta medida es el sí o el no de esa tesis, y cuesta un minuto.

QUÉ IMPRIME
-----------
    CIFRA razon_8_vs_1   t(lote 8) / t(lote 1) sobre una matriz real del modelo.
                         ≈1 → verificar 8 tokens es gratis. ≫1 → la tesis se cae.
    CIFRA gbs_efectivo   ancho de banda que se logra sobre pesos ya residentes.
    CIFRA gflops_lote32  cómputo real alcanzado, para saber cuándo deja de haber sitio.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import torch


def cronometrar(f, repes: int = 8) -> float:
    f(); f()
    t0 = time.time()
    for _ in range(repes):
        f()
    return (time.time() - t0) / repes


def _capas_reales(dir_modelo: Path, capas: list[int]) -> list[tuple[str, "torch.Tensor"]]:
    """Los pesos de verdad de unas capas concretas, no una matriz aleatoria.

    Importa porque Qwen3.8 es híbrido: 48 capas GatedDeltaNet y 16 de atención (3, 7, …,
    63), con formas muy distintas. Medir solo sobre la MLP —que es la matriz más grande y
    la más favorable— daría una razón lote-8/lote-1 mejor que la real.
    """
    import json
    from safetensors import safe_open

    indice = json.loads((dir_modelo / "model.safetensors.index.json").read_text())["weight_map"]
    quiero = {n: f for n, f in indice.items()
              if any(f".layers.{c}." in n for c in capas) and n.endswith(".weight")}
    por_fichero: dict[str, list[str]] = {}
    for n, f in quiero.items():
        por_fichero.setdefault(f, []).append(n)
    fuera = []
    for f, nombres in por_fichero.items():
        with safe_open(dir_modelo / f, framework="pt") as fh:
            for n in nombres:
                w = fh.get_tensor(n)
                if w.dim() == 2 and min(w.shape) > 64:      # matrices, no normas ni sesgos
                    fuera.append((n.split(".layers.")[-1], w))
    return sorted(fuera, key=lambda x: -x[1].numel())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--salida", type=int, default=17408, help="dim de salida (mlp up/gate)")
    p.add_argument("--entrada", type=int, default=5120, help="hidden de Qwen3.8")
    p.add_argument("--dtype", default="bfloat16")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--params-modelo", type=float, default=27.8e9)
    p.add_argument("--desde-modelo", default="",
                   help="directorio del modelo real: mide sobre sus matrices, no una aleatoria")
    p.add_argument("--capas", default="30,31", help="una deltanet y una de atención")
    p.add_argument("--n-capas", type=int, default=64)
    a = p.parse_args()

    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    dt = getattr(torch, a.dtype)

    if a.desde_modelo:
        return _medir_modelo_real(Path(a.desde_modelo),
                                  [int(c) for c in a.capas.split(",")],
                                  a.n_capas, a.params_modelo)

    W = torch.randn(a.salida, a.entrada, dtype=dt)
    bytes_W = W.numel() * W.element_size()
    print(f"W {tuple(W.shape)} {a.dtype} = {bytes_W / 1e6:.0f} MB · "
          f"{torch.get_num_threads()} hilos\n")

    print("  lote   ms/pase   ms/token   GB/s efectivo   GFLOP/s")
    tiempos = {}
    for B in (1, 2, 4, 8, 16, 32, 64):
        x = torch.randn(a.entrada, B, dtype=dt)
        t = cronometrar(lambda: torch.mm(W, x))
        tiempos[B] = t
        flops = 2 * W.numel() * B
        print(f"  {B:4d}   {t * 1e3:7.2f}   {t * 1e3 / B:8.2f}   "
              f"{bytes_W / 1e9 / t:13.1f}   {flops / 1e9 / t:7.0f}")

    razon = tiempos[8] / tiempos[1]
    gbs = bytes_W / 1e9 / tiempos[1]
    gflops32 = 2 * W.numel() * 32 / 1e9 / tiempos[32]

    # Extrapolación al modelo entero, con los pesos ya en memoria.
    bytes_modelo = a.params_modelo * W.element_size()
    seg_1 = bytes_modelo / (gbs * 1e9)
    seg_8 = seg_1 * razon
    print(f"\n  extrapolado al modelo completo ({bytes_modelo / 1e9:.0f} GB residentes):")
    print(f"    1 token por pase   {seg_1:5.2f} s/token")
    print(f"    8 tokens por pase  {seg_8 / 8:5.2f} s/token  (si se aceptan los 8)")

    print()
    print(f"CIFRA razon_8_vs_1 {razon:.4f}")
    print(f"CIFRA gbs_efectivo {gbs:.3f}")
    print(f"CIFRA gflops_lote32 {gflops32:.1f}")
    return 0


def _medir_modelo_real(dir_modelo: Path, capas: list[int], n_capas: int,
                       params: float) -> int:
    pesos = _capas_reales(dir_modelo, capas)
    if not pesos:
        raise SystemExit(f"no se encontraron matrices de las capas {capas} en {dir_modelo}")
    bytes_capas = sum(w.numel() * w.element_size() for _, w in pesos)
    print(f"{len(pesos)} matrices reales de las capas {capas} · "
          f"{bytes_capas / 1e9:.2f} GB · {torch.get_num_threads()} hilos\n")
    for nombre, w in pesos[:8]:
        print(f"    {nombre:44s} {tuple(w.shape)}")

    print(f"\n  lote   ms/pase   ms/token   GB/s efectivo")
    tiempos = {}
    for B in (1, 2, 4, 8, 16, 32):
        entradas = [torch.randn(w.shape[1], B, dtype=w.dtype) for _, w in pesos]
        def pase():
            for (_, w), x in zip(pesos, entradas):
                torch.mm(w, x)
        t = cronometrar(pase, repes=4)
        tiempos[B] = t
        print(f"  {B:4d}   {t * 1e3:7.1f}   {t * 1e3 / B:8.2f}   "
              f"{bytes_capas / 1e9 / t:13.1f}")

    razon = tiempos[8] / tiempos[1]
    gbs = bytes_capas / 1e9 / tiempos[1]
    # De las capas medidas al modelo entero: se escala por número de capas, que es lo que
    # se puede defender. Extrapolar por parámetros mezclaría embed y lm_head, que no son
    # capas y no se comportan igual.
    factor = n_capas / len(capas)
    seg_1 = tiempos[1] * factor
    print(f"\n  extrapolado a {n_capas} capas (×{factor:.0f}), pesos residentes:")
    print(f"    1 token por pase    {seg_1:5.2f} s/token   ({1 / seg_1:.2f} tok/s)")
    for k in (4, 8, 16):
        s = tiempos[k] * factor / k
        print(f"    {k:2d} tokens por pase  {s:5.2f} s/token   ({1 / s:.2f} tok/s) "
              f"si se aceptan los {k}")

    print()
    print(f"CIFRA razon_8_vs_1 {razon:.4f}")
    print(f"CIFRA gbs_efectivo {gbs:.3f}")
    print(f"CIFRA seg_token_lote1 {seg_1:.4f}")
    print(f"CIFRA seg_token_lote8 {tiempos[8] * factor / 8:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
