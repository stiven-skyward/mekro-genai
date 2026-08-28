#!/usr/bin/env python3
"""sondear_direcciones.py — H1: ¿sigue el retículo C1+C2 en los pesos deshechos?

POR QUÉ ESTA SONDA Y NO LA DE C1
---------------------------------
C1 preguntó lo mismo y salió refutado, pero el fallo fue de la sonda: estimaba `α` como
el RMS de la fila, y el RMS **no es** el factor que aplicó `reconstruir_v12._EscalaFila`.
Con una `α` equivocada, ningún retículo se recupera aunque esté intacto.

Aquí la incógnita desaparece del problema en vez de estimarse. Si el peso guardado es

    W[fila, grupo] = β_fila · (C1[i] + C2[j])

entonces **la dirección** del vector de 16 (dividido por su norma) no depende de `β_fila`
en absoluto. Una escala por fila no mueve direcciones. Así que se normaliza cada grupo a
norma unidad y se mira si las direcciones caen en unos pocos miles de cúmulos apretados
—que es lo que pasaría si el retículo sigue ahí— o si forman una nube.

Y hay una consecuencia que conviene tener escrita antes de leer el número: si el afinado
(`afinar: 60` en HERMETIC2.json) movió pesos sueltos en vez de mover solo los libros,
el retículo está roto y esto lo dirá; si movió solo los libros, el retículo sigue, con
otros códigos.

LOS DOS CONTROLES, QUE SON LO QUE LE FALTÓ A C1
-----------------------------------------------
Un número solo no dice nada: `razon_residuo 0,543` pareció estructura y era exactamente
lo que da cualquier nube. Aquí se mide lo mismo sobre tres matrices:

  · **campeón**: la matriz deshecha, la que se investiga.
  · **BF16**: la MISMA matriz del modelo sin cuantizar. Es el control real —misma
    estadística de pesos, mismo tamaño, sin retículo—, y es el que decide.
  · **gaussiana**: ruido de la misma forma. Marca el suelo.

La cifra del veredicto es el COCIENTE campeón/BF16, no el valor absoluto.

USO
---
  python3 scripts/sondear_direcciones.py --capa 30 --tensor mlp.up_proj --g 16
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
QUANTMODELS = Path(os.environ.get("MG_QUANTMODELS", "/mnt/e/QuantModels"))
CAMPEON = Path(os.environ.get("MG_CAMPEON_EXT4", "/home/forge/modelos/qwen38-h13b"))
GRANDE = Path(os.environ.get("MG_BF16", "/home/forge/modelos/qwen3.8-27b"))

from sondear_estructura import kmeans_cpu       # noqa: E402


def _matriz(ruta: Path, capa: int, tensor: str) -> torch.Tensor:
    if str(QUANTMODELS) not in sys.path:
        sys.path.insert(0, str(QUANTMODELS))
    from quant.carga import DepositoPesos       # type: ignore
    dep = DepositoPesos(ruta)
    nombre = f"{dep.prefijo_base()}layers.{capa}.{tensor}."
    return dep.tensores(nombre, dtype=torch.float32)["weight"]


def direcciones(W: torch.Tensor, g: int, n: int, semilla: int) -> torch.Tensor:
    """Grupos de `g` columnas contiguas → muestra de `n` → norma unidad."""
    filas, cols = W.shape
    if cols % g:
        raise SystemExit(f"{cols} columnas no es múltiplo de g={g}")
    V = W.reshape(filas * (cols // g), g)
    gen = torch.Generator().manual_seed(semilla)
    sel = torch.randperm(V.shape[0], generator=gen)[:n]
    V = V[sel]
    norma = V.norm(dim=1, keepdim=True)
    V = V[norma.squeeze(1) > 0]
    return V / V.norm(dim=1, keepdim=True)


def vecino_mas_cercano(D: torch.Tensor, trozo: int = 512) -> torch.Tensor:
    """Distancia de cada dirección a la más cercana DISTINTA de la muestra."""
    n = D.shape[0]
    fuera = torch.empty(n)
    for a in range(0, n, trozo):
        b = min(a + trozo, n)
        d = torch.cdist(D[a:b], D)
        d[torch.arange(b - a), torch.arange(a, b)] = float("inf")
        fuera[a:b] = d.min(1).values
    return fuera


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=30)
    p.add_argument("--tensor", default="mlp.up_proj")
    p.add_argument("--g", type=int, default=16, help="16 salvo capas 0-3 y 58-63 (g=8)")
    p.add_argument("--n", type=int, default=40000, help="grupos muestreados")
    p.add_argument("--eps", type=float, default=0.02, help="qué es «coincidir»")
    p.add_argument("--k", type=int, default=4096)
    p.add_argument("--kmeans", action="store_true", help="además, k-means sobre direcciones")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--barrido", default="",
                   help="lista de n separados por comas: estima |D| por la ley del cumpleaños")
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()

    Wc = _matriz(CAMPEON, a.capa, a.tensor)
    Wb = _matriz(GRANDE, a.capa, a.tensor)
    if Wc.shape != Wb.shape:
        raise SystemExit(f"formas distintas: campeón {tuple(Wc.shape)} vs BF16 {tuple(Wb.shape)}")
    print(f"capa {a.capa} · {a.tensor} · {tuple(Wc.shape)} · g={a.g} · "
          f"{Wc.shape[0] * Wc.shape[1] // a.g} grupos, muestra {a.n}")

    gen = torch.Generator().manual_seed(7)
    fuentes = {
        "campeon": direcciones(Wc, a.g, a.n, 1),
        "bf16": direcciones(Wb, a.g, a.n, 1),
        "gaussiana": direcciones(torch.randn(Wc.shape, generator=gen), a.g, a.n, 1),
    }
    res = {"capa": a.capa, "tensor": a.tensor, "g": a.g, "n": a.n, "eps": a.eps,
           "forma": list(Wc.shape), "por_fuente": {}}
    for nombre, D in fuentes.items():
        nn = vecino_mas_cercano(D)
        d = {"vecino_mediano": round(nn.median().item(), 5),
             "vecino_p01": round(nn.quantile(0.01).item(), 5),
             "frac_cerca": round((nn < a.eps).float().mean().item(), 6)}
        if a.kmeans:
            C, idx = kmeans_cpu(D, a.k, iters=10)
            r = (D - C[idx]).norm(dim=1).mean() / D.norm(dim=1).mean()
            d["razon_residuo_kmeans"] = round(r.item(), 4)
            d["codigos_usados"] = int(torch.bincount(idx, minlength=a.k).gt(0).sum())
        res["por_fuente"][nombre] = d
        print(f"  {nombre:10s} " + json.dumps(d, ensure_ascii=False))

    # ── la ley del cumpleaños: si las direcciones salen de un libro FINITO de |D|
    # entradas equiprobables, la fracción de puntos con vecino coincidente crece
    # LINEALMENTE con n y vale n/|D|. Es la única prueba que puede matar la hipótesis:
    # una nube continua no crece, y un artefacto no da el mismo |D| a cada n.
    if a.barrido:
        res["barrido"] = []
        for nn_ in [int(x) for x in a.barrido.split(",")]:
            fila = {"n": nn_}
            for nombre, W in (("campeon", Wc), ("bf16", Wb)):
                D = direcciones(W, a.g, nn_, 1)
                f = (vecino_mas_cercano(D) < a.eps).float().mean().item()
                fila[nombre] = round(f, 6)
                if nombre == "campeon":
                    fila["libro_estimado"] = round(nn_ / f) if f > 0 else None
            res["barrido"].append(fila)
            print(f"  n={nn_:7d} campeón {fila['campeon']:.6f} · bf16 {fila['bf16']:.6f} "
                  f"· |D| estimado {fila['libro_estimado']:,}" if fila["libro_estimado"]
                  else f"  n={nn_:7d} sin coincidencias")
        est = [f["libro_estimado"] for f in res["barrido"] if f["libro_estimado"]]
        res["libro_estimado_mediano"] = int(sorted(est)[len(est) // 2]) if est else 0
        res["razon_libro_vs_k1k2"] = round(res["libro_estimado_mediano"] / (4096 * 4096), 4)
        print(f"\nCIFRA libro_estimado {res['libro_estimado_mediano']}")
        print(f"CIFRA razon_libro_vs_k1k2 {res['razon_libro_vs_k1k2']}")

    c, b = res["por_fuente"]["campeon"], res["por_fuente"]["bf16"]
    razon = c["frac_cerca"] / b["frac_cerca"] if b["frac_cerca"] > 0 else float("inf")
    res["razon_vecinos_vs_bf16"] = round(razon, 3) if razon != float("inf") else 1e9
    res["segundos"] = round(time.time() - t0, 1)
    print()
    print(f"CIFRA razon_vecinos_vs_bf16 {res['razon_vecinos_vs_bf16']}")
    print(f"CIFRA frac_cerca_campeon {c['frac_cerca']}")
    print(f"CIFRA frac_cerca_bf16 {b['frac_cerca']}")
    print(f"CIFRA vecino_mediano_campeon {c['vecino_mediano']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_direcciones.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
