"""deshacer.py — el checkpoint que un cerebro que no se puede reintentar necesita.

Claude Code y OpenCode pueden permitirse «total, pido que lo rehaga»: una vuelta de
más cuesta segundos de nube. Aquí una vuelta mala cuesta minutos de CPU real que no
vuelven (META.md) — deshacer una edición tiene que ser instantáneo, no una generación
más. `turno()` guarda, ANTES de que un `editar`/`escribir` toque un fichero por primera
vez EN ESE TURNO, el contenido que tenía — un punto de control por MENSAJE, no por
llamada a herramienta suelta, porque «deshaz lo que acabo de pedir» es la unidad con la
que piensa quien escribe, no «deshaz la tercera de las cinco ediciones de dentro».

Un fichero que no existía se restaura BORRÁNDOLO (se guarda `None`, no ""): deshacer un
`escribir` sobre algo nuevo tiene que dejar el árbol exactamente como estaba, no un
fichero vacío que antes no estaba.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _dir(sesion_id: str) -> Path:
    raiz = Path(os.environ.get("MG_DESHACER", ".genai/deshacer"))
    return raiz / sesion_id


def guardar(sesion_id: str, encargo: str, snapshot: dict[str, str | None]) -> Path | None:
    """Un punto de control por turno; `snapshot` es ruta→contenido ANTES (`None` si
    el fichero no existía). Vacío no se guarda: nada que deshacer, nada que archivar
    —el mismo criterio que `ahorro.podar()` usa para su propio archivo recuperable."""
    if not snapshot:
        return None
    d = _dir(sesion_id)
    d.mkdir(parents=True, exist_ok=True)
    ruta = d / f"{time.time():.6f}.json"
    ruta.write_text(json.dumps({"encargo": encargo, "ficheros": snapshot},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    return ruta


def listar(sesion_id: str) -> list[dict]:
    """Los puntos de control de esta sesión, del más reciente al más viejo."""
    d = _dir(sesion_id)
    if not d.is_dir():
        return []
    puntos = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            datos = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        puntos.append({"ruta": f, "encargo": datos.get("encargo", ""),
                       "ficheros": list(datos.get("ficheros", {}).keys())})
    return puntos


def deshacer_ultimo(sesion_id: str) -> tuple[bool, str, list[str]]:
    """Restaura el punto de control MÁS RECIENTE y lo consume (se borra): repetir
    `/deshacer` camina hacia atrás, mensaje a mensaje —como el rewind de Claude
    Code— en vez de reaplicar siempre el mismo punto."""
    puntos = listar(sesion_id)
    if not puntos:
        return False, "no hay nada que deshacer en esta sesión", []
    p = puntos[0]
    datos = json.loads(p["ruta"].read_text(encoding="utf-8"))
    restaurados = []
    for ruta_str, contenido in datos["ficheros"].items():
        ruta = Path(ruta_str)
        if contenido is None:
            ruta.unlink(missing_ok=True)
        else:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(contenido, encoding="utf-8")
        restaurados.append(ruta_str)
    p["ruta"].unlink()
    return True, datos.get("encargo", ""), restaurados
