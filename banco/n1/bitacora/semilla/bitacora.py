"""Bitácora de eventos sobre disco.py. Un fichero que aún no existe ES una
bitácora: la vacía. El primer arranque no puede ser un caso especial para
quien la consulta."""
from disco import anotar, cargar


def eventos(ruta):
    return cargar(ruta)


def registrar(ruta, texto):
    anotar(ruta, {"que": texto})
