"""Cálculo de precios. El IVA y el descuento son fracciones (0.5, no 50)."""


def precio_final(base, iva):
    return base * (1 + iva)
