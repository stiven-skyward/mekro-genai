"""Mekro-Genai como servidor MCP: tu suscripción usando el arnés, no al revés.

**Por qué existe.** No hay forma legítima de que Mekro-Genai gaste la cuota de una
suscripción de consumidor (Google AI Pro/Ultra) por API: esa cuota vive dentro de las
apps de Google —Gemini, Antigravity— y la API programática es un producto de
facturación distinto (ver docs/nube.md, medido con cuenta real 2026-08-28). Intentar
saltarse eso imitando una sesión de navegador es exactamente el patrón que los
controles de abuso de cualquier proveedor existen para detectar, y no es lo que hace
este módulo.

Lo que SÍ es legítimo y funciona hoy: exponer las **herramientas** de Mekro-Genai por el
protocolo abierto que los clientes de escritorio ya hablan —Antigravity, Claude
Desktop, cualquier cliente MCP—, para que el modelo que tú ya pagas (dentro de SU
cliente, bajo SUS reglas) pueda usarlas. La dirección del mando se invierte: no es
Mekro-Genai pidiéndole texto a Gemini, es Gemini pidiéndole a Mekro-Genai que lea un
fichero o corra la suite.

**Protocolo, no biblioteca.** MCP es JSON-RPC 2.0 con streaming de línea sobre stdio —
la misma familia de diseño que `genai/lsp.py` ya usa para hablar con servidores de
lenguaje, aquí en el otro sentido: este proceso ES el servidor. Cabe en un fichero y no
añade dependencias.

**Pasa por el mismo `Registro` y la misma `Politica` que el bucle normal.** Un cliente
MCP no es más de fiar que el propio agente: `bash`, `escribir`, `editar` siguen pasando
por `permisos.py`. Por defecto el modo es `lista` —lo peligroso se permite solo si casa
con la lista blanca— porque no hay una consola donde "preguntar" tenga sentido cuando
quien llama es un cliente remoto.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from .herramientas import estandar
from .herramientas.base import Registro
from .nucleo.permisos import Politica

PROTOCOLO = "2024-11-05"


def _esquema_mcp(parametros: dict) -> dict:
    """El `parameters` de Hermes/OpenAI y el `inputSchema` de MCP son el mismo JSON
    Schema por debajo — no hace falta traducir nada, solo copiarlo."""
    return parametros or {"type": "object", "properties": {}}


class ServidorMCP:
    """Un servidor MCP sobre stdio. `atender()` bloquea leyendo líneas de `entrada`."""

    def __init__(self, registro: Registro | None = None,
                 politica: Politica | None = None, raiz: Path | None = None):
        self.raiz = raiz or Path.cwd()
        self.registro = registro or estandar(cerebro=None)
        # `lista`: no hay humano al otro lado de un cliente MCP remoto para
        # «preguntar», y `todo` sería confiar en el cliente más de lo que se confía
        # en el propio agente. Lo peligroso pasa solo si casa con la lista blanca.
        self.politica = politica or Politica(modo="lista")
        self._vivo = True

    # ── protocolo ──────────────────────────────────────────────────────────
    def _herramientas_mcp(self) -> list[dict]:
        fuera = []
        for firma in self.registro.firmas():
            f = firma["function"]
            fuera.append({"name": f["name"], "description": f["description"],
                          "inputSchema": _esquema_mcp(f.get("parameters"))})
        return fuera

    def _llamar(self, nombre: str, argumentos: dict) -> dict:
        """Invoca una herramienta pasando por la MISMA política que el bucle normal.
        Un cliente MCP no es más de fiar que el propio agente."""
        if nombre not in self.registro:
            return {"content": [{"type": "text",
                                 "text": f"no existe la herramienta «{nombre}»"}],
                    "isError": True}
        h = self.registro[nombre]
        d = self.politica.decidir(h, argumentos or {})
        if not d.permitido:
            return {"content": [{"type": "text",
                                 "text": f"DENEGADO: {d.motivo}"}], "isError": True}
        res = self.registro.invocar(nombre, argumentos or {})
        return {"content": [{"type": "text", "text": res.recortado()}],
                "isError": not res.ok}

    def _manejar(self, msg: dict) -> dict | None:
        metodo, ident = msg.get("method"), msg.get("id")
        params = msg.get("params") or {}

        if metodo == "initialize":
            return self._resp(ident, {
                "protocolVersion": PROTOCOLO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mekro-genai",
                               "version": "0.1.0"}})
        if metodo == "notifications/initialized":
            return None                        # notificación: sin respuesta
        if metodo == "tools/list":
            return self._resp(ident, {"tools": self._herramientas_mcp()})
        if metodo == "tools/call":
            r = self._llamar(params.get("name", ""), params.get("arguments") or {})
            return self._resp(ident, r)
        if metodo == "ping":
            return self._resp(ident, {})
        if ident is None:
            return None                        # otra notificación desconocida: se ignora
        return self._resp(ident, None, error={"code": -32601,
                                              "message": f"método desconocido: {metodo}"})

    @staticmethod
    def _resp(ident, result, error=None) -> dict:
        if error is not None:
            return {"jsonrpc": "2.0", "id": ident, "error": error}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    # ── bucle de E/S ───────────────────────────────────────────────────────
    def atender(self, entrada=None, salida=None) -> None:
        entrada = entrada or sys.stdin
        salida = salida or sys.stdout
        for linea in entrada:
            linea = linea.strip()
            if not linea:
                continue
            try:
                msg = json.loads(linea)
            except ValueError:
                continue                       # una línea rota no tumba el servidor
            resp = self._manejar(msg)
            if resp is not None:
                salida.write(json.dumps(resp, ensure_ascii=False) + "\n")
                salida.flush()
            if not self._vivo:
                break

    def parar(self) -> None:
        self._vivo = False


def servir(raiz: Path | None = None) -> None:
    ServidorMCP(raiz=raiz).atender()
