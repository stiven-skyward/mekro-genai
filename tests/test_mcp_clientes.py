"""El menú de clientes MCP: qué está probado de verdad y qué no.

Lo que se vigila, sin depender de que `claude` ni `codex` estén instalados en la
máquina que corre la prueba:

1. que **solo lo verificado esta sesión** (Claude Code, Codex) lleve un comando
   ejecutable; lo demás (Antigravity, Kimi Code CLI) da instrucciones y el fragmento
   JSON genérico, nunca una sintaxis inventada;
2. que un binario ausente, un cliente desconocido o un cliente sin comando se digan
   con claridad y no revienten;
3. que **no exista** un camino de "suscripción directa" para OpenAI ni Anthropic —
   es la línea que se decidió no cruzar, y tiene que seguir sin cruzarse mañana.
"""
import json

from _util import Cuenta

from genai.mcp_clientes import CLIENTES, detectado, instalar, json_generico, quitar

c = Cuenta("mcp_clientes")

# ── el registro, coherente consigo mismo ────────────────────────────────────
for clave, cl in CLIENTES.items():
    if cl.get("verificado"):
        c(callable(cl.get("comando")) and callable(cl.get("quitar")),
          f"[{clave}] verificado lleva comando Y quitar ejecutables")
        c(bool(cl.get("binario")),
          f"[{clave}] verificado dice qué binario detectar")
    else:
        c(cl.get("comando") is None,
          f"[{clave}] SIN verificar no ofrece un comando: inventar la sintaxis de un "
          f"CLI no probado es peor que no darla — un comando a medias puede dejar "
          f"config rota")
        c(bool(cl.get("instrucciones")),
          f"[{clave}] sin comando, al menos explica qué hacer a mano")

# ── el fragmento genérico sirve para cualquiera, probado o no ──────────────
j = json_generico("mi-servidor", "/algun/proyecto")
c(j["mcpServers"]["mi-servidor"]["args"] == ["-m", "genai.cli", "mcp"],
  "el fragmento genérico invoca exactamente `python3 -m genai.cli mcp`")
c(j["mcpServers"]["mi-servidor"]["cwd"] == "/algun/proyecto",
  "y respeta el directorio de proyecto que se le pida")
c(json.loads(json.dumps(j)) == j, "es JSON válido de verdad, no solo un dict con esa forma")

# ── detección: no revienta si el binario no existe ──────────────────────────
c(detectado("claude-code") in (True, False), "detectado() nunca revienta, exista o no")
c(not detectado("antigravity"),
  "un cliente sin binario propio (se configura por fichero) nunca se da por detectado")

# ── instalar: los tres casos degenerados ────────────────────────────────────
ok, msg = instalar("no-existe-este-cliente")
c(not ok and "no conozco" in msg and "claude-code" in msg,
  "un cliente desconocido se dice, y la lista de conocidos sale en el propio mensaje")

ok, msg = instalar("antigravity")
c(not ok and "mcp_config.json" in msg and "mcpServers" in msg,
  "un cliente sin comando (Antigravity) da las instrucciones Y el JSON genérico "
  "pegado, para no obligar a ir a buscarlo aparte")

# forzar «no detectado» sin depender de si el binario existe en esta máquina
import genai.mcp_clientes as MC  # noqa: E402

_orig_which = MC.shutil.which
MC.shutil.which = lambda _n: None
ok, msg = instalar("claude-code")
c(not ok and "no encuentro" in msg and "claude" in msg,
  "sin el binario en el PATH, se dice cuál falta en vez de intentar ejecutarlo a ciegas")
MC.shutil.which = _orig_which

# instalar/quitar con un subprocess de mentira, para no depender de tener el CLI real
_orig_run = MC.subprocess.run


class _Resultado:
    def __init__(self, cod=0, out="hecho", err=""):
        self.returncode, self.stdout, self.stderr = cod, out, err


ordenes_vistas = []


def _run_falso(orden, **kw):
    ordenes_vistas.append(orden)
    return _Resultado()


MC.shutil.which = lambda _n: "/usr/bin/claude"
MC.subprocess.run = _run_falso
ok, msg = instalar("claude-code", nombre="prueba-x")
c(ok and msg == "hecho", "con el binario presente y el subproceso en verde, instala")
c(ordenes_vistas[-1][:3] == ["claude", "mcp", "add"] and "prueba-x" in ordenes_vistas[-1],
  "y la orden real construida es la que se documentó, con el nombre pedido")
c(ordenes_vistas[-1][-3:] == ["-m", "genai.cli", "mcp"],
  "terminando siempre en el mismo proceso servidor, `python3 -m genai.cli mcp`")

ok, _ = quitar("claude-code", nombre="prueba-x")
c(ok and ordenes_vistas[-1] == ["claude", "mcp", "remove", "prueba-x"],
  "quitar construye la orden de desinstalación simétrica")

MC.subprocess.run = lambda *a, **k: _Resultado(1, "", "algo falló")
ok, msg = instalar("claude-code")
c(not ok and "algo falló" in msg,
  "si el propio CLI falla, se propaga su motivo en vez de decir solo «no funcionó»")

MC.shutil.which = _orig_which
MC.subprocess.run = _orig_run

c(quitar("antigravity")[0] is False,
  "un cliente sin comando de desinstalación lo dice, no finge haber quitado algo")

# ── la línea que no se cruza: sin suscripción directa para OpenAI ni Anthropic ──
c(not any(k in CLIENTES for k in ("openai", "chatgpt", "anthropic", "claude")),
  "no hay entradas 'openai'/'anthropic' aquí bajo ningún nombre: los dos únicos "
  "clientes de estos proveedores en el registro son de tipo MCP (su propio agente "
  "sigue siendo el suyo), nunca un cerebro-por-suscripción-directa")
fuente = __import__("pathlib").Path(
    "genai/mcp_clientes.py").read_text(encoding="utf-8")
c("repurposear" in fuente.lower() or "extraer" in fuente.lower(),
  "y el módulo explica POR QUÉ, no solo omite: la razón está escrita, no es un vacío "
  "que alguien podría rellenar después sin darse cuenta de que fue a propósito")

raise SystemExit(c.fin())
