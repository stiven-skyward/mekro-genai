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
    "antigravity": {
        "nombre": "Google Antigravity",
        "binario": None,
        "verificado": None,  # se sabe que admite MCP (MCP Store, mcp_config.json);
        # no se ha ejecutado ninguna instalación desde aquí
        "instrucciones": ("Antigravity lee `mcp_config.json` con el mismo fragmento "
                          "JSON genérico de `json_generico()`. No se ha probado la "
                          "ruta exacta del fichero en esta máquina."),
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
    if not c.get("comando"):
        fragmento = json.dumps(json_generico(nombre), indent=2, ensure_ascii=False)
        return False, f"{c['nombre']}: {c['instrucciones']}\n\n  {fragmento}"
    if not detectado(clave):
        return False, (f"no encuentro «{c['binario']}» en el PATH. Instala "
                       f"{c['nombre']} primero.")
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
    if not c or not c.get("quitar"):
        return False, f"no hay una orden de desinstalación automática para «{clave}»"
    try:
        r = subprocess.run(c["quitar"](nombre), capture_output=True, text=True,
                           timeout=30)
    except OSError as e:
        return False, f"no se pudo ejecutar: {e}"
    return r.returncode == 0, (r.stdout or r.stderr or "").strip()
