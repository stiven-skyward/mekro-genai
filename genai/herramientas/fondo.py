"""fondo.py — trabajo en segundo plano sin sentar el turno a esperar (M5 brecha 3).

El patrón es el que este proyecto ya practicaba a mano con los `.pid` en `logs/` y el
que el arnés de Claude Code ofrece de serie: lanzar desasido, seguir trabajando, y que
el AVISO llegue solo al terminar. Aquí el aviso lo entrega el bucle al empezar la vuelta
siguiente (un agente síncrono no tiene interrupciones: tiene vueltas).

Tres piezas por proceso, en `.genai/fondo/` del directorio de trabajo:
    <nombre>.log      la salida (stdout+stderr), viva mientras corre
    <nombre>.rc       aparece AL TERMINAR, con el código de salida — es la señal
    <nombre>.avisado  marca de que el bucle ya dio el aviso (para no repetirlo)

`fondo_lanzar` figura en `EJECUTAN_SHELL` (permisos.py): pasa por el veto, las rutas
vedadas y la lista blanca EXACTAMENTE igual que `bash` — un lanzador de fondo que las
esquivara sería un agujero, no una herramienta.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .base import Herramienta, Resultado

DIR = Path(".genai") / "fondo"


def lanzar(comando: str, nombre: str) -> Resultado:
    if not str(nombre).isidentifier():
        return Resultado(False, "el nombre debe ser un identificador simple "
                                "(letras, dígitos, guion bajo), sin rutas.")
    DIR.mkdir(parents=True, exist_ok=True)
    log, rc, pid = (DIR / f"{nombre}.log", DIR / f"{nombre}.rc", DIR / f"{nombre}.pid")
    if pid.exists() and not rc.exists():
        return Resultado(False, f"ya hay un fondo «{nombre}» vivo. Espera su aviso, "
                                "revísalo con fondo_revisar, o usa otro nombre.")
    for viejo in (rc, DIR / f"{nombre}.avisado"):
        viejo.unlink(missing_ok=True)
    envoltura = f"({comando}); echo $? > {rc}"
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.Popen(envoltura, shell=True, stdout=f,
                             stderr=subprocess.STDOUT, start_new_session=True)
    pid.write_text(str(p.pid), encoding="utf-8")
    return Resultado(True, f"lanzado en fondo «{nombre}» (pid {p.pid}). Sigue con otra "
                           "cosa: el bucle avisará cuando termine. Para mirar cómo va: "
                           f"fondo_revisar({{\"nombre\": \"{nombre}\"}}).",
                     {"pid": p.pid})


def revisar(nombre: str) -> Resultado:
    log, rc = DIR / f"{nombre}.log", DIR / f"{nombre}.rc"
    if not log.exists():
        return Resultado(False, f"no existe ningún fondo llamado «{nombre}».")
    cola = log.read_text(encoding="utf-8", errors="ignore")[-1500:]
    if rc.exists():
        codigo = (rc.read_text(encoding="utf-8").strip() or "1")
        return Resultado(codigo == "0",
                         f"«{nombre}» TERMINÓ con código {codigo}. Cola del log:\n{cola}",
                         {"codigo": int(codigo)})
    return Resultado(True, f"«{nombre}» aún corre. Cola del log:\n{cola}")


def avisos_pendientes() -> list[str]:
    """Para el bucle: fondos terminados de los que todavía no se dio aviso. Cada uno
    se entrega UNA vez (la marca .avisado evita repetir)."""
    if not DIR.exists():
        return []
    listos = []
    for rc in sorted(DIR.glob("*.rc")):
        marca = rc.with_suffix(".avisado")
        if marca.exists():
            continue
        codigo = (rc.read_text(encoding="utf-8").strip() or "?")
        listos.append(f"el proceso de fondo «{rc.stem}» terminó con código {codigo}. "
                      f"Mira su salida con fondo_revisar({{\"nombre\": \"{rc.stem}\"}}).")
        marca.touch()
    return listos


HERRAMIENTAS = [
    Herramienta(
        nombre="fondo_lanzar",
        descripcion=("Lanza un comando de shell en SEGUNDO PLANO y devuelve el control "
                     "de inmediato. Úsalo para lo que tarde más de un minuto (compilar, "
                     "una carrera, una descarga): el bucle te avisará al terminar. "
                     "Pasa por los mismos permisos que bash."),
        parametros={"type": "object", "properties": {
            "comando": {"type": "string"},
            "nombre": {"type": "string",
                       "description": "identificador corto para seguirlo"}},
            "required": ["comando", "nombre"]},
        peligrosa=True,
        ejecuta_shell=True,
        funcion=lanzar),
    Herramienta(
        nombre="fondo_revisar",
        descripcion="Mira cómo va (o cómo acabó) un proceso lanzado con fondo_lanzar.",
        parametros={"type": "object", "properties": {
            "nombre": {"type": "string"}}, "required": ["nombre"]},
        peligrosa=False,
        funcion=revisar),
]
