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

# ── @fichero: el contenido llega al mensaje SIN gastar un turno en `leer` ───
adjunto = tmp / "notas.txt"
adjunto.write_text("contenido de prueba único 7f3a", encoding="utf-8")
r4 = _chat(f"resume @{adjunto}\n/salir\n")
c(r4.returncode == 0, "un mensaje con @fichero también sale limpio")
c(f"@{adjunto} adjuntado" in r4.stdout, "la terminal confirma qué fichero adjuntó")

ultima4 = json.loads((tmp / ".genai" / "ultima.json").read_text(encoding="utf-8"))
mensaje_usuario = next(m["contenido"] for m in ultima4["mensajes"] if m["rol"] == "usuario")
c("contenido de prueba único 7f3a" in mensaje_usuario,
  "el CONTENIDO del fichero quedó dentro del mensaje real que vio el cerebro — no "
  "una promesa de que se leyó, sino el texto de verdad en la transcripción guardada")

# ── /deshacer: un punto de control real, restaurado desde dentro del chat ───
objetivo = tmp / "editable.txt"
objetivo.write_text("antes\n", encoding="utf-8")
guion_editar = tmp / "guion_editar.json"
guion_editar.write_text(json.dumps([
    "<tool_call>\n" + json.dumps({"name": "editar", "arguments": {
        "ruta": str(objetivo),
        "cambios": [{"buscar": "antes", "poner": "despues"}]}}) + "\n</tool_call>",
    "cambiado.",
]), encoding="utf-8")
r5 = _chat("cambia el fichero\n/deshacer\n/salir\n", extra=["--guion", str(guion_editar)])
c(r5.returncode == 0, "una conversación con edición + /deshacer sale limpia")
c(objetivo.read_text() == "antes\n",
  "/deshacer devolvió el fichero a su contenido de antes del mensaje, desde dentro "
  "del propio REPL — sin gastar otra vuelta del cerebro en pedirlo de nuevo")
c("deshecho:" in r5.stdout, "y la terminal confirma qué se deshizo")

# ── /modelo: cambiar de cerebro SIN perder el historial ─────────────────────
r6 = _chat("hola\n/modelo eco\n/sesion\n/salir\n")
c(r6.returncode == 0, "cambiar de cerebro con /modelo sale limpio")
c("cerebro → eco" in r6.stdout, "/modelo confirma a qué cerebro cambió")
c("el historial sigue igual" in r6.stdout,
  "y lo dice explícitamente: cambiar de cerebro no reinicia la conversación")
c("1 vueltas" in r6.stdout.split("cerebro → eco", 1)[1],
  "/sesion DESPUÉS del cambio sigue contando la vuelta gastada ANTES de cambiar — "
  "es la misma Sesion, no una nueva con el contador a cero")

r7 = _chat("hola\n/modelo proveedor-que-no-existe\n/salir\n")
c(r7.returncode == 0, "pedir un cerebro que no carga no tumba la conversación")
c("no se pudo cargar" in r7.stdout,
  "se avisa del fallo y se sigue con el cerebro de antes, en vez de morir a medias")

# ── /modelo SIN argumento: el menú guiado ───────────────────────────────────
# los 8 de fábrica, en orden alfabético: 2=anthropic 3=deepseek 4=gemini 5=groq
# 6=kimi 7=openai 8=openrouter 9=xai — luego 10=copilot 11=google, luego un
# número por cada cliente MCP (crece si se añade uno nuevo: NO se fija a mano),
# y el último es «personalizado».
from genai.cerebro.nube import PROVEEDORES as _PROV
from genai.mcp_clientes import CLIENTES as _MCP_CLIENTES

_primer_mcp = 2 + len(_PROV) + 2
_num_personalizado = _primer_mcp + len(_MCP_CLIENTES)

claves_menu = tmp / "claves_menu.json"
claves_menu.write_text(json.dumps({"gemini": {"clave": "clave-de-prueba"}}),
                       encoding="utf-8")


def _chat_menu(entrada: str) -> subprocess.CompletedProcess:
    entorno = {**os.environ, "MG_COLOR": "0", "PYTHONPATH": str(RAIZ),
              "MG_CLAVES": str(claves_menu)}
    return subprocess.run(
        [sys.executable, "-m", "genai", "chat", "--cerebro", "eco",
         "--guion", str(guion), "--modo", "lista"],
        cwd=tmp, input=entrada, capture_output=True, text=True, timeout=30,
        env=entorno)


r8 = _chat_menu("/modelo\n0\n/salir\n")
c(r8.returncode == 0, "abrir el menú guiado y cancelar con 0 sale limpio")
c("elige un cerebro" in r8.stdout, "el menú se muestra de verdad")
c("configurado" in r8.stdout and "sin clave" in r8.stdout,
  "y distingue, proveedor por proveedor, cuáles ya tienen clave puesta")

r9 = _chat_menu("/modelo\n4\n/salir\n")
c(r9.returncode == 0, "elegir por número un proveedor YA configurado (4=gemini) funciona")
c("cerebro → nube:gemini" in r9.stdout,
  "y cambia de verdad al cerebro que corresponde a ese número")

r10 = _chat_menu("/modelo\n3\n/salir\n")
c(r10.returncode == 0, "elegir un proveedor SIN clave (3=deepseek) no revienta la conversación")
c("no se pudo cargar" in r10.stdout,
  "y se enseña el mensaje de cargar() —dónde poner la clave— tal cual, sin duplicar "
  "esa ayuda en el propio menú")

r11 = _chat_menu(f"/modelo\n{_num_personalizado}\nnombre-que-no-existe\n/salir\n")
c(r11.returncode == 0, "la opción «otro» pide un nombre a mano sin reventar")
c("no se pudo cargar" in r11.stdout, "y lo intenta cargar igual, fallando limpio si no existe")

r12 = _chat_menu("/modelo\n999\n/salir\n")
c(r12.returncode == 0, "un número que no es ninguna opción de la lista no revienta")
c("no es ninguna de las opciones" in r12.stdout, "y lo dice explícitamente")

# ── MCP en el propio menú: Cursor, Claude Code, Codex (ChatGPT), Antigravity ──
c(_MCP_CLIENTES, "hay al menos un cliente MCP registrado para esta prueba")
_clave_mcp, _info_mcp = next(iter(_MCP_CLIENTES.items()))
r13 = _chat_menu(f"/modelo\n{_primer_mcp}\n/salir\n")
c(r13.returncode == 0, "elegir un cliente MCP desde el menú no revienta la conversación")
c(_info_mcp["nombre"] in r13.stdout,
  "se enseña de verdad qué cliente es —Cursor, Claude Code, Codex/ChatGPT Plus/Pro, "
  "Antigravity, Kimi Code, según cuál sea el primero registrado— no una opción muda")
c("genai mcp instalar" in r13.stdout,
  "con el comando exacto para activarlo EN OTRA terminal")
c("cerebro →" not in r13.stdout,
  "y NO intenta cargarlo como si fuera un cerebro de chat: el que genera sigue "
  "siendo el cliente externo con su propia suscripción, esto solo informa")

raise SystemExit(c.fin())
