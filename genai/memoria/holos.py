"""holos.py — el holograma, expuesto al cerebro como herramienta.

Es la pieza que cierra META.md §puerta 1: si el arnés puede hacer `foco H3` en vez de
leer cuatro módulos, su presupuesto de contexto deja de ser el cuello de botella. Y como
`holograma.py` avisa cuando un ancla se rompe, el arnés se entera de que su mapa está
desactualizado en lugar de razonar sobre código que ya no existe.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..herramientas.base import Herramienta, Resultado

# Honra MG_RAIZ como el resto del proyecto. Sin esto, una tarea del banco que use
# `anotar` escribiría en el holograma REAL en vez de en su directorio de trabajo, y el
# banco dejaría de ser repetible: la segunda carrera vería lo que escribió la primera.
RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parents[2]))


def _holograma(*args: str) -> Resultado:
    r = subprocess.run([sys.executable, "holograma.py", *args],
                       cwd=RAIZ, capture_output=True, text=True, timeout=60)
    salida = (r.stdout or "") + (r.stderr or "")
    return Resultado(r.returncode == 0, salida.strip() or "(sin salida)")


def listar_holos() -> Resultado:
    return _holograma("listar")


def foco(ident: str) -> Resultado:
    return _holograma("foco", ident)


def anotar(ident: str, texto: str) -> Resultado:
    return _holograma("anotar", ident, texto)


HERRAMIENTAS = [
    Herramienta(
        nombre="holos",
        descripcion=("El mapa de tareas vivas del proyecto: identificador, título, hito y "
                     "cuántas anclas tiene cada una. ~40 tokens por tarea."),
        parametros={"type": "object", "properties": {}},
        funcion=listar_holos),
    Herramienta(
        nombre="foco",
        descripcion=("Reconstruye el contexto COMPLETO de una tarea (síntoma, causa, "
                     "comprobación de cierre y el código exacto de sus anclas). Úsalo "
                     "ANTES de leer ficheros: cuesta una fracción y no trae ruido."),
        parametros={"type": "object", "properties": {
            "ident": {"type": "string", "description": "el identificador, p.ej. H1"}},
            "required": ["ident"]},
        funcion=foco),
    Herramienta(
        nombre="anotar",
        descripcion=("Deja constancia en la bitácora de una tarea para la sesión "
                     "siguiente. Lo que no se anota, se vuelve a descubrir."),
        parametros={"type": "object", "properties": {
            "ident": {"type": "string"},
            "texto": {"type": "string"}},
            "required": ["ident", "texto"]},
        funcion=anotar, peligrosa=True),
]
