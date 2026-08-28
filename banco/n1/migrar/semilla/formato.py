"""Formateo de etiquetas. Desde la v2, los interruptores son SOLO por nombre:
la firma vieja `etiqueta(texto, True, False)` confundía el orden de los
booleanos en silencio, y eso costó un informe entero en mayúsculas."""


def etiqueta(texto, *, mayusculas=False, recortar=False):
    if recortar:
        texto = texto.strip()
    if mayusculas:
        texto = texto.upper()
    return f"[{texto}]"
