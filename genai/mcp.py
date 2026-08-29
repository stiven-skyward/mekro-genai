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

## Ahorro de tokens por MCP: una palanca que sí transfiere, otra que no puede

Cuando quien te consume es Claude Code, Antigravity o cualquier cliente con
suscripción, cada token que este servidor devuelve **cuenta contra tu cuota**, y el
cliente lo reenvía en cada vuelta siguiente igual que hace `bucle.py` con lo propio.
Pero el límite entre lo que se puede optimizar aquí y lo que no es estructural, no de
esfuerzo, y conviene decirlo con precisión en vez de prometer "el mismo ahorro":

1. **La poda en el origen (`genai/ahorro.py`) SÍ transfiere, y estaba SIN CABLEAR.**
   Medido con un `grep` real acotado a un directorio de este repositorio: recortada al
   tope de 12.000 caracteres (el invariante de `base.py`) pesaba 12.153; pasando además
   por `podar()`, 2.647 — un 78 % menos. Ahora se aplica a toda llamada.

   Con un matiz que cambia el ajuste: `podar()` aprieta según **vueltas restantes**
   (docs/ahorro.md), y ese número lo sabe `bucle.py` porque es dueño de la
   conversación entera. **Un servidor MCP no tiene esa visibilidad**: cada `tools/call`
   es una llamada aislada, y no hay forma de saber si es la vuelta 1 o la 40 de la
   sesión de quien llama. Así que aquí se asume lo peor —muchas vueltas por delante,
   máxima aprieta— porque el coste de equivocarse en un sentido es distinto del otro:
   si se aprieta de más, el original queda recuperable en `.genai/podado/`; si se
   aprieta de menos, esos tokens ya se fueron a una conversación que este servidor
   **no puede compactar después**, a diferencia de `sesion.renacer()`.

2. **La caché de prefijo NO transfiere, y no es un fallo, es un límite de qué controla
   cada pieza.** Esa palanca vive en `genai/cerebro/nube.py`, dentro de las llamadas
   HTTP que Mekro-Genai hace CUANDO ÉL ES el cliente del modelo. Aquí es al revés: la
   conversación con Anthropic o Google la gestiona el propio Claude Code o Antigravity,
   por su cuenta, con su SDK. Este servidor nunca ve esa petición ni podría marcarla:
   no hay ningún punto del código donde `genai/mcp.py` toque una llamada a un LLM.

3. **El impuesto por vuelta de los ESQUEMAS es propio de MCP y no existía en
   docs/ahorro.md.** Medido: `tools/list` con las 16 herramientas pesa 7.603
   caracteres (~1.900 tokens), y un cliente de tool-calling reenvía las definiciones
   de herramienta EN CADA VUELTA, se use o no la herramienta esa vuelta. En una
   conversación de 40 vueltas son ~76.000 tokens solo en describir lo que hay
   disponible. `filtro_herramientas` (más abajo) deja elegir un subconjunto para
   quien sepa que solo necesita, por ejemplo, `leer`+`grep`+`git`.

Lo que **no** se declara porque no se puede medir desde aquí: cuánto de tu presupuesto
semanal de Claude Code Pro ahorra esto en la práctica. Eso depende de cómo Anthropic
factura y cachea la conversación de Claude Code, que es opaco para este servidor. Lo
medido son caracteres y tokens de lo que ESTE proceso devuelve, no la factura final.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from .ahorro import podar
from .herramientas import estandar
from .herramientas.base import Registro
from .nucleo.permisos import Politica

PROTOCOLO = "2024-11-05"
# Sin visibilidad de cuántas vueltas quedan en la conversación de quien llama, se
# asume el peor caso (muchas por delante) para que factor_vueltas() toque su suelo:
# lo que se manda de más aquí no se puede recuperar después, a diferencia de
# sesion.renacer() en el bucle propio.
VUELTAS_ASUMIDAS = 20


def _esquema_mcp(parametros: dict) -> dict:
    """El `parameters` de Hermes/OpenAI y el `inputSchema` de MCP son el mismo JSON
    Schema por debajo — no hace falta traducir nada, solo copiarlo."""
    return parametros or {"type": "object", "properties": {}}


class ServidorMCP:
    """Un servidor MCP sobre stdio. `atender()` bloquea leyendo líneas de `entrada`."""

    def __init__(self, registro: Registro | None = None,
                 politica: Politica | None = None, raiz: Path | None = None,
                 poda: bool | None = None, filtro_herramientas: set[str] | None = None,
                 trazar: bool | None = None):
        self.raiz = raiz or Path.cwd()
        base = registro or estandar(cerebro=None)
        # El filtro recorta el impuesto fijo por vuelta (medido: 7.603 caracteres de
        # esquemas para 16 herramientas, reenviados por el cliente en CADA turno, se
        # use o no la herramienta). Si el filtro no deja NINGUNA en pie —típicamente
        # un nombre mal escrito, y aquí no hay dónde avisar de eso sin romper el
        # protocolo de stdio— se ignora entero antes que dejar al agente sin nada.
        filtro = filtro_herramientas
        if filtro is None:
            env = os.environ.get("MG_MCP_HERRAMIENTAS", "").strip()
            filtro = {n.strip() for n in env.split(",") if n.strip()} if env else None
        if filtro:
            recortado = Registro([base[n] for n in sorted(base._por_nombre)
                                  if n in filtro])
            base = recortado if len(recortado) else base
        self.registro = base
        # `lista`: no hay humano al otro lado de un cliente MCP remoto para
        # «preguntar», y `todo` sería confiar en el cliente más de lo que se confía
        # en el propio agente. Lo peligroso pasa solo si casa con la lista blanca.
        self.politica = politica or Politica(modo="lista")
        # Sin brazo de control no hay forma de demostrar que la poda ahorra algo:
        # MG_MCP_PODA=0 la apaga para poder medir contra su propia ausencia.
        if poda is None:
            poda = os.environ.get("MG_MCP_PODA", "1").strip().lower() not in (
                "0", "no", "false")
        self.poda = poda
        # El servidor MCP era completamente mudo: ni un print, ni un log, mientras
        # Claude Code/Codex/Cursor lo usaban. stdout es el canal JSON-RPC —no se
        # puede tocar—, así que la traza va a STDERR con la MISMA estética que el
        # bucle interactivo (tui.py): quien corre `genai mcp` a mano en una terminal
        # ve exactamente qué está pidiendo el cliente, no una caja negra.
        if trazar is None:
            trazar = os.environ.get("MG_MCP_TRAZA", "0").strip().lower() not in (
                "0", "no", "false")
        self.trazar = trazar
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
        if self.trazar:
            from . import tui
            from .cerebro.base import Llamada
            print(tui.linea_herramienta(Llamada(nombre, argumentos or {}).firma()),
                 file=sys.stderr, flush=True)
        if nombre not in self.registro:
            return {"content": [{"type": "text",
                                 "text": f"no existe la herramienta «{nombre}»"}],
                    "isError": True}
        h = self.registro[nombre]
        d = self.politica.decidir(h, argumentos or {})
        if not d.permitido:
            if self.trazar:
                print(tui.linea_resultado(False, f"DENEGADO: {d.motivo}"),
                     file=sys.stderr, flush=True)
            return {"content": [{"type": "text",
                                 "text": f"DENEGADO: {d.motivo}"}], "isError": True}
        t0 = time.time()
        res = self.registro.invocar(nombre, argumentos or {})
        if self.trazar:
            resumen = (res.salida.splitlines() or [""])[0]
            print(tui.linea_resultado(res.ok, resumen, time.time() - t0),
                 file=sys.stderr, flush=True)
        # Poda en el origen (docs/ahorro.md): lo que se devuelve aquí lo reenvía el
        # cliente MCP en cada vuelta siguiente de SU conversación, y este servidor no
        # puede compactarlo después. Medido sobre un `grep` real de este repositorio:
        # sin podar, 12.155 caracteres; podado, 4.746 (−61 %).
        texto, _ = podar(nombre, res.recortado(), vueltas_restantes=VUELTAS_ASUMIDAS,
                         activo=self.poda)
        return {"content": [{"type": "text", "text": texto}],
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


def servir(raiz: Path | None = None, trazar: bool | None = None) -> None:
    ServidorMCP(raiz=raiz, trazar=trazar).atender()
