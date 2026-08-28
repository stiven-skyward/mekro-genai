"""genai — el arnés desde la terminal, contra el cerebro local y sin nube.

    genai tarea "arregla el bug de suma.py"     un encargo en el directorio actual
    genai tarea "..." --modo todo               sin preguntar (cuidado)
    genai tarea "..." --cerebro eco             el arnés sin modelo (pruebas)
    genai version                               qué hay instalado y qué cerebro ve

El modo por defecto es «preguntar»: lo peligroso (escribir, borrar, ejecutar) se
consulta por consola antes de hacerse. Los topes existen porque cada vuelta cuesta
segundos de CPU de verdad: se enseñan al arrancar y se respetan.
"""
from __future__ import annotations

import argparse
import sys

from genai.cerebro import cargar
from genai.herramientas import estandar
from genai.nucleo import Politica, Sesion, turno
from genai.nucleo.permisos import Decision

SISTEMA = """Eres Mekro-Genai, un agente de ingeniería. Trabajas en el directorio actual.

Cada vuelta tuya cuesta segundos de cómputo local. Por eso:
- Antes de leer ficheros, orientate con `grep` o `simbolos`.
- Manda todos los cambios de un fichero en UNA llamada a `editar`.
- Verifica con `bash` lo que afirmes.
- El intérprete es `python3`; `python` a secas NO existe en esta máquina.
- Nada de `cd`: todas las rutas son relativas al directorio actual.
- Cuando la tarea esté hecha y verificada, responde SIN llamar a ninguna herramienta."""


def _preguntar(herramienta, argumentos) -> Decision:
    firma = f"{herramienta.nombre}({str(argumentos)[:120]})"
    try:
        r = input(f"  ¿{firma}? [s/N] ").strip().lower()
    except EOFError:
        r = ""
    if r in ("s", "si", "sí", "y"):
        return Decision(True, "aprobado por consola")
    return Decision(False, "denegado por consola")


def cmd_tarea(a) -> int:
    import json
    from pathlib import Path

    cerebro = cargar(a.cerebro)
    ultima = Path(".genai") / "ultima.json"
    if a.continuar:
        # M5 brecha 2: la sesión anterior revive tal cual. El primer generar
        # re-prefilla la transcripción UNA vez; después, append-exacto normal.
        if not ultima.exists():
            print(f"no hay sesión que continuar en {ultima}: lanza una tarea primero.")
            return 2
        sesion = Sesion.de_dict(json.loads(ultima.read_text(encoding="utf-8")), cerebro)
        print(f"continuando la sesión {sesion.id} ({sesion.vueltas} vueltas previas, "
              f"{len(sesion.mensajes)} mensajes)")
    else:
        sesion = Sesion(sistema=SISTEMA, cerebro=cerebro)
    politica = Politica(modo=a.modo)
    print(f"cerebro {cerebro.nombre} · modo {a.modo} · topes: {a.vueltas} vueltas, "
          f"{a.tokens} tokens, {a.segundos} s")
    # streaming (M5.5): a 2,9 tok/s, ver avanzar el texto ES la experiencia. El
    # cerebro entrega deltas decodificables; aquí solo se pintan según llegan.
    if hasattr(cerebro, "al_token") and not a.sin_streaming:
        cerebro.al_token = lambda trozo: print(trozo, end="", flush=True)

    def _correr(encargo: str, modo: str):
        return turno(sesion, estandar(malla=a.malla), Politica(modo=modo), encargo,
                     tope_vueltas=a.vueltas, tope_tokens=a.tokens,
                     tope_segundos=a.segundos,
                     preguntar=_preguntar if modo == "preguntar" else None)

    r = _correr(a.encargo, a.modo)
    if a.modo == "plan" and r.motivo == "fin":
        # plan conversacional (M5.5): proponer → aprobar → ejecutar, en la MISMA
        # sesión (el append-exacto hace barata la continuación).
        print(f"\n{r.texto}\n")
        try:
            resp = input("¿ejecutar el plan? [s/N] ").strip().lower()
        except EOFError:
            resp = ""
        if resp in ("s", "si", "sí", "y"):
            r = _correr("Adelante: ejecuta el plan que propusiste, paso a paso.",
                        "preguntar")
        else:
            print("plan no ejecutado; la sesión queda guardada por si cambias de idea.")
    ultima.parent.mkdir(exist_ok=True)
    ultima.write_text(json.dumps(sesion.a_dict(), ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\n{r.texto}\n── {r.motivo} · {r.vueltas} vueltas · "
          f"{r.uso.tokens_salida} tok · {r.uso.segundos:.1f} s · "
          f"sesión guardada en {ultima} (retoma con --continuar)")
    return 0 if r.motivo == "fin" else 1


def cmd_version(_a) -> int:
    from genai.cerebro.local_gguf import GGUF
    from pathlib import Path
    print("Mekro-Genai — arnés agéntico para cerebros locales en CPU")
    ruta = Path(GGUF)
    if ruta.exists():
        print(f"cerebro: {ruta} ({ruta.stat().st_size / 2**30:.1f} GB)")
    else:
        print(f"cerebro: NO ENCONTRADO en {ruta}. Descarga el GGUF y ponlo ahí, o "
              "usa --cerebro eco para probar el arnés sin modelo.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="genai", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden")
    t = sub.add_parser("tarea", help="un encargo agéntico en el directorio actual")
    t.add_argument("encargo")
    t.add_argument("--cerebro", default="gguf",
                   help="gguf (local, defecto) · eco (pruebas) · "
                        "nube:PROVEEDOR[/MODELO] con TU clave (docs/nube.md)")
    t.add_argument("--modo", default="preguntar",
                   choices=("plan", "preguntar", "lista", "todo"))
    t.add_argument("--vueltas", type=int, default=16)
    t.add_argument("--tokens", type=int, default=4000)
    t.add_argument("--segundos", type=int, default=3600)
    t.add_argument("--continuar", action="store_true",
                   help="retomar la última sesión de este directorio (.genai/ultima.json)")
    t.add_argument("--malla", action="store_true",
                   help="modo Mesh: permite delegar tareas a pares (docs/malla.md)")
    t.add_argument("--sin-streaming", action="store_true",
                   help="no pintar el texto según se genera")
    sub.add_parser("version", help="qué hay instalado y qué cerebro ve")
    m = sub.add_parser("malla", help="modo Mesh: donar cómputo o ver la cuenta")
    m.add_argument("resto", nargs=argparse.REMAINDER,
                   help="servir [--puerto N --hilos N] | cuenta")
    a = ap.parse_args(argv)
    if a.orden == "tarea":
        return cmd_tarea(a)
    if a.orden == "version":
        return cmd_version(a)
    if a.orden == "malla":
        from genai.malla import main as malla_main
        return malla_main(a.resto)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
