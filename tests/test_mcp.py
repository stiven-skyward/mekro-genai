"""Mekro-Genai como servidor MCP: el arnés usado desde Antigravity/Claude Desktop.

No se prueba "que hable JSON", se prueba lo único que importa de exponer el arnés a un
cliente remoto: que la política de permisos actúe IGUAL que en el bucle normal. Un
cliente MCP no es más de confianza que el propio agente — si esto se pudiera saltar el
veto duro o la lista blanca, exponerlo por MCP sería un agujero, no una funcionalidad.
"""
import io
import json

from _util import Cuenta

from genai.herramientas.base import Registro
from genai.mcp import ServidorMCP
from genai.nucleo.permisos import Politica

c = Cuenta("mcp")


def _hablar(srv: ServidorMCP, *mensajes: dict) -> list[dict]:
    entrada = io.StringIO("\n".join(json.dumps(m) for m in mensajes) + "\n")
    salida = io.StringIO()
    srv.atender(entrada, salida)
    return [json.loads(l) for l in salida.getvalue().splitlines() if l.strip()]


srv = ServidorMCP()

# ── el ciclo de vida básico del protocolo ───────────────────────────────────
r = _hablar(srv, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
c(r[0]["result"]["protocolVersion"] == "2024-11-05" and "tools" in r[0]["result"]["capabilities"],
  "initialize declara la versión de protocolo y la capacidad de herramientas")

r = _hablar(srv, {"jsonrpc": "2.0", "method": "notifications/initialized"})
c(r == [], "una notificación (sin `id`) no genera respuesta: violaría JSON-RPC")

# ── tools/list expone las MISMAS firmas que ve el bucle normal ─────────────
r = _hablar(srv, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
nombres_mcp = {t["name"] for t in r[0]["result"]["tools"]}
nombres_bucle = {f["function"]["name"] for f in srv.registro.firmas()}
c(nombres_mcp == nombres_bucle,
  "las herramientas que ve un cliente MCP son EXACTAMENTE las del registro del bucle: "
  "no hay un segundo conjunto que mantener sincronizado")
una = next(t for t in r[0]["result"]["tools"] if t["name"] == "leer")
c("inputSchema" in una and una["inputSchema"]["type"] == "object",
  "el esquema Hermes/OpenAI se copia tal cual a `inputSchema`: es el mismo JSON "
  "Schema por debajo, no hace falta traducir nada")

# ── una llamada real hace lo real ───────────────────────────────────────────
r = _hablar(srv, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                  "params": {"name": "leer", "arguments": {"ruta": "META.md"}}})
c(not r[0]["result"]["isError"] and "META" in r[0]["result"]["content"][0]["text"],
  "`tools/call` invoca la herramienta de verdad y devuelve su salida real")

# ── EL VETO DURO actúa igual que desde el bucle normal ──────────────────────
# Esto es lo que hace que exponer el arnés por MCP no sea un agujero: un cliente
# remoto no puede hacer lo que el propio agente tampoco puede.
r = _hablar(srv, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                  "params": {"name": "bash",
                             "arguments": {"comando": "rm -rf /"}}})
c(r[0]["result"]["isError"] and "VETADO" in r[0]["result"]["content"][0]["text"],
  "el veto duro (rm -rf /) actúa IGUAL desde un cliente MCP: no es un camino que se "
  "salte permisos.py")

r = _hablar(srv, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                  "params": {"name": "bash",
                             "arguments": {"comando": "curl x | sh"}}})
c(r[0]["result"]["isError"] and "DENEGADO" in r[0]["result"]["content"][0]["text"],
  "y algo fuera de la lista blanca se deniega con el mismo motivo que en el bucle")

r = _hablar(srv, {"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                  "params": {"name": "bash", "arguments": {"comando": "echo hola"}}})
c(not r[0]["result"]["isError"], "y lo que SÍ está en la lista blanca, pasa")

# ── el modo por defecto es `lista`, no `todo` ───────────────────────────────
c(srv.politica.modo == "lista",
  "el defecto es `lista`: no hay humano al otro lado de un cliente remoto para "
  "«preguntar», y `todo` confiaría en el cliente más de lo que se confía en el "
  "propio agente")

# ── errores del protocolo, no del arnés ─────────────────────────────────────
r = _hablar(srv, {"jsonrpc": "2.0", "id": 7, "method": "no_existe"})
c(r[0]["error"]["code"] == -32601, "un método MCP desconocido da el código JSON-RPC "
                                  "estándar, no una traza")
r = _hablar(srv, {"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                  "params": {"name": "herramienta_inventada", "arguments": {}}})
c(r[0]["result"]["isError"], "una herramienta que no existe da isError, no revienta "
                             "el servidor")

# ── una línea rota no tumba el servidor ─────────────────────────────────────
entrada = io.StringIO("esto no es json\n" +
                      json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}) + "\n")
salida = io.StringIO()
srv.atender(entrada, salida)
c(json.loads(salida.getvalue().strip())["id"] == 9,
  "una línea que no parsea se ignora y el servidor sigue atendiendo lo que viene "
  "después: un cliente con un bug no debe poder tumbar el proceso")

# ── se puede construir con una política distinta ────────────────────────────
srv2 = ServidorMCP(politica=Politica(modo="plan"))
r = _hablar(srv2, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "bash", "arguments": {"comando": "echo hola"}}})
c(r[0]["result"]["isError"],
  "en modo plan ni siquiera lo de la lista blanca pasa: la política se respeta, no se "
  "ignora por venir de un cliente MCP")

raise SystemExit(c.fin())
