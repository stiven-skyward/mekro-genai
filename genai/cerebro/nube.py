"""nube.py — cerebros de nube con TU clave (BYOK), como alternativa OPT-IN al local.

DOCTRINA (META.md §cerebros de nube, decidido por el autor 2026-08-27)
----------------------------------------------------------------------
El local sigue siendo el defecto y la identidad del proyecto. Esto existe porque el
autor quiso que cada usuario pueda enchufar SU clave del proveedor que prefiera. Dos
reglas que no se negocian:

1. **Una carrera con cerebro de nube NUNCA cuenta como cifra local.** El registro
   anota siempre proveedor y modelo; M0/M2 se declararon con el cerebro local y ahí
   se quedan. Comparar nube con local es comparar dos máquinas distintas.
2. **La clave es del usuario y vive fuera del repositorio**, en
   `~/.config/genai/claves.json` (permisos 600). Nunca en el árbol, nunca en un
   registro, nunca en un log.

POR QUE HTTP CRUDO Y NO TRES SDK
--------------------------------
La dependencia de este proyecto es UNA (llama-cpp-python) y esa sobriedad es parte de
lo que lo hace instalable en hardware modesto. Cada proveedor aqui son ~30 lineas de
`urllib`, y la alternativa serian tres SDK pesados con sus propias cadenas de
dependencias. Las tres formas de API que existen hoy:

    gemini      generativelanguage.googleapis.com  ·  contents[] + functionDeclarations
    anthropic   api.anthropic.com/v1/messages      ·  x-api-key + tools[input_schema]
    openai      /v1/chat/completions               ·  el dialecto que casi todos hablan
                (OpenAI, DeepSeek, Kimi/Moonshot, xAI, Groq, Together, y cualquier
                 endpoint compatible que el usuario configure)

UNA TRAMPA MEDIDA: EL THINK CUENTA DENTRO DE max_tokens
-------------------------------------------------------
Los modelos con razonamiento (Gemini 3.x entre ellos) cuentan los tokens de think
dentro de `maxOutputTokens`. Medido el 2026-08-28: con `max_tokens=600`, Gemini 3.7
gastó 579 pensando y devolvió 21 tokens de texto truncado; con 2.000, devolvió 121 de
texto útil. Si pides prosa a un modelo pensante, dale presupuesto de sobra — un
`max_tokens` apretado no lo hace conciso, lo hace mudo.

LLAMADAS A HERRAMIENTAS: NATIVAS, NO HERMES
-------------------------------------------
El cerebro local emite Hermes en texto porque es lo que Qwen trae entrenado. Los
modelos de nube tienen llamada a funciones NATIVA y es mucho mas fiable: aqui se usa
la nativa de cada uno y se convierte a la `Llamada` del arnes. El bucle, los permisos
y el banco no se enteran de la diferencia.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

from .base import Llamada, Mensaje, Respuesta, Uso

CLAVES = Path(os.environ.get("MG_CLAVES",
                             Path.home() / ".config" / "genai" / "claves.json"))

# Cada entrada: como se llama la API, donde, y con que modelo por defecto. El usuario
# puede sobreescribir modelo y url en su claves.json sin tocar este fichero.
PROVEEDORES = {
    "gemini": {"dialecto": "gemini", "modelo": "gemini-3.7-flash",
               "url": "https://generativelanguage.googleapis.com/v1beta"},
    "anthropic": {"dialecto": "anthropic", "modelo": "claude-opus-5",
                  "url": "https://api.anthropic.com/v1/messages"},
    "openai": {"dialecto": "openai", "modelo": "gpt-5.1",
               "url": "https://api.openai.com/v1/chat/completions"},
    "deepseek": {"dialecto": "openai", "modelo": "deepseek-chat",
                 "url": "https://api.deepseek.com/v1/chat/completions"},
    "kimi": {"dialecto": "openai", "modelo": "kimi-k2-turbo-preview",
             "url": "https://api.moonshot.ai/v1/chat/completions"},
    "xai": {"dialecto": "openai", "modelo": "grok-4",
            "url": "https://api.x.ai/v1/chat/completions"},
    "groq": {"dialecto": "openai", "modelo": "llama-3.3-70b-versatile",
             "url": "https://api.groq.com/openai/v1/chat/completions"},
    "openrouter": {"dialecto": "openai", "modelo": "openai/gpt-5.1",
                   "url": "https://openrouter.ai/api/v1/chat/completions"},
}


def claves() -> dict:
    """Lo que el usuario configuró. Fuera del repositorio, siempre."""
    if not CLAVES.exists():
        return {}
    return json.loads(CLAVES.read_text(encoding="utf-8"))


def proveedores_configurados() -> list[str]:
    return sorted(k for k, v in claves().items() if isinstance(v, dict) and v.get("clave"))


def _pedir(url: str, cuerpo: dict, cabeceras: dict, segundos: int = 300) -> dict:
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"Content-Type": "application/json",
                                          **cabeceras})
    try:
        with urllib.request.urlopen(req, timeout=segundos) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "ignore")[:400]
        raise SystemExit(f"el proveedor respondio {e.code}: {detalle}\n"
                         "  Revisa la clave y el modelo en " + str(CLAVES))


class CerebroNube:
    """Un modelo de nube hablando el protocolo `Cerebro` del arnes."""

    def __init__(self, proveedor: str = "gemini", modelo: str = "",
                 contexto_max: int = 200000, temperatura: float = 0.0):
        cfg = claves().get(proveedor) or {}
        base = PROVEEDORES.get(proveedor)
        if base is None and not cfg.get("url"):
            raise SystemExit(
                f"proveedor «{proveedor}» desconocido. Conocidos: "
                f"{', '.join(PROVEEDORES)}. Para uno nuevo compatible con OpenAI, "
                f'añade {{"url": "...", "dialecto": "openai"}} en {CLAVES}.')
        base = base or {}
        self.proveedor = proveedor
        self.dialecto = cfg.get("dialecto") or base.get("dialecto", "openai")
        self.url = cfg.get("url") or base.get("url", "")
        self.modelo = modelo or cfg.get("modelo") or base.get("modelo", "")
        self.clave = cfg.get("clave", "")
        if not self.clave:
            raise SystemExit(
                f"falta tu clave de «{proveedor}». Ponla en {CLAVES}:\n"
                f'  {{"{proveedor}": {{"clave": "TU_CLAVE"}}}}\n'
                "  (fichero con permisos 600, fuera del repositorio)")
        # el nombre va al registro: una carrera de nube JAMAS se confunde con local
        self.nombre = f"nube:{proveedor}/{self.modelo}"
        self.contexto_max = contexto_max
        self.temperatura = temperatura
        # Gemini 3.x exige que cada functionCall vuelva con su `thoughtSignature`
        # (400 si falta). No cabe en la `Llamada` del arnes sin ensuciar el protocolo
        # compartido, asi que se guarda aqui por id de llamada y se reinyecta.
        self._firmas_pensamiento: dict[str, str] = {}

    # ── conversion de la transcripcion del arnes a cada dialecto ────────────

    @staticmethod
    def _sistema(mensajes: Sequence[Mensaje]) -> str:
        return "\n\n".join(m.contenido for m in mensajes if m.rol == "sistema")

    def _openai_mensajes(self, mensajes: Sequence[Mensaje]) -> list[dict]:
        fuera = []
        for m in mensajes:
            if m.rol == "sistema":
                fuera.append({"role": "system", "content": m.contenido})
            elif m.rol == "usuario":
                fuera.append({"role": "user", "content": m.contenido})
            elif m.rol == "asistente":
                msg = {"role": "assistant", "content": m.contenido or None}
                if m.llamadas:
                    msg["tool_calls"] = [
                        {"id": ll.id or f"c{i}", "type": "function",
                         "function": {"name": ll.nombre,
                                      "arguments": json.dumps(ll.argumentos,
                                                              ensure_ascii=False)}}
                        for i, ll in enumerate(m.llamadas)]
                fuera.append(msg)
            else:
                fuera.append({"role": "tool", "tool_call_id": m.id_llamada or "c0",
                              "content": m.contenido})
        return fuera

    def _anthropic_mensajes(self, mensajes: Sequence[Mensaje]) -> list[dict]:
        fuera = []
        for m in mensajes:
            if m.rol == "sistema":
                continue                       # va en el campo `system`, aparte
            if m.rol == "usuario":
                fuera.append({"role": "user", "content": m.contenido})
            elif m.rol == "asistente":
                bloques = []
                if m.contenido:
                    bloques.append({"type": "text", "text": m.contenido})
                for i, ll in enumerate(m.llamadas):
                    bloques.append({"type": "tool_use", "id": ll.id or f"c{i}",
                                    "name": ll.nombre, "input": ll.argumentos})
                fuera.append({"role": "assistant", "content": bloques or [
                    {"type": "text", "text": "(sin texto)"}]})
            else:
                fuera.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": m.id_llamada or "c0",
                     "content": m.contenido}]})
        return fuera

    def _gemini_contenidos(self, mensajes: Sequence[Mensaje]) -> list[dict]:
        fuera = []
        for m in mensajes:
            if m.rol == "sistema":
                continue                       # va en systemInstruction, aparte
            if m.rol == "usuario":
                fuera.append({"role": "user", "parts": [{"text": m.contenido}]})
            elif m.rol == "asistente":
                partes = []
                if m.contenido:
                    partes.append({"text": m.contenido})
                for ll in m.llamadas:
                    parte = {"functionCall": {"name": ll.nombre,
                                              "args": ll.argumentos}}
                    firma = self._firmas_pensamiento.get(ll.id)
                    if firma:
                        parte["thoughtSignature"] = firma
                    partes.append(parte)
                fuera.append({"role": "model", "parts": partes or [{"text": "."}]})
            else:
                # el nombre de la funcion se recupera de la llamada que la pidio
                nombre = "herramienta"
                for prev in reversed(mensajes[:mensajes.index(m)]):
                    if prev.rol == "asistente" and prev.llamadas:
                        for ll in prev.llamadas:
                            if ll.id == m.id_llamada:
                                nombre = ll.nombre
                        break
                fuera.append({"role": "user", "parts": [
                    {"functionResponse": {"name": nombre,
                                          "response": {"resultado": m.contenido}}}]})
        return fuera

    # ── generar: una firma, tres dialectos ──────────────────────────────────

    def generar(self, mensajes: Sequence[Mensaje], herramientas: Sequence[dict] = (),
                max_tokens: int = 1024, pensar: bool | None = None) -> Respuesta:
        t0 = time.time()
        if self.dialecto == "gemini":
            texto, llamadas, entrada, salida = self._gemini(
                mensajes, herramientas, max_tokens)
        elif self.dialecto == "anthropic":
            texto, llamadas, entrada, salida = self._anthropic(
                mensajes, herramientas, max_tokens)
        else:
            texto, llamadas, entrada, salida = self._openai(
                mensajes, herramientas, max_tokens)
        return Respuesta(texto=texto, llamadas=llamadas,
                         uso=Uso(entrada, salida, round(time.time() - t0, 3)),
                         motivo_parada="herramienta" if llamadas else "fin")

    def _gemini(self, mensajes, herramientas, max_tokens):
        cuerpo = {"contents": self._gemini_contenidos(mensajes),
                  "generationConfig": {"temperature": self.temperatura,
                                       "maxOutputTokens": max_tokens}}
        sistema = self._sistema(mensajes)
        if sistema:
            cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        if herramientas:
            cuerpo["tools"] = [{"functionDeclarations": [
                {"name": h["function"]["name"],
                 "description": h["function"].get("description", ""),
                 "parameters": _limpiar_esquema(h["function"].get("parameters", {}))}
                for h in herramientas]}]
        url = f"{self.url}/models/{self.modelo}:generateContent?key={self.clave}"
        d = _pedir(url, cuerpo, {})
        texto, llamadas = "", []
        cand = (d.get("candidates") or [{}])[0]
        for i, parte in enumerate((cand.get("content") or {}).get("parts", [])):
            if "text" in parte:
                texto += parte["text"]
            if "functionCall" in parte:
                fc = parte["functionCall"]
                ident = f"g{len(self._firmas_pensamiento)}_{i}"
                if parte.get("thoughtSignature"):
                    self._firmas_pensamiento[ident] = parte["thoughtSignature"]
                llamadas.append(Llamada(fc.get("name", ""), fc.get("args") or {},
                                        id=ident))
        u = d.get("usageMetadata") or {}
        return (texto.strip(), llamadas, u.get("promptTokenCount", 0),
                u.get("candidatesTokenCount", 0))

    def _anthropic(self, mensajes, herramientas, max_tokens):
        cuerpo = {"model": self.modelo, "max_tokens": max_tokens,
                  "messages": self._anthropic_mensajes(mensajes)}
        sistema = self._sistema(mensajes)
        if sistema:
            cuerpo["system"] = sistema
        if herramientas:
            cuerpo["tools"] = [{"name": h["function"]["name"],
                                "description": h["function"].get("description", ""),
                                "input_schema": h["function"].get("parameters", {})}
                               for h in herramientas]
        d = _pedir(self.url, cuerpo, {"x-api-key": self.clave,
                                      "anthropic-version": "2023-06-01"})
        texto, llamadas = "", []
        for bloque in d.get("content", []):
            if bloque.get("type") == "text":
                texto += bloque.get("text", "")
            elif bloque.get("type") == "tool_use":
                llamadas.append(Llamada(bloque.get("name", ""),
                                        bloque.get("input") or {},
                                        id=bloque.get("id", "")))
        u = d.get("usage") or {}
        return (texto.strip(), llamadas, u.get("input_tokens", 0),
                u.get("output_tokens", 0))

    def _openai(self, mensajes, herramientas, max_tokens):
        cuerpo = {"model": self.modelo, "messages": self._openai_mensajes(mensajes),
                  "max_completion_tokens": max_tokens,
                  "temperature": self.temperatura}
        if herramientas:
            cuerpo["tools"] = list(herramientas)     # ya vienen en dialecto OpenAI
        d = _pedir(self.url, cuerpo, {"Authorization": f"Bearer {self.clave}"})
        msg = ((d.get("choices") or [{}])[0].get("message") or {})
        llamadas = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            llamadas.append(Llamada(fn.get("name", ""), args, id=tc.get("id", "")))
        u = d.get("usage") or {}
        return ((msg.get("content") or "").strip(), llamadas,
                u.get("prompt_tokens", 0), u.get("completion_tokens", 0))

    def contar_tokens(self, texto: str) -> int:
        """Aproximación declarada (~4 caracteres por token). No pretende ser el
        tokenizador del proveedor: pretende no mentir con un 0. Las cifras REALES de
        cada llamada vienen del `usage` que devuelve la API y esas son las que van
        al registro."""
        return max(1, len(texto) // 4)


def _limpiar_esquema(esquema: dict) -> dict:
    """Gemini rechaza claves de JSON Schema que OpenAI acepta (`additionalProperties`,
    `default`, `$schema`). Se podan en vez de fallar."""
    if not isinstance(esquema, dict):
        return esquema
    fuera = {}
    for k, v in esquema.items():
        if k in ("additionalProperties", "default", "$schema", "examples"):
            continue
        if isinstance(v, dict):
            fuera[k] = _limpiar_esquema(v)
        elif isinstance(v, list):
            fuera[k] = [_limpiar_esquema(x) if isinstance(x, dict) else x for x in v]
        else:
            fuera[k] = v
    return fuera
