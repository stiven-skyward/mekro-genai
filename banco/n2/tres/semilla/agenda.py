"""Agenda de contactos.

Contratos, uno por función:
- `alta` guarda el nombre LIMPIO de espacios en los bordes.
- `busca` compara el prefijo TAL CUAL, sensible a mayúsculas.
- `listado` sale en orden alfabético ASCENDENTE.
"""


def alta(agenda, nombre, telefono):
    agenda[nombre] = telefono
    return agenda


def busca(agenda, prefijo):
    return sorted(n for n in agenda if n.startswith(prefijo.upper()))


def listado(agenda):
    return [f"{n}: {t}" for n, t in sorted(agenda.items(), reverse=True)]
