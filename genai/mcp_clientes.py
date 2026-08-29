"""Registro de clientes MCP conocidos: cómo enchufar Mekro-Genai a cada uno.

**El porqué de este fichero.** Después de probar Claude Code, Codex y de investigar
Antigravity y Kimi Code CLI, quedó claro que había tres caminos distintos para traer un
cerebro de nube, no uno — y el usuario decide cuál, no el arnés. Este módulo es el
menú, y `docs/nube.md §Tres caminos` es su explicación larga.

**Solo lo probado de verdad lleva un comando ejecutable.** Claude Code y Codex se
verificaron esta sesión con cuentas reales: `claude mcp add` y `codex mcp add`
funcionan, y las llamadas llegaron y volvieron con datos reales. Antigravity y Kimi
Code CLI se SABE que hablan MCP —está documentado, no es una suposición— pero su
sintaxis de instalación no se ha ejecutado ni una vez desde aquí. Inventar el comando
exacto de un CLI que no se ha probado es peor que no darlo: un comando que falla a
medias puede dejar una configuración rota que cuesta más deshacer que escribir a mano
el JSON genérico que sí se sabe correcto (MCP es un protocolo abierto: el fragmento
`{"mcpServers": {...}}` vale para cualquier cliente que lo lea, probado o no).

**Sobre el tercer camino que NO está aquí y no va a estarlo.** Para OpenAI y Anthropic
no hay una «suscripción directa» (`genai openai entrar`, `genai claude entrar`) al
estilo de `genai/copilot.py` o `genai/google_cuenta.py`. No es un olvido: extraer el
token de sesión de Codex o de Claude Code para que Mekro-Genai lo use COMO SI FUERA esas
herramientas, sustituyendo su propio bucle de agente, es repurposar una credencial fuera
del cliente para el que se emitió — la misma categoría que rechazar extraer cookies del
navegador para Gemini, solo que con OAuth en vez de cookies. El mecanismo cambia; el
límite no. Por eso Claude Code y Codex están en este fichero **solo como clientes MCP**
(su propio bucle de agente sigue siendo el suyo, Mekro-Genai les presta herramientas) y
nunca como cerebro-de-nube-por-suscripción.

Copilot y Google sí tienen módulo de suscripción directa porque el mecanismo es
distinto: GitHub documenta oficialmente el device flow para editores de terceros —es
la base misma de que Copilot funcione en Neovim, JetBrains, etc., no una extracción—, y
con Google se hizo el intento de buena fe con las credenciales oficiales de `gemini-cli`
y SE MIDIÓ que el nivel gratuito para individuos está cerrado (`nube.md`, C86).
"""
from __future__ import annotations

import json
import shutil
import subprocess

PROCESO = ["python3", "-m", "genai.cli", "mcp"]


def _claude_add(nombre: str) -> list[str]:
    return ["claude", "mcp", "add", nombre, "--", *PROCESO]


def _claude_quitar(nombre: str) -> list[str]:
    return ["claude", "mcp", "remove", nombre]


def _codex_add(nombre: str) -> list[str]:
    return ["codex", "mcp", "add", nombre, "--", *PROCESO]


def _codex_quitar(nombre: str) -> list[str]:
    return ["codex", "mcp", "remove", nombre]


def _cursor_instalar(nombre: str) -> tuple[bool, str]:
    """Cursor no tiene `mcp add`: los servidores se declaran en `.cursor/mcp.json` del
    proyecto y se aprueban con `cursor-agent mcp enable`. Se lee el fichero si ya
    existe —para no borrar otros servidores que el usuario tenga puestos— y solo se
    añade la entrada propia."""
    from pathlib import Path
    f = Path(".cursor") / "mcp.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if f.is_file():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return False, f"{f} existe pero no es JSON válido; arréglalo a mano primero"
    cfg.setdefault("mcpServers", {})[nombre] = {"command": "python3",
                                                "args": ["-m", "genai.cli", "mcp"]}
    f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        r = subprocess.run(["cursor-agent", "mcp", "enable", nombre],
                           capture_output=True, text=True, timeout=30)
    except OSError as e:
        return False, f"escribí {f}, pero no pude ejecutar cursor-agent: {e}"
    if r.returncode != 0:
        return False, (f"escribí {f}, pero `mcp enable` falló: "
                       f"{(r.stderr or r.stdout).strip()}")
    return True, (r.stdout or "habilitado").strip()


def _antigravity_instalar(nombre: str) -> tuple[bool, str]:
    """Antigravity IDE lee `.agents/mcp_config.json` en el proyecto (o
    `~/.gemini/config/mcp_config.json` en global) — verificado contra la
    documentación oficial (antigravity.google/docs/ide/mcp/, revisado
    2026-08-29): raíz `mcpServers`, cada entrada con `command`/`args`/`env`/`cwd`.
    Se usa la ruta de PROYECTO, igual que Cursor: no toca nada fuera de este
    directorio. Se lee el fichero si ya existe, para no borrar otros servidores
    que el usuario tenga puestos. Lo que esto NO tiene, a diferencia de Cursor,
    es una llamada MCP real de vuelta que confirme que Antigravity de verdad lo
    lee — la ruta y el formato están verificados por escrito, el efecto en vivo
    no."""
    from pathlib import Path
    f = Path(".agents") / "mcp_config.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if f.is_file():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return False, f"{f} existe pero no es JSON válido; arréglalo a mano primero"
    cfg.setdefault("mcpServers", {})[nombre] = {"command": "python3",
                                                "args": ["-m", "genai.cli", "mcp"]}
    f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, f"escribí {f} — abre Antigravity en este proyecto para verlo"


def _antigravity_quitar(nombre: str) -> tuple[bool, str]:
    from pathlib import Path
    f = Path(".agents") / "mcp_config.json"
    if f.is_file():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
            cfg.get("mcpServers", {}).pop(nombre, None)
            f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except ValueError:
            pass
    return True, f"quitado de {f}"


def _cursor_quitar(nombre: str) -> tuple[bool, str]:
    from pathlib import Path
    f = Path(".cursor") / "mcp.json"
    if f.is_file():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
            cfg.get("mcpServers", {}).pop(nombre, None)
            f.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except ValueError:
            pass
    try:
        subprocess.run(["cursor-agent", "mcp", "disable", nombre],
                       capture_output=True, text=True, timeout=30)
    except OSError:
        pass
    return True, f"quitado de {f}"


# Cada entrada dice de qué tipo de cosa se trata («cliente MCP», nunca «cerebro de
# suscripción») y si `verificado` es True lleva `comando`/`quitar` ejecutables.
CLIENTES: dict[str, dict] = {
    "claude-code": {
        "nombre": "Claude Code",
        "binario": "claude",
        "verificado": "probado con cuenta real 2026-08-28: tools/call contra `git log` "
                      "y veto de `rm -rf /`, ambos correctos",
        "comando": _claude_add, "quitar": _claude_quitar,
    },
    "codex": {
        "nombre": "Codex CLI (OpenAI, con login de ChatGPT Plus/Pro)",
        "binario": "codex",
        "verificado": "probado con cuenta real 2026-08-28: `codex exec --approve-for-me` "
                      "llamó a `git` por MCP y devolvió el log real, gastando la "
                      "suscripción y no una clave de API aparte",
        "comando": _codex_add, "quitar": _codex_quitar,
    },
    "cursor": {
        "nombre": "Cursor (cursor-agent)",
        "binario": "cursor-agent",
        "verificado": ("probado con cuenta real y con clave 2026-08-28: `mcp list-tools` "
                      "vio las 16 herramientas, y `cursor-agent --api-key ... -p` llamó "
                      "a `git` por MCP y devolvió el log real de este repositorio. "
                      "Admite las DOS autenticaciones de forma nativa — "
                      "`cursor-agent login` (cuenta, navegador) o "
                      "`--api-key`/`CURSOR_API_KEY` (token) — la elección es de "
                      "cursor-agent, no de este registro"),
        # No hay `mcp add`: se escribe .cursor/mcp.json y se aprueba con `mcp enable`.
        "instalador": _cursor_instalar, "desinstalador": _cursor_quitar,
    },
    "antigravity": {
        "nombre": "Google Antigravity",
        "binario": None,
        # La RUTA y el FORMATO están verificados por escrito (documentación
        # oficial, antigravity.google/docs/ide/mcp/, 2026-08-29) y el instalador
        # ya escribe `.agents/mcp_config.json` de verdad. Sigue en `None` porque
        # falta lo que SÍ tienen Claude Code/Codex/Cursor: una llamada MCP real
        # de vuelta que confirme que Antigravity de verdad lo lee y llama a una
        # herramienta. Documentación verificada ≠ efecto en vivo comprobado.
        "verificado": None,
        "instrucciones": ("`genai mcp instalar antigravity` YA escribe "
                          "`.agents/mcp_config.json` (ruta y formato verificados "
                          "por la documentación oficial de Google) — lo que falta "
                          "es que alguien abra Antigravity apuntando aquí y "
                          "confirme que de verdad llama a una herramienta."),
        "instalador": _antigravity_instalar, "desinstalador": _antigravity_quitar,
    },
    "kimi-code": {
        "nombre": "Kimi Code CLI (Moonshot, con membresía de Kimi)",
        "binario": "kimi",
        "verificado": None,  # se sabe que admite MCP vía `/mcp-config`; no se ha
        # probado si acepta el mismo JSON o exige otro formato
        "instrucciones": ("Kimi Code CLI se configura con `/mcp-config` dentro de su "
                          "propia sesión, o su fichero de configuración. Revisa su "
                          "documentación: la sintaxis exacta no se ha probado desde "
                          "aquí, a diferencia de Claude Code y Codex."),
    },
}


def json_generico(nombre: str = "mekro-genai", cwd: str = ".") -> dict:
    """El fragmento que sirve para CUALQUIER cliente MCP que lea configuración JSON,
    probado o no: MCP es un protocolo abierto y esta forma no depende de ninguno."""
    return {"mcpServers": {nombre: {"command": "python3",
                                    "args": ["-m", "genai.cli", "mcp"], "cwd": cwd}}}


def detectado(clave: str) -> bool:
    binario = CLIENTES.get(clave, {}).get("binario")
    return bool(binario and shutil.which(binario))


def instalar(clave: str, nombre: str = "mekro-genai") -> tuple[bool, str]:
    c = CLIENTES.get(clave)
    if not c:
        return False, (f"no conozco «{clave}». Conocidos: {', '.join(CLIENTES)}. "
                       f"Para cualquier otro, usa el fragmento JSON genérico "
                       f"(`json_generico()`) y la documentación del cliente.")
    if not c.get("comando") and not c.get("instalador"):
        fragmento = json.dumps(json_generico(nombre), indent=2, ensure_ascii=False)
        return False, f"{c['nombre']}: {c['instrucciones']}\n\n  {fragmento}"
    # sin binario que buscar (Antigravity es una IDE, no un CLI en el PATH) no hay
    # nada que este chequeo pueda decir con sentido — se salta, no se inventa un
    # "no encontrado" para algo que nunca tuvo forma de detectarse.
    if c.get("binario") and not detectado(clave):
        return False, (f"no encuentro «{c['binario']}» en el PATH. Instala "
                       f"{c['nombre']} primero.")
    if c.get("instalador"):
        # Clientes sin `mcp add` (Cursor: se configura por fichero, no por subcomando)
        # llevan su propia función de instalación completa.
        return c["instalador"](nombre)
    orden = c["comando"](nombre)
    try:
        r = subprocess.run(orden, capture_output=True, text=True, timeout=30)
    except OSError as e:
        return False, f"no se pudo ejecutar {' '.join(orden)}: {e}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "falló sin más detalle").strip()
    return True, (r.stdout or "hecho").strip()


def quitar(clave: str, nombre: str = "mekro-genai") -> tuple[bool, str]:
    c = CLIENTES.get(clave)
    if not c or not (c.get("quitar") or c.get("desinstalador")):
        return False, f"no hay una orden de desinstalación automática para «{clave}»"
    if c.get("desinstalador"):
        return c["desinstalador"](nombre)
    try:
        r = subprocess.run(c["quitar"](nombre), capture_output=True, text=True,
                           timeout=30)
    except OSError as e:
        return False, f"no se pudo ejecutar: {e}"
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()
