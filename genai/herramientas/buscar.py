"""buscar.py — encontrar sin leer.

Aquí se juega la mayor parte del presupuesto de tokens del arnés. La forma ingenua de
orientarse —leer ficheros enteros— es exactamente lo que META.md §puerta 1 declara
inviable: un módulo de 900 líneas son ~9 K tokens, y con tres módulos ya no queda
contexto para pensar.

Estas dos herramientas devuelven **símbolos y coincidencias con su contexto**, no
ficheros. Y hay una tercera vía, mejor que ambas, cuando la tarea ya tiene holograma:
`holograma.py foco`, que reconstruye solo lo que esa tarea necesita.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from .base import Herramienta, Resultado

IGNORAR = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache", "modelos"}


def grep(patron: str, ruta: str = ".", glob: str = "", contexto: int = 2,
         max_coincidencias: int = 60) -> Resultado:
    """`rg` si está; si no, `grep -r`. Se prefiere `rg` porque respeta .gitignore."""
    base = ["rg", "--line-number", "--color", "never",
            "-C", str(contexto), "-m", str(max_coincidencias)]
    if glob:
        base += ["--glob", glob]
    cmd = base + [patron, ruta]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        cmd = ["grep", "-rn", f"-C{contexto}", "--", patron, ruta]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return Resultado(False, "la búsqueda pasó de 60 s: acota la ruta o el patrón")
    if r.returncode not in (0, 1):
        return Resultado(False, f"búsqueda fallida: {r.stderr.strip()[:400]}")
    if not r.stdout.strip():
        return Resultado(True, f"sin coincidencias de «{patron}» en {ruta}")
    return Resultado(True, r.stdout)


def simbolos(aguja: str, ruta: str = ".") -> Resultado:
    """Qué funciones y clases contienen «aguja» en su nombre, con firma y tamaño.

    Por AST y no por grep: una subcadena casa por accidente («leer» está dentro de
    «leer_ventana» y de veinte comentarios), y mandar al modelo a mirar el sitio
    equivocado cuesta una vuelta entera del bucle.
    """
    raiz = Path(ruta)
    aguja_l = aguja.lower()
    filas: list[str] = []
    for p in sorted(raiz.rglob("*.py")):
        if IGNORAR & set(p.parts):
            continue
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if aguja_l not in nodo.name.lower():
                continue
            tipo = "class" if isinstance(nodo, ast.ClassDef) else "def"
            largo = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
            doc = (ast.get_docstring(nodo) or "").strip().splitlines()
            filas.append(f"{p}:{nodo.lineno}  {tipo} {nodo.name}  ({largo} líneas)"
                         + (f"\n      {doc[0][:90]}" if doc else ""))
    if not filas:
        return Resultado(True, f"ningún símbolo contiene «{aguja}» bajo {ruta}")
    return Resultado(True, f"{len(filas)} símbolos:\n" + "\n".join(filas[:80]),
                     {"n": len(filas)})


HERRAMIENTAS = [
    Herramienta(
        nombre="grep",
        descripcion=("Busca un patrón (regex) en los ficheros y devuelve las líneas con "
                     "su contexto. Para orientarte, esto antes que «leer»."),
        parametros={"type": "object", "properties": {
            "patron": {"type": "string"},
            "ruta": {"type": "string", "description": "dónde buscar (por defecto .)"},
            "glob": {"type": "string", "description": "filtro, p.ej. *.py"},
            "contexto": {"type": "integer", "description": "líneas alrededor (2)"}},
            "required": ["patron"]},
        funcion=grep),
    Herramienta(
        nombre="simbolos",
        descripcion=("Qué funciones y clases de Python contienen un texto en su NOMBRE, "
                     "con fichero, línea, tamaño y primera línea de su docstring. "
                     "Devuelve símbolos, no ficheros."),
        parametros={"type": "object", "properties": {
            "aguja": {"type": "string"},
            "ruta": {"type": "string"}},
            "required": ["aguja"]},
        funcion=simbolos),
]
