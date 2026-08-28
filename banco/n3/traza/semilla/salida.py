"""Paso 3: totalizar."""


def total(registros):
    return sum(r["cantidad"] for r in registros)
