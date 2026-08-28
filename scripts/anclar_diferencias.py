#!/usr/bin/env python3
"""anclar_diferencias.py — H1: diferencias ANCLADAS en un punto, sin k-means.

POR QUÉ ANCLAR
--------------
C14 midió que las traslaciones existen (242 contra 2 del control). C15 midió que **no
componen**: 120 triángulos cierran a 0,543. La causa no es la hipótesis —C11, C12 y C14 la
sostienen con tres pruebas independientes— sino el punto de partida: con cúmulos del
k-means al 19 % de pureza, cada par elige el desplazamiento entre una pareja de índices
distinta, y `(i_A1,i_B2)` con `(i_B3,i_C1)` no encadenan.

La salida es no relacionar cúmulos entre sí sino referirlo todo a **un solo punto**.
Fijado `u₀ = C1[i₀] + C2[j₀]`, un punto `u ∈ U` da diferencia válida exactamente cuando

  · comparte `i₀` — y entonces `u − u₀` es una diferencia de **C2**, o
  · comparte `j₀` — y entonces `u − u₀` es una diferencia de **C1**.

Ancladas en `u₀` las diferencias son consistentes por construcción. Y la validez se
comprueba sin k-means, contando: `|U ∩ (U + d)|` es grande sólo si `d` es una diferencia
del libro.

LA ARITMÉTICA, ESCRITA ANTES DE MIRAR
--------------------------------------
De cada candidato al azar, la probabilidad de compartir `i₀` o `j₀` es 2/4096. Para un `d`
válido, un punto `u` cualquiera cumple `u + d ∈ U` con probabilidad ≈ (1/4096)·ocupación
≈ 8·10⁻⁵. Para un `d` inválido, `u + d` cae en una celda ocupada con probabilidad ≈3·10⁻¹¹
—la nube ocupa del orden de 12¹⁶ ≈ 2·10¹⁷ celdas—, o sea **cero**. El cribado es limpio.
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


class Rejilla:
    """Pertenencia aproximada por rejilla: clave entera y búsqueda binaria."""

    def __init__(self, U, delta=0.5, semilla=23):
        self.paso = U.abs().median().clamp_min(1e-12) * delta
        gen = torch.Generator().manual_seed(semilla)
        self.peso = torch.randint(1, 2**30, (U.shape[1],), generator=gen, dtype=torch.int64)
        self.claves, _ = self._clave(U).sort()

    def _clave(self, X):
        return (torch.round(X / self.paso).to(torch.int64) * self.peso).sum(1)

    def dentro(self, X):
        c = self._clave(X)
        pos = torch.searchsorted(self.claves, c).clamp(max=self.claves.numel() - 1)
        return self.claves[pos] == c


def probar(rej, U_test, D, lote=64):
    """Aciertos de cada candidato d: cuántos u de la muestra cumplen u+d ∈ U."""
    out = torch.zeros(D.shape[0], dtype=torch.long)
    for a in range(0, D.shape[0], lote):
        b = min(a + lote, D.shape[0])
        X = (U_test[None, :, :] + D[a:b, None, :]).reshape(-1, U_test.shape[1])
        out[a:b] = rej.dentro(X).reshape(b - a, -1).sum(1)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=30)
    p.add_argument("--tensor", default="mlp.gate_proj")
    p.add_argument("--g", type=int, default=16)
    p.add_argument("--candidatos", type=int, default=20000)
    p.add_argument("--criba", type=int, default=20000, help="muestra del cribado")
    p.add_argument("--confirma", type=int, default=400000, help="muestra de confirmación")
    p.add_argument("--umbral", type=int, default=8, help="aciertos para dar por válido")
    p.add_argument("--suelo-empirico", action="store_true",
                   help="«válido» = por encima del percentil 99,9 del CONTROL, no de un "
                        "umbral calculado. Lección de C16: el modelo nulo se mide, no se "
                        "calcula de una densidad idealizada.")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()
    gen = torch.Generator().manual_seed(11)
    res = {"capa": a.capa, "tensor": a.tensor, "candidatos": a.candidatos,
           "criba": a.criba, "confirma": a.confirma, "umbral": a.umbral, "fuentes": {}}

    orden_fuentes = ((("bf16", GRANDE), ("campeon", CAMPEON)) if a.suelo_empirico
                     else (("campeon", CAMPEON), ("bf16", GRANDE)))
    for fuente, ruta in orden_fuentes:
        W = matriz(ruta, a.capa, a.tensor)
        filas, cols = W.shape
        beta = escalas(W, a.g)[0] if fuente == "campeon" else \
            W.reshape(filas, -1).pow(2).mean(1).sqrt()
        U = (W / beta[:, None]).reshape(-1, a.g).contiguous()
        rej = Rejilla(U)
        print(f"[{fuente}] {U.shape[0]:,} grupos · rejilla lista · {time.time()-t0:.0f}s")

        perm = torch.randperm(U.shape[0], generator=gen)
        u0 = U[perm[0]]
        D = U[perm[1:1 + a.candidatos]] - u0
        U_criba = U[perm[a.candidatos + 1:a.candidatos + 1 + a.criba]].contiguous()
        aciertos = probar(rej, U_criba, D)
        pasa = (aciertos >= 1).nonzero().squeeze(1)
        print(f"[{fuente}] cribado: {pasa.numel()} de {a.candidatos} con ≥1 acierto "
              f"· {time.time()-t0:.0f}s")

        U_conf = U[perm[:a.confirma]].contiguous()
        conf = probar(rej, U_conf, D) if a.suelo_empirico else (
            probar(rej, U_conf, D[pasa]) if pasa.numel() else torch.zeros(0, dtype=torch.long))
        if a.suelo_empirico:
            if fuente == "bf16":
                suelo = int(conf.float().quantile(0.999).item())
                res["suelo_empirico"] = suelo
                validos = int((conf > suelo).sum())
            else:
                suelo = res["suelo_empirico"]
                validos = int((conf > suelo).sum())
            print(f"[{fuente}] suelo empírico (p99,9 del control) = {suelo}")
        else:
            validos = int((conf >= a.umbral).sum())
        mejores = sorted(conf.tolist(), reverse=True)[:10] if conf.numel() else []
        res["fuentes"][fuente] = {
            "cribados": int(pasa.numel()), "validos": validos,
            "mediana_aciertos": float(conf.float().median()) if conf.numel() else 0.0,
            "mejores_aciertos": mejores, "segundos": round(time.time() - t0, 1)}
        print(f"[{fuente}] válidos {validos} · mejores {mejores} · {time.time()-t0:.0f}s\n")
        del W, U, rej

    c, b = res["fuentes"]["campeon"], res["fuentes"]["bf16"]
    res["segundos"] = round(time.time() - t0, 1)
    print(f"CIFRA candidatos_validos_campeon {c['validos']}")
    print(f"CIFRA candidatos_validos_control {b['validos']}")
    print(f"CIFRA cribados_campeon {c['cribados']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_anclas.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
