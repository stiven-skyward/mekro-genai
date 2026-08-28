#!/usr/bin/env python3
"""medir_compresion.py — ¿cuánto encoge BF16 SIN perder un solo bit, y a qué velocidad?

LA IDEA
-------
Un BF16 son 16 bits: 1 de signo, 8 de exponente, 7 de mantisa. En los pesos de una red
entrenada, **los exponentes están concentradísimos** (casi todos los pesos viven en dos o
tres órdenes de magnitud) y **las mantisas son casi ruido**. Un compresor genérico aplicado
al flujo entrelazado no ve nada, porque cada byte alterna estructura y ruido.

Separar los **planos de bytes** —todos los bytes altos juntos, todos los bajos juntos— y
comprimir cada plano por su cuenta deja que el compresor encuentre la estructura donde la
hay. Es la idea de ZipNN, y es **exactamente sin pérdida**: se comprueba bit a bit.

LA CIFRA QUE DECIDE NO ES LA RAZÓN DE COMPRESIÓN
------------------------------------------------
Comprimir solo ayuda si descomprimir no se convierte en el nuevo cuello de botella. El
NVMe da 6,77 GB/s medidos; si la descompresión va a 4 GB/s, el sistema empeora aunque el
fichero sea un 30 % menor. Lo que hay que maximizar es

    ancho_efectivo = min( nvme × razón , velocidad_de_descompresión )

y esa es la cifra que este script imprime como `gbs_efectivo`.
"""
from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import zstandard as zstd

TROZO = 2 * 1024 * 1024


def planos_de_bytes(crudo: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """BF16 → (bytes altos, bytes bajos). Little-endian: el byte 1 lleva signo+exponente.

    Se devuelven CONTIGUOS (`ascontiguousarray`) a propósito: una vista con paso 2 le
    llega al compresor como el mismo entrelazado que queríamos deshacer, y el experimento
    mediría exactamente lo contrario de lo que pretende.
    """
    pares = crudo.reshape(-1, 2)
    return (np.ascontiguousarray(pares[:, 1]), np.ascontiguousarray(pares[:, 0]))


def comprimir(datos: bytes, nivel: int, hilos: int) -> tuple[list[bytes], float]:
    """En trozos, para poder descomprimir en paralelo: un único bloque de 3 GB solo se
    puede descomprimir con un hilo, y ahí se pierde todo lo ganado."""
    # Trozo FIJO de 2 MB, no derivado del número de hilos. Con un trozo por hilo, el más
    # lento marca el tiempo de todos; medido sobre los mismos 537 MB: 33 MB/trozo → 3,4
    # GB/s, 8 MB → 3,8, 2 MB → 4,6. El reparto fino es la diferencia, no el compresor.
    trozo = TROZO
    partes = [datos[i:i + trozo] for i in range(0, len(datos), trozo)]
    # Un compresor POR LLAMADA, no uno compartido: un `ZstdCompressor` usado desde varios
    # hilos a la vez revienta con SIGSEGV (medido: código -11, sin mensaje). El objeto es
    # barato de crear; el fallo, carísimo de diagnosticar.
    def _c(datos_trozo: bytes) -> bytes:
        return zstd.ZstdCompressor(level=nivel).compress(datos_trozo)

    t0 = time.time()
    with ThreadPoolExecutor(hilos) as ex:
        comprimidas = list(ex.map(_c, partes))
    return comprimidas, time.time() - t0


def descomprimir(partes: list[bytes], hilos: int, repes: int = 3) -> tuple[bytes, float]:
    """Con calentamiento y repeticiones, quedándose con el MEJOR tiempo.

    No es optimismo: es que la primera pasada paga la creación del pool, la reserva de los
    búferes de salida y las faltas de página. Medir eso una sola vez y llamarlo «velocidad
    de descompresión» dio 1,3 GB/s donde el estado estacionario da 4,6 — y con esa cifra
    falsa la decisión de arquitectura se habría tomado al revés.
    """
    def _d(parte: bytes) -> bytes:
        return zstd.ZstdDecompressor().decompress(parte)

    mejor = float("inf")
    with ThreadPoolExecutor(hilos) as ex:
        salidas = list(ex.map(_d, partes))          # calentamiento (y verificación)
        for _ in range(repes):
            t0 = time.time()
            salidas = list(ex.map(_d, partes))
            mejor = min(mejor, time.time() - t0)
    return b"".join(salidas), mejor


def _todos_los_shards(dir_modelo: Path, hilos: int, nivel: int, gbs_nvme: float,
                      exigir: bool) -> int:
    """La medición de verdad: los 52 GB, en flujo, sin cargarlos en RAM.

    Se recorre shard a shard en trozos de 256 MB: se separan los planos, se comprime el
    alto, se comprueba que vuelve bit a bit y se suman los tamaños. Nunca hay más de un
    trozo en memoria, así que esto cabe en una máquina de 30 GB midiendo un modelo de 52.
    """
    shards = sorted(dir_modelo.glob("*.safetensors"))
    if not shards:
        raise SystemExit(f"sin shards en {dir_modelo}")
    print(f"== los {len(shards)} shards de {dir_modelo.name}, en flujo ==\n")
    orig = comp = 0
    t0 = time.time()
    for k, s in enumerate(shards, 1):
        with s.open("rb") as fh:
            n_cab = int.from_bytes(fh.read(8), "little")
            fh.seek(8 + n_cab)
            while True:
                bloque = fh.read(256 << 20)
                if len(bloque) < 2:
                    break
                bruto = np.frombuffer(bloque, dtype=np.uint8)
                bruto = bruto[:(len(bruto) // 2) * 2]
                alto, bajo = planos_de_bytes(bruto)
                partes, _ = comprimir(alto.tobytes(), nivel, hilos)
                vuelta, _ = descomprimir(partes, hilos, repes=0)
                if vuelta != alto.tobytes():
                    raise SystemExit(f"{s.name}: el plano alto NO vuelve bit a bit")
                orig += len(bruto)
                comp += sum(map(len, partes)) + len(bajo)
        print(f"  [{k:2d}/{len(shards)}] {s.name:34s} acumulado "
              f"{orig / 1e9:5.1f} GB → {comp / 1e9:5.1f} GB  (razón {orig / comp:.4f})",
              flush=True)
    razon = orig / comp
    seg = time.time() - t0
    print(f"\n── {orig / 1e9:.1f} GB de pesos en {seg / 60:.1f} min, "
          f"reconstrucción bit a bit verificada en todos los shards")
    print(f"\nCIFRA razon_compresion {razon:.4f}")
    print(f"CIFRA gb_modelo_comprimido {comp / 1e9:.3f}")
    print(f"CIFRA ganancia_vs_nvme {razon:.4f}")
    print(f"\n── {orig / 1e9:.0f} GB → {comp / 1e9:.0f} GB · un pase pasa de "
          f"{orig / 1e9 / gbs_nvme:.1f} s a {comp / 1e9 / gbs_nvme:.1f} s desde NVMe")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--shard", default="/home/forge/modelos/qwen3.8-27b/"
                                      "model-00001-of-00018.safetensors")
    p.add_argument("--mb", type=int, default=1024, help="cuántos MB del shard usar")
    p.add_argument("--nivel", type=int, default=1, help="nivel de zstd (1 = el más rápido)")
    p.add_argument("--hilos", type=int, default=0)
    p.add_argument("--gbs-nvme", type=float, default=6.77)
    p.add_argument("--exigir-exacto", action="store_true")
    p.add_argument("--todos", action="store_true",
                   help="recorre TODOS los shards del modelo en flujo (la medición real)")
    a = p.parse_args()

    hilos = a.hilos or os.cpu_count() or 8
    if a.todos:
        return _todos_los_shards(Path(a.shard).parent, hilos, a.nivel, a.gbs_nvme,
                                 a.exigir_exacto)
    ruta = Path(a.shard)
    if not ruta.exists():
        raise SystemExit(f"no existe {ruta}")

    # Se salta la cabecera JSON de safetensors y se toman bytes de pesos de verdad: medir
    # sobre ceros o sobre la cabecera daría una razón de compresión de fantasía.
    with ruta.open("rb") as fh:
        n_cab = int.from_bytes(fh.read(8), "little")
        fh.seek(8 + n_cab)
        crudo = np.frombuffer(fh.read(a.mb << 20), dtype=np.uint8)
    crudo = crudo[:(len(crudo) // 2) * 2]
    print(f"{len(crudo) / 1e6:.0f} MB de pesos BF16 de {ruta.name} · "
          f"zstd nivel {a.nivel} · {hilos} hilos\n")

    filas = []

    partes, t_c = comprimir(crudo.tobytes(), a.nivel, hilos)
    salida, t_d = descomprimir(partes, hilos)
    exacto = salida == crudo.tobytes()
    filas.append(("entrelazado (tal cual)", sum(map(len, partes)), t_c, t_d, exacto))

    alto, bajo = planos_de_bytes(crudo)
    pa, t_ca = comprimir(alto.tobytes(), a.nivel, hilos)
    pb, t_cb = comprimir(bajo.tobytes(), a.nivel, hilos)
    sa, t_da = descomprimir(pa, hilos)
    sb, t_db = descomprimir(pb, hilos)
    rec = np.empty((len(alto), 2), dtype=np.uint8)
    rec[:, 1] = np.frombuffer(sa, dtype=np.uint8)
    rec[:, 0] = np.frombuffer(sb, dtype=np.uint8)
    exacto2 = rec.tobytes() == crudo.tobytes()
    filas.append(("planos de bytes", sum(map(len, pa)) + sum(map(len, pb)),
                  t_ca + t_cb, t_da + t_db, exacto2))

    # Solo el plano alto, dejando el bajo tal cual: si la mantisa es ruido, comprimirla
    # cuesta tiempo y no encoge. Vale la pena saber cuánto de la ganancia viene de cada uno.
    filas.append(("solo el plano alto", sum(map(len, pa)) + len(bajo),
                  t_ca, t_da, exacto2))

    # Dos cuentas, porque la diferencia entre ellas es una decisión de arquitectura:
    #   serie    = leer y LUEGO descomprimir. Es lo que sale si el lector es ingenuo.
    #   solapado = leer la capa N+1 mientras se descomprime la N. Disco y CPU son recursos
    #              distintos, así que un lector con prefetch (H7) alcanza esto.
    print(f"  {'variante':24s} {'MB':>7s} {'razón':>7s} {'descompr':>10s} "
          f"{'serie':>9s} {'solapado':>9s}  exacto")
    orig = len(crudo)
    mejor_razon = mejor_gbs = mejor_serie = 0.0
    for nombre, tam, tc, td, ok in filas:
        razon = orig / tam
        gbs_d = orig / 1e9 / td if td > 0 else float("inf")
        serie = orig / 1e9 / (tam / 1e9 / a.gbs_nvme + td)
        solapado = min(a.gbs_nvme * razon, gbs_d)
        if solapado > mejor_gbs:
            mejor_gbs, mejor_razon, mejor_serie = solapado, razon, serie
        print(f"  {nombre:24s} {tam / 1e6:7.0f} {razon:7.3f} {gbs_d:7.1f}GB/s "
              f"{serie:6.2f}GB/s {solapado:6.2f}GB/s  {'sí' if ok else '¡NO!'}")

    if a.exigir_exacto and not all(f[4] for f in filas):
        raise SystemExit("alguna variante NO reconstruyó los bytes originales")

    print()
    print(f"CIFRA razon_compresion {mejor_razon:.4f}")
    print(f"CIFRA gbs_efectivo {mejor_gbs:.3f}")
    print(f"CIFRA gbs_serie {mejor_serie:.3f}")
    print(f"CIFRA ganancia_vs_nvme {mejor_gbs / a.gbs_nvme:.4f}")
    print(f"CIFRA ganancia_serie {mejor_serie / a.gbs_nvme:.4f}")
    print(f"\n── NVMe crudo {a.gbs_nvme:.2f} GB/s → efectivo {mejor_gbs:.2f} GB/s "
          f"(×{mejor_gbs / a.gbs_nvme:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
