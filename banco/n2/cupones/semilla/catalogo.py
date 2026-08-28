"""Catálogo de la tienda. Los precios son enteros, en euros."""

PRECIOS = {"pan": 2, "leche": 1, "queso": 5}


def precio(nombre):
    if nombre not in PRECIOS:
        raise ValueError(f"{nombre} no está en el catálogo")
    return PRECIOS[nombre]
