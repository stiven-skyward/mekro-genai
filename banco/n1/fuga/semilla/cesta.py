"""Agrupar la compra por iniciales. OJO: cada llamada parte de cero; lo que
se agrupó en una cesta no puede aparecer en la siguiente."""


def agrupar(palabras, grupos={}):
    for p in palabras:
        grupos.setdefault(p[0], []).append(p)
    return grupos
