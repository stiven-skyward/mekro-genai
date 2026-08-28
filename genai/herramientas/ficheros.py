"""ficheros.py — leer y editar. La herramienta `editar` es el ejemplo canónico de grano
grueso: recibe TODOS los cambios de un fichero y los aplica de forma atómica.

POR QUÉ ATÓMICA
---------------
Si de ocho cambios entran seis y fallan dos, el fichero queda en un estado que ni el
modelo ni el humano predijeron, y el modelo —que no vio el resultado— seguirá razonando
sobre el fichero que creía haber escrito. Con un cerebro caro no hay presupuesto para
descubrir eso tres vueltas después. O entran todos o no entra ninguno.

POR QUÉ POR TEXTO EXACTO Y NO POR NÚMERO DE LÍNEA
-------------------------------------------------
Los números de línea se desplazan con el primer cambio. Un modelo pequeño no lleva bien
esa contabilidad. El texto exacto, en cambio, es autoverificable: si aparece dos veces o
ninguna, se rechaza con un motivo accionable en vez de tocar el sitio equivocado.
"""
from __future__ import annotations

from pathlib import Path

from .base import Herramienta, Resultado


def leer(ruta: str, desde: int = 1, lineas: int = 400) -> Resultado:
    p = Path(ruta)
    if not p.exists():
        return Resultado(False, f"no existe: {ruta}")
    if p.is_dir():
        hijos = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        return Resultado(True, f"{ruta} es un directorio:\n" + "\n".join(hijos[:200]))
    try:
        texto = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return Resultado(False, f"{ruta} no es texto UTF-8 (¿binario?)")
    todas = texto.splitlines()
    ini = max(1, desde)
    fin = min(len(todas), ini + lineas - 1)
    cuerpo = "\n".join(f"{i:>5} │ {todas[i - 1]}" for i in range(ini, fin + 1))
    cola = "" if fin >= len(todas) else f"\n[… {len(todas) - fin} líneas más; usa desde={fin + 1}]"
    return Resultado(True, f"── {ruta}  (L{ini}-{fin} de {len(todas)})\n{cuerpo}{cola}",
                     {"lineas_total": len(todas)})


def escribir(ruta: str, contenido: str) -> Resultado:
    p = Path(ruta)
    existia = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contenido, encoding="utf-8")
    verbo = "sobrescrito" if existia else "creado"
    return Resultado(True, f"{verbo} {ruta} ({len(contenido.splitlines())} líneas)",
                     {"ruta": str(p), "creado": not existia})


def editar(ruta: str, cambios: list) -> Resultado:
    """`cambios` = [{"buscar": "...", "poner": "..."}, ...] — todos o ninguno."""
    p = Path(ruta)
    if not p.exists():
        return Resultado(False, f"no existe: {ruta}")
    original = p.read_text(encoding="utf-8")
    texto = original
    aplicados: list[str] = []

    for i, c in enumerate(cambios, 1):
        if not isinstance(c, dict) or "buscar" not in c or "poner" not in c:
            return Resultado(False, f"cambio {i} mal formado: espera "
                                    '{"buscar": "...", "poner": "..."}')
        viejo, nuevo = c["buscar"], c["poner"]
        n = texto.count(viejo)
        if n == 0:
            return Resultado(False, f"cambio {i}: el texto a buscar no aparece en {ruta}. "
                                    "NO se aplicó ningún cambio. Lee el fichero y copia "
                                    f"el fragmento exacto.\n  buscaba: {viejo[:200]!r}")
        if n > 1:
            return Resultado(False, f"cambio {i}: el texto aparece {n} veces en {ruta} y "
                                    "sería ambiguo. NO se aplicó ningún cambio. Añade "
                                    "líneas de contexto alrededor hasta que sea único.")
        texto = texto.replace(viejo, nuevo, 1)
        aplicados.append(f"  {i}. {viejo.splitlines()[0][:60] if viejo else '(vacío)'}…")

    p.write_text(texto, encoding="utf-8")
    delta = len(texto.splitlines()) - len(original.splitlines())
    return Resultado(True, f"{ruta}: {len(cambios)} cambios aplicados "
                           f"({delta:+d} líneas)\n" + "\n".join(aplicados),
                     {"ruta": str(p), "cambios": len(cambios)})


HERRAMIENTAS = [
    Herramienta(
        nombre="leer",
        descripcion="Lee un fichero de texto con números de línea, o lista un directorio.",
        parametros={"type": "object", "properties": {
            "ruta": {"type": "string", "description": "ruta del fichero o directorio"},
            "desde": {"type": "integer", "description": "primera línea (por defecto 1)"},
            "lineas": {"type": "integer", "description": "cuántas líneas (por defecto 400)"}},
            "required": ["ruta"]},
        funcion=leer),
    Herramienta(
        nombre="escribir",
        descripcion="Crea un fichero o sobrescribe uno entero. Para cambios parciales usa «editar».",
        parametros={"type": "object", "properties": {
            "ruta": {"type": "string"},
            "contenido": {"type": "string"}},
            "required": ["ruta", "contenido"]},
        funcion=escribir, peligrosa=True),
    Herramienta(
        nombre="editar",
        descripcion=("Aplica VARIOS cambios por texto exacto a un fichero, de forma atómica "
                     "(o entran todos o no entra ninguno). Manda todos los cambios de un "
                     "fichero en UNA sola llamada: cada llamada cuesta una vuelta entera."),
        parametros={"type": "object", "properties": {
            "ruta": {"type": "string"},
            "cambios": {"type": "array", "description": "lista de cambios en orden",
                        "items": {"type": "object", "properties": {
                            "buscar": {"type": "string",
                                       "description": "texto exacto y ÚNICO en el fichero"},
                            "poner": {"type": "string", "description": "lo que va en su lugar"}},
                            "required": ["buscar", "poner"]}}},
            "required": ["ruta", "cambios"]},
        funcion=editar, peligrosa=True),
]
