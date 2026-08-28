"""Contrato: los sesenta validadores aceptan cadenas de hasta 40 caracteres.

Imprime una linea por validador y por caso. El fallo NO esta al final.
"""
import validadores

fallos = []
corta, justa, larga = "ab", "x" * 40, "y" * 41

for i in range(60):
    f = getattr(validadores, f"campo_{i}")
    for etiqueta, valor, esperado in (("corta", corta, True),
                                      ("justa-40", justa, True),
                                      ("larga-41", larga, False)):
        obtenido = f(valor)
        marca = "ok " if obtenido == esperado else "FALLO"
        print(f"{marca} campo_{i} {etiqueta}: esperaba {esperado}, obtuvo {obtenido}")
        if obtenido != esperado:
            fallos.append(f"campo_{i} {etiqueta}")

print(f"--- {180 - len(fallos)}/180 casos correctos ---")
if fallos:
    # A proposito NO se dice cual falla: la senal esta en la linea FALLO, en medio de
    # las 182. Leer solo la cola no basta, y ese es el punto de esta tarea.
    raise SystemExit(f"FALLAN {len(fallos)} de 180 casos")
