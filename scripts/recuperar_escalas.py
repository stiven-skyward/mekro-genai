#!/usr/bin/env python3
"""recuperar_escalas.py — H1: LEER `β_fila` de los duplicados en vez de estimarla.

EL PUENTE DE DUPLICADOS
-----------------------
El checkpoint deshecho cumple `W[r, grupo] = β_r · (C1[i] + C2[j])`, con `β_r` desconocida
—la puso `reconstruir_v12._EscalaFila`— y sin índices guardados. C1 fracasó por estimar
esa escala como el RMS de la fila, que no lo es.

C11 midió que filas distintas **comparten puntos del retículo**: unos 900.000 pares
duplicados entre los 5,57 M de grupos de una matriz. Ahí está la salida, y no pasa por
estimar nada:

    si (r, i) y (r', j) usan el MISMO punto del retículo,
    entonces  ‖W[r, i]‖ / ‖W[r', j]‖  ES  β_r / β_r' ,  exactamente.

Cada duplicado es un **puente** entre dos filas. Con cientos de miles de puentes y 17.408
filas, el grafo está densamente conectado: un árbol de expansión fija todas las `β` salvo
una constante global, que da igual porque se absorbe en el libro.

CÓMO SE ENCUENTRAN LOS PUENTES SIN COMPARAR TODO CONTRA TODO
------------------------------------------------------------
**Firma de signos**: se proyectan las direcciones sobre `b` hiperplanos aleatorios y se
guarda el signo. Dos direcciones separadas sólo por el redondeo de bf16 distan ~0,006 rad
y comparten la firma de 20 bits con probabilidad 0,96; dos al azar, con 2⁻²⁰. Ordenando
por firma, los duplicados quedan contiguos y basta comparar cada elemento con sus vecinos
en ese orden. De O(n²) a O(n log n).

LA PRUEBA QUE NO SE PUEDE ACOMODAR DESPUÉS: EL CIERRE DE CICLOS
----------------------------------------------------------------
El grafo tiene cientos de miles de aristas y sólo `filas−1` caben en el árbol. **Todas las
demás son redundantes y tienen que cerrar.** Si el modelo es cierto, el cociente que
predice el árbol y el que mide la arista coinciden hasta la precisión de bf16. Son cientos
de miles de comprobaciones independientes de la misma hipótesis, y ninguna se puede
explicar a posteriori: un grafo cuyos ciclos cierran a 0,001 no lo produce un artefacto.

USO
---
  python3 scripts/recuperar_escalas.py --capa 30 --tensor mlp.gate_proj --g 16
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
QUANTMODELS = Path(os.environ.get("MG_QUANTMODELS", "/mnt/e/QuantModels"))
CAMPEON = Path(os.environ.get("MG_CAMPEON_EXT4", "/home/forge/modelos/qwen38-h13b"))


def matriz(ruta: Path, capa: int, tensor: str) -> torch.Tensor:
    if str(QUANTMODELS) not in sys.path:
        sys.path.insert(0, str(QUANTMODELS))
    from quant.carga import DepositoPesos       # type: ignore
    dep = DepositoPesos(ruta)
    return dep.tensores(f"{dep.prefijo_base()}layers.{capa}.{tensor}.",
                        dtype=torch.float32)["weight"]


def firmas(D: torch.Tensor, bits: int, semilla: int) -> torch.Tensor:
    """Firma de signos: `bits` proyecciones aleatorias, empaquetadas en un entero."""
    gen = torch.Generator().manual_seed(semilla)
    R = torch.randn(D.shape[1], bits, generator=gen)
    s = (D @ R > 0).to(torch.int64)
    peso = (1 << torch.arange(bits, dtype=torch.int64))
    return (s * peso).sum(1)


def puentes(D, normas, fila_de, bits, semilla, eps, vecinos):
    """Pares (a, b) de grupos con la MISMA dirección y de filas distintas."""
    f = firmas(D, bits, semilla)
    orden = torch.argsort(f)
    f_ord = f[orden]
    A, B = [], []
    for salto in range(1, vecinos + 1):
        misma = f_ord[:-salto] == f_ord[salto:]
        a, b = orden[:-salto][misma], orden[salto:][misma]
        if a.numel() == 0:
            continue
        ok = fila_de[a] != fila_de[b]
        a, b = a[ok], b[ok]
        d = (D[a] - D[b]).norm(dim=1)
        ok = d < eps
        A.append(a[ok]); B.append(b[ok])
    if not A:
        return torch.zeros(0, dtype=torch.long), torch.zeros(0, dtype=torch.long)
    return torch.cat(A), torch.cat(B)


def arbol_y_cierre(fa, fb, logr, n_filas):
    """Árbol de expansión por union-find → log β. Devuelve (logbeta, alcanzadas,
    residuos de las aristas REDUNDANTES, que son las que prueban el modelo)."""
    padre = list(range(n_filas))

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    ady = [[] for _ in range(n_filas)]
    en_arbol = torch.zeros(fa.numel(), dtype=torch.bool)
    fa_l, fb_l, lr_l = fa.tolist(), fb.tolist(), logr.tolist()
    for k in range(len(fa_l)):
        u, v = fa_l[k], fb_l[k]
        ru, rv = raiz(u), raiz(v)
        if ru != rv:
            padre[ru] = rv
            en_arbol[k] = True
            ady[u].append((v, lr_l[k]))
            ady[v].append((u, -lr_l[k]))

    logbeta = torch.full((n_filas,), float("nan"))
    for s in range(n_filas):
        if not torch.isnan(logbeta[s]):
            continue
        if not ady[s]:
            continue
        logbeta[s] = 0.0
        pila = [s]
        while pila:
            u = pila.pop()
            for v, w in ady[u]:
                if torch.isnan(logbeta[v]):
                    logbeta[v] = logbeta[u] - w     # log β_v = log β_u − log(β_u/β_v)
                    pila.append(v)
    red = ~en_arbol
    ok = red & ~torch.isnan(logbeta[fa]) & ~torch.isnan(logbeta[fb])
    residuo = (logbeta[fa[ok]] - logbeta[fb[ok]] - logr[ok]).abs()
    return logbeta, ady, residuo


def _varios(a, tensores, t0) -> int:
    """Varias matrices en una carrera. La CIFRA es el PEOR cierre, no el mejor:
    una confirmación se defiende por su caso más débil."""
    import subprocess
    filas_res = []
    for t in tensores:
        cmd = [sys.executable, __file__, "--capa", str(a.capa), "--tensor", t,
               "--g", str(a.g), "--bits", str(a.bits), "--eps", str(a.eps),
               "--rondas", str(a.rondas), "--vecinos", str(a.vecinos),
               "--salida", str(Path(a.salida or "registros/x.json").with_name(
                   f"{Path(a.salida).stem if a.salida else 'escalas'}_{t.replace('.', '-')}.json"))]
        print(f"\n=== {t}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-2000:], r.stderr[-2000:])
            raise SystemExit(f"falló {t}")
        cif = {l.split()[1]: float(l.split()[2]) for l in r.stdout.splitlines()
               if l.startswith("CIFRA ")}
        cif["tensor"] = t
        filas_res.append(cif)
        print(f"    cierre {cif['cierre_mediano']} · control {cif['cierre_mediano_control']}"
              f" · filas {cif['frac_filas_conectadas']} · puentes {int(cif['puentes']):,}")
    peor = max(filas_res, key=lambda d: d["cierre_mediano"])
    mejor_ctrl = min(filas_res, key=lambda d: d["cierre_mediano_control"])
    res = {"capa": a.capa, "tensores": tensores, "por_tensor": filas_res,
           "peor_tensor": peor["tensor"], "segundos": round(time.time() - t0, 1)}
    print(f"\nPEOR caso: {peor['tensor']}")
    print(f"CIFRA cierre_mediano {peor['cierre_mediano']}")
    print(f"CIFRA cierre_mediano_control {mejor_ctrl['cierre_mediano_control']}")
    print(f"CIFRA frac_filas_conectadas {min(d['frac_filas_conectadas'] for d in filas_res)}")
    print(f"CIFRA puentes {int(min(d['puentes'] for d in filas_res))}")
    if a.salida:
        Path(a.salida).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nregistro: {a.salida}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--capa", type=int, default=30)
    p.add_argument("--tensor", default="mlp.gate_proj",
                   help="uno, o varios separados por comas: la CIFRA es el PEOR caso")
    p.add_argument("--g", type=int, default=16)
    p.add_argument("--bits", type=int, default=20)
    p.add_argument("--vecinos", type=int, default=4, help="saltos en el orden por firma")
    p.add_argument("--rondas", type=int, default=3, help="firmas independientes")
    p.add_argument("--eps", type=float, default=0.02)
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--salida", default="")
    a = p.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    t0 = time.time()

    tensores = [t.strip() for t in a.tensor.split(",")]
    if len(tensores) > 1:
        return _varios(a, tensores, t0)
    W = matriz(CAMPEON, a.capa, a.tensor)
    filas, cols = W.shape
    ng = cols // a.g
    V = W.reshape(filas * ng, a.g)
    normas = V.norm(dim=1)
    vivo = normas > 0
    idx_vivo = vivo.nonzero().squeeze(1)
    D = V[idx_vivo] / normas[idx_vivo, None]
    fila_de = idx_vivo // ng
    print(f"capa {a.capa} · {a.tensor} · {filas}x{cols} · g={a.g} · "
          f"{V.shape[0]:,} grupos ({int((~vivo).sum())} nulos) · {time.time()-t0:.0f}s")

    A, B = [], []
    for r in range(a.rondas):
        x, y = puentes(D, normas, fila_de, a.bits, 100 + r, a.eps, a.vecinos)
        A.append(x); B.append(y)
        print(f"  ronda {r+1}: {x.numel():,} puentes · {time.time()-t0:.0f}s")
    A, B = torch.cat(A), torch.cat(B)
    # deduplicar aristas idénticas de rondas distintas
    clave = torch.minimum(A, B) * V.shape[0] + torch.maximum(A, B)
    _, unico = torch.unique(clave, return_inverse=False, return_counts=False), None
    orden = torch.argsort(clave)
    keep = torch.ones(clave.numel(), dtype=torch.bool)
    keep[1:] = clave[orden][1:] != clave[orden][:-1]
    sel = orden[keep]
    A, B = A[sel], B[sel]
    print(f"  puentes únicos: {A.numel():,}")

    na, nb = normas[idx_vivo[A]], normas[idx_vivo[B]]
    logr = (na.log() - nb.log())                     # log(β_a / β_b)
    fa, fb = fila_de[A], fila_de[B]
    logbeta, ady, residuo = arbol_y_cierre(fa, fb, logr, filas)

    conectadas = int((~torch.isnan(logbeta)).sum())
    res = {"capa": a.capa, "tensor": a.tensor, "g": a.g, "forma": [filas, cols],
           "grupos": int(V.shape[0]), "puentes": int(A.numel()),
           "aristas_redundantes": int(residuo.numel()),
           "filas": filas, "filas_conectadas": conectadas,
           "frac_filas_conectadas": round(conectadas / filas, 4),
           "cierre_mediano": round(float(residuo.median()) if residuo.numel() else 9.9, 6),
           "cierre_p90": round(float(residuo.quantile(0.9)) if residuo.numel() else 9.9, 6),
           "cierre_p99": round(float(residuo.quantile(0.99)) if residuo.numel() else 9.9, 6),
           "beta_min": round(float(logbeta[~torch.isnan(logbeta)].exp().min()), 6),
           "beta_max": round(float(logbeta[~torch.isnan(logbeta)].exp().max()), 6),
           "segundos": round(time.time() - t0, 1)}

    # control: las mismas aristas con las normas BARAJADAS. Si el cierre no se destruye,
    # el número no mide nada. Es el control que le faltó a C1.
    gen = torch.Generator().manual_seed(3)
    perm = torch.randperm(logr.numel(), generator=gen)
    _, _, res_ctrl = arbol_y_cierre(fa, fb, logr[perm], filas)
    res["cierre_mediano_control"] = round(float(res_ctrl.median()) if res_ctrl.numel() else 9.9, 6)

    print(json.dumps({k: v for k, v in res.items() if k != "forma"}, indent=2, ensure_ascii=False))
    print(f"CIFRA cierre_mediano {res['cierre_mediano']}")
    print(f"CIFRA cierre_mediano_control {res['cierre_mediano_control']}")
    print(f"CIFRA frac_filas_conectadas {res['frac_filas_conectadas']}")
    print(f"CIFRA puentes {res['puentes']}")

    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_escalas.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"logbeta": logbeta, "capa": a.capa, "tensor": a.tensor, "g": a.g},
               destino.with_suffix(".pt"))
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino} · escalas: {destino.with_suffix('.pt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
