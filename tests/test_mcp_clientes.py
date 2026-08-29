"""El menú de clientes MCP: qué está probado de verdad y qué no.

Lo que se vigila, sin depender de que `claude`, `codex` ni `cursor-agent` estén
instalados en la máquina que corre la prueba:

1. que **solo lo verificado esta sesión** (Claude Code, Codex, Cursor) lleve una
   instalación ejecutable —de subcomando (`mcp add`) o de fichero (Cursor no lo
   tiene)—; lo demás (Antigravity, Kimi Code CLI) da instrucciones y el fragmento
   JSON genérico, nunca una sintaxis inventada;
2. que un binario ausente, un cliente desconocido o un cliente sin comando se digan
   con claridad y no revienten;
3. que Cursor, al no tener `mcp add`, escriba `.cursor/mcp.json` sin destruir lo que
   ya hubiera ahí — un usuario con otros servidores MCP configurados no puede perderlos
   por instalar el nuestro;
4. que **no exista** un camino de "suscripción directa" para OpenAI ni Anthropic —
   es la línea que se decidió no cruzar, y tiene que seguir sin cruzarse mañana.
"""
import json
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.mcp_clientes import CLIENTES, detectado, instalar, json_generico, quitar

c = Cuenta("mcp_clientes")

# ── el registro, coherente consigo mismo ────────────────────────────────────
for clave, cl in CLIENTES.items():
    if cl.get("verificado") and cl.get("comando"):
        c(callable(cl.get("comando")) and callable(cl.get("quitar")),
          f"[{clave}] verificado por subcomando lleva comando Y quitar ejecutables")
        c(bool(cl.get("binario")),
          f"[{clave}] verificado dice qué binario detectar")
    elif cl.get("verificado"):
        c(callable(cl.get("instalador")) and callable(cl.get("desinstalador")),
          f"[{clave}] verificado sin `mcp add` lleva instalador/desinstalador propios "
          f"en vez de un comando inventado")
        c(bool(cl.get("binario")),
          f"[{clave}] también dice qué binario detectar")
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

ok, msg = instalar("kimi-code")
c(not ok and "mcp-config" in msg,
  "un cliente sin instalador (Kimi Code) da sus instrucciones tal cual, sin "
  "inventar una sintaxis que nadie ha probado")

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

c(quitar("kimi-code")[0] is False,
  "un cliente sin comando de desinstalación lo dice, no finge haber quitado algo")

# ── Cursor: se instala por FICHERO, no por `mcp add` ────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="cursor-inst-"))
antes_cwd = Path.cwd()

import genai.mcp_clientes as MC2  # noqa: E402

llamadas = []


def _run_falso_cursor(orden, **kw):
    llamadas.append(orden)
    return type("R", (), {"returncode": 0, "stdout": "habilitado", "stderr": ""})()


import os  # noqa: E402
os.chdir(tmp)
MC2.shutil.which = lambda n: "/usr/bin/cursor-agent" if n == "cursor-agent" else None
MC2.subprocess.run = _run_falso_cursor
try:
    ok, msg = instalar("cursor", nombre="mekro-genai")
    c(ok and msg == "habilitado", "cursor se instala sin `mcp add`: escribe el "
                                  "fichero y aprueba con `mcp enable`")
    cfg = json.loads((tmp / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    c(cfg["mcpServers"]["mekro-genai"]["args"] == ["-m", "genai.cli", "mcp"],
      "el fichero escrito apunta al mismo proceso servidor que los demás clientes")
    c(llamadas[-1] == ["cursor-agent", "mcp", "enable", "mekro-genai"],
      "y se aprueba con la orden real de cursor-agent")

    # otro servidor YA configurado no puede desaparecer por instalar el nuestro
    otro = json.loads((tmp / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    otro["mcpServers"]["otro-servidor"] = {"command": "algo"}
    (tmp / ".cursor" / "mcp.json").write_text(json.dumps(otro), encoding="utf-8")
    instalar("cursor", nombre="mekro-genai")
    final = json.loads((tmp / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    c("otro-servidor" in final["mcpServers"],
      "un servidor MCP que el usuario ya tenía configurado sobrevive a instalar el "
      "nuestro: el fichero se lee y se completa, nunca se sobrescribe entero")

    ok, msg = quitar("cursor", nombre="mekro-genai")
    tras_quitar = json.loads((tmp / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    c(ok and "mekro-genai" not in tras_quitar["mcpServers"],
      "quitar borra SOLO la entrada propia del fichero")
    c("otro-servidor" in tras_quitar["mcpServers"],
      "y sigue sin tocar lo que era de otro servidor")

    (tmp / ".cursor" / "mcp.json").write_text("esto no es json", encoding="utf-8")
    ok, msg = instalar("cursor")
    c(not ok and "no es JSON válido" in msg,
      "un mcp.json corrupto se dice en vez de sobrescribirlo a ciegas, perdiendo lo "
      "que hubiera dentro")
finally:
    os.chdir(antes_cwd)
    MC2.shutil.which = _orig_which
    MC2.subprocess.run = _orig_run

# ── Antigravity: ruta y formato verificados por la documentación oficial de ──
# Google (antigravity.google/docs/ide/mcp/, 2026-08-29) — sin binario que
# detectar (es una IDE, no un CLI en el PATH), así que no hace falta mockear
# `shutil.which`/`subprocess.run`: es solo escribir el fichero, como Cursor.
tmp2 = Path(tempfile.mkdtemp(prefix="antigravity-inst-"))
os.chdir(tmp2)
try:
    ok, msg = instalar("antigravity", nombre="mekro-genai")
    c(ok, f"antigravity SÍ se instala solo ahora, sin binario que verificar ({msg})")
    cfg = json.loads((tmp2 / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
    c(cfg["mcpServers"]["mekro-genai"]["command"] == "python3",
      "escribe .agents/mcp_config.json —la ruta de PROYECTO documentada— con el "
      "mismo proceso servidor que los demás clientes")

    otro = json.loads((tmp2 / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
    otro["mcpServers"]["otro-servidor"] = {"command": "algo"}
    (tmp2 / ".agents" / "mcp_config.json").write_text(json.dumps(otro), encoding="utf-8")
    instalar("antigravity", nombre="mekro-genai")
    final = json.loads((tmp2 / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
    c("otro-servidor" in final["mcpServers"],
      "un servidor que el usuario ya tenía configurado sobrevive a instalar el nuestro")

    ok, _ = quitar("antigravity", nombre="mekro-genai")
    tras = json.loads((tmp2 / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
    c(ok and "mekro-genai" not in tras["mcpServers"] and "otro-servidor" in tras["mcpServers"],
      "quitar borra solo la entrada propia, deja lo demás intacto")
finally:
    os.chdir(antes_cwd)

c(CLIENTES["antigravity"]["verificado"] is None,
  "pero sigue SIN marcarse «verificado»: la ruta y el formato están confirmados "
  "por escrito, no que Antigravity de verdad llame a una herramienta en vivo — "
  "esa es la barra que sí pasaron Claude Code, Codex y Cursor")

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
