"""Líneas de factura legibles, con el precio ya calculado por tarifas.py."""
from tarifas import precio_final


def linea(concepto, base, iva):
    return f"{concepto}: {precio_final(base, iva):.2f}"
