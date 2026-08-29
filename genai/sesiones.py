"""Registro de sesiones del proyecto: varios agentes a la vez sin pisarse.

Hasta ahora una sesión era un fichero suelto en `logs/sesiones/`. Eso basta para un
agente; con dos trabajando en el mismo proyecto hace falta responder a tres preguntas
que el fichero suelto no contesta: **cuáles hay, cuál está viva, y quién la tiene
cogida**.

**El bloqueo es de sesión, no de proyecto.** Bloquear el proyecto entero convertiría la
multi-sesión en un turno de espera, que es justo lo contrario de lo que se busca. Dos
agentes pueden trabajar a la vez sobre el mismo repositorio; lo que no pueden es
escribir los dos en la MISMA sesión, porque el hilo de una conversación no admite dos
autores.

**El candado lleva el PID y se comprueba que ese proceso viva.** Un candado de fichero
sin dueño es peor que no tener candado: si el proceso muere a mitad —Ctrl-C, OOM, un
corte— la sesión queda bloqueada para siempre y la única salida es borrar ficheros a
mano. Aquí un candado huérfano se detecta y se recoge.

**Y avisa de lo que NO puede impedir.** Dos agentes sobre el mismo repositorio pueden
editar el mismo fichero; eso no lo arregla un candado de sesión y fingir que sí sería
peor que no tenerlo. `conflictos()` mira los ficheros que cada sesión ha tocado y lo
dice.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

RAIZ = Path(".genai") / "sesiones"
CADUCA = 8 * 3600          # una sesión sin latido más de 8 h se da por muerta


def _dir(raiz: Path | str | None = None) -> Path:
    d = Path(raiz) if raiz else Path(os.environ.get("MG_SESIONES", RAIZ))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vivo(pid: int) -> bool:
    """¿Existe ese proceso? Es lo que separa un candado de un candado huérfano."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                 # existe, es de otro usuario
    return True


def _leer(f: Path) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir_atomico(f: Path, datos: dict) -> None:
    # temporal + rename: atómico en POSIX y en Windows. Un `write_text()` a secas
    # trunca el fichero a 0 bytes y LUEGO escribe — un `listar()` concurrente (otro
    # hilo del servidor, atendiendo un GET mientras esto escribe) puede leer justo
    # en ese hueco, ver un JSON vacío o a medias, y DESCARTAR la sesión entera
    # (`if not s.get("id"): continue` en `listar()`): un GET /sesiones/<id> real
    # puede devolver 404 en ese instante. Encontrado reproduciendo de verdad un
    # fallo intermitente de tests/test_servidor_ui.py (2 de 15 carreras).
    tmp = f.with_suffix(f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def crear(titulo: str = "", raiz=None, meta: dict | None = None) -> dict:
    ident = uuid.uuid4().hex[:12]
    d = {"id": ident, "titulo": titulo.strip() or "(sin título)",
         "creada": time.time(), "latido": time.time(), "estado": "nueva",
         "duenyo": 0, "tocados": [], "vueltas": 0, "meta": meta or {}}
    _escribir_atomico(_dir(raiz) / f"{ident}.json", d)
    return d


def listar(raiz=None) -> list[dict]:
    fuera = []
    for f in sorted(_dir(raiz).glob("*.json")):
        s = _leer(f)
        if not s.get("id"):
            continue
        s["viva"] = bool(s.get("duenyo")) and _vivo(s["duenyo"])
        s["rancia"] = (time.time() - s.get("latido", 0)) > CADUCA
        fuera.append(s)
    return sorted(fuera, key=lambda s: s.get("latido", 0), reverse=True)


def _guardar(s: dict, raiz=None) -> None:
    _escribir_atomico(_dir(raiz) / f"{s['id']}.json", s)


def tomar(ident: str, raiz=None) -> tuple[dict | None, str]:
    """Coge una sesión en exclusiva. Devuelve (sesión, queja).

    Aquí vive la decisión: si el dueño anotado ya no existe, el candado se RECOGE y se
    dice. Un candado sin dueño no protege nada y sí impide trabajar."""
    f = _dir(raiz) / f"{ident}.json"
    if not f.is_file():
        return None, f"no existe la sesión «{ident}»"
    s = _leer(f)
    duenyo = s.get("duenyo", 0)
    if duenyo and duenyo != os.getpid():
        if _vivo(duenyo):
            return None, (f"la sesión «{ident}» la tiene el proceso {duenyo}, que sigue "
                          f"vivo. Abre otra con `genai sesiones nueva`: dos agentes "
                          f"pueden trabajar en el mismo proyecto, pero no en el mismo "
                          f"hilo de conversación.")
        s["recogidas"] = s.get("recogidas", 0) + 1      # candado huérfano
    s["duenyo"] = os.getpid()
    s["latido"] = time.time()
    s["estado"] = "activa"
    _guardar(s, raiz)
    return s, ""


def soltar(ident: str, raiz=None, estado: str = "libre") -> None:
    f = _dir(raiz) / f"{ident}.json"
    if not f.is_file():
        return
    s = _leer(f)
    if s.get("duenyo") in (0, os.getpid()):
        s["duenyo"], s["estado"], s["latido"] = 0, estado, time.time()
        _guardar(s, raiz)


def latir(ident: str, raiz=None, **campos) -> None:
    """Señal de vida más lo que haya cambiado (vueltas, ficheros tocados)."""
    f = _dir(raiz) / f"{ident}.json"
    if not f.is_file():
        return
    s = _leer(f)
    s["latido"] = time.time()
    for k, v in campos.items():
        if k == "tocados":
            s["tocados"] = sorted(set(s.get("tocados", [])) | set(v))
        else:
            s[k] = v
    _guardar(s, raiz)


def conflictos(raiz=None) -> list[tuple[str, list[str]]]:
    """Ficheros que más de una sesión VIVA ha tocado.

    El candado de sesión no impide que dos agentes editen el mismo fichero del
    repositorio, y fingir que sí sería peor que no tenerlo. Esto no lo impide tampoco:
    lo DICE, que es lo honesto y lo accionable."""
    vivas = [s for s in listar(raiz) if s.get("viva")]
    de_quien: dict[str, list[str]] = {}
    for s in vivas:
        for t in s.get("tocados", []):
            de_quien.setdefault(t, []).append(s["id"])
    return sorted((f, ids) for f, ids in de_quien.items() if len(ids) > 1)


def limpiar(raiz=None) -> int:
    """Quita las sesiones rancias y sin dueño. Devuelve cuántas."""
    n = 0
    for s in listar(raiz):
        if s.get("rancia") and not s.get("viva"):
            (_dir(raiz) / f"{s['id']}.json").unlink(missing_ok=True)
            n += 1
    return n
