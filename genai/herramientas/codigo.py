"""`definicion`, `referencias` y `diagnostico`: lo que `grep` no puede saber.

`grep pagar` encuentra la palabra. No sabe si son la misma función, un método homónimo
de otra clase, o una cadena dentro de un comentario. Estas tres herramientas preguntan a
alguien que ha parseado el proyecto de verdad (ver `genai/lsp.py`).

**La salida va podada por diseño, no por gusto.** Cuarenta referencias en tres ficheros
se agrupan por fichero, igual que hace el filtro de `grep` en `genai/ahorro.py`: repetir
la ruta cuarenta veces para decir tres cosas se paga en TODAS las vueltas que queden
(docs/ahorro.md).

**Y si no hay servidor instalado, se dice cuál falta.** Devolver «0 referencias» cuando
lo cierto es «no hay quien busque» es la peor respuesta posible: el modelo concluye que
el símbolo no se usa y borra código vivo.
"""
from __future__ import annotations

import urllib.parse
from pathlib import Path

from ..lsp import para
from .base import Herramienta, Resultado

SEVERIDAD = {1: "error", 2: "aviso", 3: "info", 4: "pista"}


def _pos(f: Path, simbolo: str, linea: int = 0) -> tuple[int, int] | str:
    """Dónde está el símbolo. LSP habla de (línea, carácter) en base 0; el agente
    habla de nombres, que es lo que sabe."""
    try:
        lineas = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"no se pudo leer {f}: {e}"
    orden = range(linea - 1, linea) if linea else range(len(lineas))
    for i in orden:
        if 0 <= i < len(lineas):
            col = lineas[i].find(simbolo)
            if col >= 0:
                return (i, col)
    donde = f" en la línea {linea}" if linea else ""
    return f"«{simbolo}» no aparece en {f.name}{donde}"


def _ruta(uri: str) -> str:
    p = urllib.parse.urlparse(uri)
    return urllib.parse.unquote(p.path)


def _relativa(ruta: str, raiz: Path) -> str:
    try:
        return str(Path(ruta).resolve().relative_to(raiz.resolve()))
    except ValueError:
        return ruta


def _preparar(ruta: str, simbolo: str, linea: int):
    # LSP habla en URIs absolutos; el agente escribe rutas relativas. Se resuelve aquí,
    # una vez, en vez de en cada punto que construya un URI.
    f = Path(ruta).resolve()
    if not f.is_file():
        return None, Resultado(False, f"no existe o no es un fichero: {ruta}")
    srv, queja = para(f)
    if srv is None:
        return None, Resultado(False, queja)
    p = _pos(f, simbolo, linea)
    if isinstance(p, str):
        return None, Resultado(False, p)
    srv.abrir(f)
    return (f, srv, p), None


def definicion(ruta: str, simbolo: str, linea: int = 0) -> Resultado:
    listo, mal = _preparar(ruta, simbolo, linea)
    if mal:
        return mal
    f, srv, (ln, col) = listo
    r = srv._pedir("textDocument/definition", {
        "textDocument": {"uri": f.as_uri()},
        "position": {"line": ln, "character": col}})
    sitios = r if isinstance(r, list) else ([r] if r else [])
    if not sitios:
        return Resultado(False, f"el servidor no sabe dónde se define «{simbolo}». "
                                f"Puede ser de una biblioteca sin fuentes, o estar mal "
                                f"escrito.")
    fuera = []
    for s in sitios[:10]:
        rango = s.get("range") or s.get("targetSelectionRange") or {}
        ini = (rango.get("start") or {}).get("line", 0)
        arch = _ruta(s.get("uri") or s.get("targetUri", ""))
        fuera.append(f"{_relativa(arch, srv.raiz)}:{ini + 1}")
    return Resultado(True, f"«{simbolo}» se define en:\n" + "\n".join(fuera),
                     datos={"sitios": fuera})


def referencias(ruta: str, simbolo: str, linea: int = 0,
                incluir_definicion: bool = True) -> Resultado:
    listo, mal = _preparar(ruta, simbolo, linea)
    if mal:
        return mal
    f, srv, (ln, col) = listo
    r = srv._pedir("textDocument/references", {
        "textDocument": {"uri": f.as_uri()},
        "position": {"line": ln, "character": col},
        "context": {"includeDeclaration": bool(incluir_definicion)}})
    if not r:
        return Resultado(True, f"«{simbolo}» no se usa en ninguna otra parte. "
                               f"Esto lo dice el servidor de lenguaje, no un grep: "
                               f"cuenta como respuesta.")
    # agrupado por fichero: repetir la ruta 40 veces para decir 3 cosas se paga en
    # todas las vueltas que queden (docs/ahorro.md)
    por_fichero: dict[str, list[int]] = {}
    for s in r:
        arch = _relativa(_ruta(s["uri"]), srv.raiz)
        por_fichero.setdefault(arch, []).append(s["range"]["start"]["line"] + 1)
    fuera = [f"«{simbolo}»: {len(r)} referencias en {len(por_fichero)} ficheros"]
    for arch, lineas in sorted(por_fichero.items()):
        nums = ", ".join(str(n) for n in sorted(lineas)[:40])
        fuera.append(f"  {arch}  (líneas {nums})")
    return Resultado(True, "\n".join(fuera),
                     datos={"total": len(r), "ficheros": sorted(por_fichero)})


def diagnostico(ruta: str) -> Resultado:
    f = Path(ruta).resolve()
    if not f.is_file():
        return Resultado(False, f"no existe o no es un fichero: {ruta}")
    srv, queja = para(f)
    if srv is None:
        return Resultado(False, queja)
    ds = srv.diagnosticos(f)
    if not ds:
        return Resultado(True, f"{f.name}: el servidor de lenguaje no ve problemas.")
    fuera = []
    for d in ds[:40]:
        ln = (d.get("range") or {}).get("start", {}).get("line", 0) + 1
        sev = SEVERIDAD.get(d.get("severity", 2), "aviso")
        fuera.append(f"  {f.name}:{ln}  [{sev}] {d.get('message', '')[:160]}")
    cab = f"{len(ds)} diagnósticos en {f.name}"
    if len(ds) > 40:
        cab += " (se muestran 40)"
    return Resultado(not any(d.get("severity") == 1 for d in ds),
                     cab + "\n" + "\n".join(fuera), datos={"total": len(ds)})


_ESQ = {
    "type": "object",
    "properties": {
        "ruta": {"type": "string", "description": "fichero donde aparece el símbolo"},
        "simbolo": {"type": "string", "description": "nombre exacto de la función, "
                                                     "clase o variable"},
        "linea": {"type": "integer", "description": "acota a esta línea si el nombre "
                                                    "aparece varias veces (opcional)"},
    },
    "required": ["ruta", "simbolo"],
}

HERRAMIENTAS = [
    Herramienta(
        nombre="definicion",
        descripcion=("Dónde se DEFINE un símbolo, preguntándoselo a un servidor de "
                     "lenguaje. A diferencia de `grep`, distingue una función de otra "
                     "con el mismo nombre."),
        parametros=_ESQ, funcion=definicion, peligrosa=False),
    Herramienta(
        nombre="referencias",
        descripcion=("Todos los sitios donde se USA un símbolo, de verdad: no las "
                     "coincidencias de texto. Úsala ANTES de renombrar o borrar algo, "
                     "para saber qué vas a romper. Devuelve las líneas agrupadas por "
                     "fichero."),
        parametros={**_ESQ, "properties": {
            **_ESQ["properties"],
            "incluir_definicion": {"type": "boolean",
                                   "description": "incluir la definición (sí)"}}},
        funcion=referencias, peligrosa=False),
    Herramienta(
        nombre="diagnostico",
        descripcion=("Errores y avisos que el servidor de lenguaje ve en un fichero "
                     "SIN ejecutarlo: nombres que no existen, argumentos que sobran, "
                     "tipos que no encajan. Más barato que correr las pruebas."),
        parametros={"type": "object",
                    "properties": {"ruta": {"type": "string"}},
                    "required": ["ruta"]},
        funcion=diagnostico, peligrosa=False),
]
