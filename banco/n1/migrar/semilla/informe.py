"""Arma las líneas de un informe con las etiquetas de formato.py."""
from formato import etiqueta


def cabecera(titulo):
    return etiqueta(titulo, True, True)


def nota(texto):
    return etiqueta(texto, False, True)
