"""git como herramienta de primera clase (M7.5), con la salida ya podada.

Dos motivos, y el segundo es el que decide la forma:

1. **Sin git, el agente trabaja a ciegas.** No sabe qué cambió él, no puede deshacer, y
   quien revisa su trabajo tiene que ir a mirar a mano. Es la brecha 5 del informe de
   paridad.
2. **Un diff ES poda en el origen.** Enseñar «estas 6 líneas cambiaron» en vez del
   fichero entero es exactamente lo que docs/ahorro.md pide: recortar antes de que
   entre, no después. Por eso el diff aquí va sin contexto por defecto y el `estado` va
   en formato corto — no por gusto tipográfico, sino porque cada carácter que entra
   aquí se reenvía en todas las vueltas que queden.

**Qué NO hace**: nada que reescriba historia o hable con un remoto. Ni `push`, ni
`reset --hard`, ni `rebase`, ni `clean`. Un agente que puede borrar el trabajo de otro
no es una herramienta, es un accidente esperando. Publicar sigue siendo un acto humano.
"""
from __future__ import annotations

import subprocess

from .base import Herramienta, Resultado

# Solo lo que informa o registra. `commit` entra porque es reversible y es lo que hace
# revisable el trabajo del agente; todo lo que destruye o publica se queda fuera.
PERMITIDOS = {"estado", "diff", "log", "ramas", "commit", "muestra"}
VETADOS = ("push", "reset", "rebase", "clean", "checkout", "restore", "cherry-pick",
           "filter-branch", "gc", "remote", "config", "submodule")


def _git(*args: str, tope: int = 30_000) -> tuple[bool, str]:
    try:
        p = subprocess.run(("git",) + args, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return False, "git no está instalado en esta máquina"
    except subprocess.TimeoutExpired:
        return False, "git tardó más de 60 s; ¿es un repositorio enorme?"
    salida = (p.stdout + p.stderr).strip()
    return p.returncode == 0, salida[:tope]


def git(accion: str, ruta: str = "", mensaje: str = "", n: int = 10) -> Resultado:
    accion = (accion or "").strip().lower()
    if accion not in PERMITIDOS:
        return Resultado(False, f"«{accion}» no está permitida. Disponibles: "
                                f"{', '.join(sorted(PERMITIDOS))}. Lo que reescribe "
                                f"historia o publica ({', '.join(VETADOS[:5])}…) no es "
                                f"del agente: eso lo decide una persona.")
    ok, _ = _git("rev-parse", "--git-dir")
    if not ok:
        return Resultado(False, "aquí no hay repositorio git (`git init` primero)")

    if accion == "estado":
        # --short: una línea por fichero en vez de la parrafada con consejos que git
        # imprime para humanos y que aquí se pagaría en cada vuelta.
        ok, s = _git("status", "--short", "--branch")
        return Resultado(ok, s or "árbol limpio, nada que registrar")

    if accion == "diff":
        # -U0: sin líneas de contexto. El agente ya tiene el fichero si lo necesita;
        # lo que no tiene es saber QUÉ cambió, y eso son las líneas marcadas.
        ok, resumen = _git("diff", "--stat", *( [ruta] if ruta else [] ))
        ok2, cuerpo = _git("diff", "-U0", *( [ruta] if ruta else [] ), tope=20_000)
        if not (resumen or cuerpo):
            ok3, s = _git("diff", "--cached", "--stat")
            return Resultado(True, s or "sin cambios respecto a HEAD")
        return Resultado(ok and ok2, (resumen + "\n\n" + cuerpo).strip())

    if accion == "log":
        ok, s = _git("log", f"-{max(1, min(n, 40))}", "--oneline", "--no-decorate",
                     *([ "--", ruta] if ruta else []))
        return Resultado(ok, s or "todavía no hay commits")

    if accion == "muestra":
        ok, s = _git("show", "--stat", "-U0", ruta or "HEAD", tope=20_000)
        return Resultado(ok, s)

    if accion == "ramas":
        ok, s = _git("branch", "--format=%(refname:short)%(if)%(HEAD)%(then)  ← aquí%(end)")
        return Resultado(ok, s)

    if accion == "commit":
        if not mensaje.strip():
            return Resultado(False, "un commit sin mensaje no sirve a quien lo lea "
                                    "mañana: di QUÉ cambia y POR QUÉ")
        _git("add", ruta or "-A")
        ok2, s = _git("commit", "-m", mensaje.strip())
        if not ok2 and "nothing to commit" in s:
            return Resultado(False, "no hay nada que registrar: el árbol está limpio")
        return Resultado(ok2, s.splitlines()[0] if s else "commit hecho")

    return Resultado(False, f"acción no implementada: {accion}")


HERRAMIENTAS = [
    Herramienta(
        nombre="git",
        descripcion=(
            "Consulta y registra en git. Acciones: `estado` (qué has tocado), `diff` "
            "(qué cambió exactamente, sin contexto para no gastar contexto), `log`, "
            "`muestra` (un commit), `ramas`, `commit` (mensaje obligatorio). "
            "Úsala para revisar tu propio trabajo antes de darlo por bueno. NO puede "
            "publicar ni reescribir historia: eso lo decide una persona."),
        parametros={
            "type": "object",
            "properties": {
                "accion": {"type": "string",
                           "enum": sorted(PERMITIDOS),
                           "description": "qué hacer"},
                "ruta": {"type": "string",
                         "description": "acota a un fichero o directorio (opcional)"},
                "mensaje": {"type": "string",
                            "description": "solo para commit: qué cambia y por qué"},
                "n": {"type": "integer",
                      "description": "solo para log: cuántos commits (por defecto 10)"},
            },
            "required": ["accion"],
        },
        funcion=git,
        peligrosa=True,       # commit escribe: pasa por permisos.py como todo lo demás
    ),
]
