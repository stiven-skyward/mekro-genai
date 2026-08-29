"""genai chat — la conversación continua, probada como se usa: un proceso real,
stdin de verdad, `--cerebro eco` para no depender de ningún modelo.

Lo que separa esto de `genai tarea` y por eso merece su propia prueba: la MISMA
`Sesion` tiene que sobrevivir a varios mensajes dentro de un solo proceso (vueltas
acumuladas, no reiniciadas), los comandos `/algo` no deben gastar un turno del
cerebro, y salir (`/salir` o EOF) tiene que soltar el candado de sesión — si no lo
suelta, la siguiente sesión del directorio queda bloqueada para siempre.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _util import Cuenta

from genai import sesiones

c = Cuenta("chat")
RAIZ = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp(prefix="chat-"))
os.environ["MG_SESIONES"] = str(tmp / "s")

guion = tmp / "guion.json"
guion.write_text(json.dumps(["primera respuesta", "segunda respuesta"]),
                 encoding="utf-8")


def _chat(entrada: str, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    # cwd=tmp (para que .genai/ultima.json y el candado de sesión sean del directorio
    # de prueba, no del propio repositorio) exige PYTHONPATH a mano: `-m genai` solo
    # se resuelve solo cuando el cwd ES el repo o el paquete está instalado.
    entorno = {**os.environ, "MG_COLOR": "0", "PYTHONPATH": str(RAIZ)}
    return subprocess.run(
        [sys.executable, "-m", "genai", "chat", "--cerebro", "eco",
         "--guion", str(guion), "--modo", "lista", *(extra or [])],
        cwd=tmp, input=entrada, capture_output=True, text=True, timeout=30,
        env=entorno)


# ── dos mensajes, una sola sesión ────────────────────────────────────────────
r = _chat("hola\nsegundo mensaje\n/salir\n")
c(r.returncode == 0, f"la REPL termina limpia con /salir (código {r.returncode}, "
                     f"stderr: {r.stderr[-300:]})")
c("primera respuesta" in r.stdout, "el primer mensaje se contesta con el primer paso "
                                   "del guion")
c("segunda respuesta" in r.stdout, "y el segundo con el segundo — MISMO cerebro, "
                                   "misma sesión, el guion no se reinicia")

ultima = json.loads((tmp / ".genai" / "ultima.json").read_text(encoding="utf-8"))
c(ultima["vueltas"] == 2, "la sesión guardada acumuló las DOS vueltas, no solo la "
                          "última — es la misma Sesion todo el rato, no una por mensaje")

# ── comandos meta: no gastan guion (el cerebro eco se agotaría si lo hicieran) ──
r2 = _chat("/ayuda\n/sesion\n/modo plan\n/modo disparate\n/salir\n")
c(r2.returncode == 0, "una sesión hecha solo de comandos meta también sale limpia")
c("comandos" in r2.stdout, "/ayuda muestra la caja de comandos")
c("modo → plan" in r2.stdout, "/modo con un valor válido cambia el modo")
c("modos válidos" in r2.stdout, "/modo con un valor inválido se queja, no revienta")
c("primera respuesta" not in r2.stdout,
  "y ninguno de los meta-comandos llegó a consumir el guion del cerebro")

# ── EOF (Ctrl-D) sale tan limpio como /salir ────────────────────────────────
r3 = _chat("hola\n")   # sin /salir: el guion se acaba y el pipe de stdin se cierra
c(r3.returncode == 0, "cerrar stdin sin /salir (Ctrl-D) también termina en 0")

# ── el candado se suelta de verdad: una sesión nueva no queda bloqueada ─────
libres = [s for s in sesiones.listar() if not s.get("en_curso")]
c(all(not s.get("en_curso") for s in sesiones.listar()),
  "tras las tres conversaciones, NINGUNA sesión quedó marcada «en curso»: /salir, "
  "un /modo inválido y el EOF sueltan el candado por igual")

raise SystemExit(c.fin())
