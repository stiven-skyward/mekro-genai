"""Turnos de trabajo: un turno es (inicio, fin) en horas enteras, fin excluido."""


def solapan(a, b):
    """¿Se pisan dos turnos? Tocarse en el borde —el fin de uno igual al inicio
    del otro— NO es pisarse."""
    return a[0] <= b[1] and b[0] <= a[1]


def huecos(turnos, jornada=(0, 24)):
    """Los tramos de la jornada que ningún turno cubre, ordenados."""
    libres = []
    cursor = jornada[0]
    for ini, fin in sorted(turnos):
        if ini > cursor:
            libres.append((cursor, ini))
        cursor = max(cursor, fin)
    if cursor < jornada[1]:
        libres.append((cursor, jornada[1]))
    return libres
