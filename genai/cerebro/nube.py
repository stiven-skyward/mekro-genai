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
        # Los ocho de fábrica MANDAN: son los que tienen medición detrás (caché, firmas
        # de pensamiento, PDF) y el catálogo no sabe nada de eso. Solo si el nombre no
        # está aquí ni escrito a mano se busca entre los 207 de models.dev.
        if proveedor == "google" and not cfg.get("clave"):
            # Cuota de la SUSCRIPCIÓN, no clave de API: se entra con la cuenta y se
            # habla con Code Assist, que envuelve la respuesta de Gemini.
            from ..google_cuenta import acceso, proyecto
            tok, q = acceso()
            if not tok:
                raise SystemExit(q)
            pid, q2 = proyecto()
            if not pid:
                raise SystemExit(q2)
            cfg = {"dialecto": "gemini", "url": "https://cloudcode-pa.googleapis.com/"
                                                "v1internal",
                   "clave": tok, "modelo": modelo or "gemini-2.5-pro",
                   "proyecto_asist": pid, "cachear": False, **cfg}
            base = {}
        if proveedor == "copilot" and not cfg.get("clave"):
            # Copilot no usa una clave que escribas: usa tu SESIÓN de GitHub, y su
            # token caduca en minutos, así que se pide fresco en cada arranque.
            from ..copilot import config as _copiloto
            cfg = {**_copiloto(), **cfg}
            base = {}
        if base is None and not cfg.get("url"):
            from ..catalogo import resolver
            base, queja = resolver(proveedor)
            if not base:
                raise SystemExit(
                    f"proveedor «{proveedor}» desconocido. De fábrica: "
                    f"{', '.join(PROVEEDORES)}.\n  {queja}\n"
                    f'  O escríbelo a mano: {{"url": "...", "dialecto": "openai", '
                    f'"clave": "..."}} en {CLAVES}.')
            # la clave puede venir de la variable de entorno que el catálogo declara
            if not cfg.get("clave") and base.get("env"):
                import os as _os
                if _os.environ.get(base["env"]):
                    cfg = {**cfg, "clave": _os.environ[base["env"]]}
        base = base or {}
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
        # caché de prefijo: se puede apagar para medir el A/B (docs/ahorro.md)
        self.cachear = cfg.get("cachear", True)
        self.cache = {"leidos": 0, "totales": 0, "escritos": 0, "escrituras": 0}
        # p. ej. {"anthropic-workspace-id": "wrkspc_..."} o las de un proxy
        self.cabeceras = dict(cfg.get("cabeceras", {}))
        # qué proveedor es, por nombre. `buscar_web` lo usa para que la búsqueda salga
        # por el proveedor que ya se está pagando y no por otro.
        self.proveedor = proveedor
        # Si va por Code Assist, aquí está el proyecto; si no, cadena vacía.
        self.asist = cfg.get("proyecto_asist", "")
        self._cache_g = None          # caché explícita viva, solo dialecto gemini
        # M7.4 — qué puede MIRAR este cerebro. `ver` lo consulta antes de mandar bytes:
        # un adjunto que el proveedor tira en silencio hace que el modelo responda con
        # seguridad sobre algo que nunca vio.
        self.multimodal = cfg.get("multimodal", True)
        self.pdf = cfg.get("pdf", self.dialecto in ("gemini", "anthropic"))

    def _anotar_cache(self, leidos: int, totales: int) -> None:
        """Cuánto de la entrada vino de caché. Es la cifra que dice si el ahorro
        mayor está funcionando; sin medirla, «usamos caché» es un adjetivo."""
        self.cache["leidos"] += int(leidos or 0)
        self.cache["totales"] += int(totales or 0)

    @property
    def ahorro_cache(self) -> float:
        t = self.cache["totales"]
        return round(self.cache["leidos"] / t, 3) if t else 0.0

    # ── conversion de la transcripcion del arnes a cada dialecto ────────────

    @staticmethod
    def _sistema(mensajes: Sequence[Mensaje]) -> str:
        return "\n\n".join(m.contenido for m in mensajes if m.rol == "sistema")

    @staticmethod
    def _partes_openai(m) -> list[dict]:
        """OpenAI y compatibles: imágenes como data: URI. PDF no se manda —`ver` ya lo
        impidió arriba mirando `cerebro.pdf`, y duplicar aquí el veto sería fingir dos
        guardias donde hay uno."""
        fuera = [{"type": "text", "text": m.contenido}]
        for a in m.adjuntos:
            if a["medio"].startswith("image/"):
                fuera.append({"type": "image_url",
                              "image_url": {"url": f"data:{a['medio']};base64,"
                                                   f"{a['datos']}"}})
        return fuera

    def _openai_mensajes(self, mensajes: Sequence[Mensaje]) -> list[dict]:
        fuera = []
        for m in mensajes:
            if m.rol == "sistema":
                fuera.append({"role": "system", "content": m.contenido})
            elif m.rol == "usuario":
                fuera.append({"role": "user",
                              "content": (self._partes_openai(m) if m.adjuntos
                                          else m.contenido)})
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

    @staticmethod
    def _bloques_adjuntos(m) -> list[dict]:
        """Anthropic separa imagen (`image`) de PDF (`document`); el resto del cuerpo
        es idéntico, así que se arma una vez."""
        fuera = []
        for a in m.adjuntos:
            tipo = "document" if a["medio"] == "application/pdf" else "image"
            fuera.append({"type": tipo, "source": {"type": "base64",
                                                   "media_type": a["medio"],
                                                   "data": a["datos"]}})
        return fuera

    def _anthropic_mensajes(self, mensajes: Sequence[Mensaje]) -> list[dict]:
        fuera = []
        for m in mensajes:
            if m.rol == "sistema":
                continue                       # va en el campo `system`, aparte
            if m.rol == "usuario":
                cont = m.contenido
                if m.adjuntos:
                    cont = ([{"type": "text", "text": m.contenido}]
                            + self._bloques_adjuntos(m))
                fuera.append({"role": "user", "content": cont})
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
                partes = [{"text": m.contenido}]
                for a in m.adjuntos:      # M7.4: Gemini acepta imagen y PDF en línea
                    partes.append({"inlineData": {"mimeType": a["medio"],
                                                  "data": a["datos"]}})
                fuera.append({"role": "user", "parts": partes})
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

    # ── caché explícita de Gemini (cachedContents) ──────────────────────────
    # Gemini NO tiene caché implícita: se midió con tres peticiones idénticas de 6.008
    # tokens y `cachedContentTokenCount` no apareció ni una vez. Lo que sí tiene es
    # caché explícita, y hay que pedirla a mano.
    #
    # La aritmética que decide CUÁNDO recrearla, porque escribir una caché cuesta como
    # entrada normal: escribir T y leerlo K veces con descuento sale a T·(1 + 0,25·K)
    # frente a T·K sin caché. Gana en cuanto K > 1,33, es decir a partir de la SEGUNDA
    # lectura. Por eso se recrea solo cuando el prefijo ha crecido lo bastante para que
    # la reescritura se amortice, y no en cada vuelta.
    CACHE_MINIMO = 1024        # el mínimo del API; por debajo responde 400 (medido)
    # Recrear cuando la COLA SIN CACHEAR llegue a esta fracción de lo ya cacheado. Se
    # mide en tokens y no en número de mensajes: un turno de 20 caracteres y uno de
    # 5.000 pesan igual en la cuenta de mensajes y nada parecido en la factura.
    CACHE_COLA_MAX = 0.5
    CACHE_TTL = "600s"

    def _cache_crear(self, prefijo, sistema, tools):
        cuerpo = {"model": f"models/{self.modelo}", "contents": prefijo,
                  "ttl": self.CACHE_TTL}
        if sistema:
            cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
        if tools:
            cuerpo["tools"] = tools
        try:
            d = _pedir(f"{self.url}/cachedContents?key={self.clave}", cuerpo, {})
        except (Exception, SystemExit):
            # Una caché que no se puede crear no puede costar la carrera: se sigue sin
            # ella. Es un ahorro, no un requisito.
            self._cache_g = None
            return None
        self._cache_borrar()
        escritos = int((d.get("usageMetadata") or {}).get("totalTokenCount", 0))
        # Escribir una caché NO es gratis: se contabiliza aparte para que el ahorro
        # neto sea una cifra y no una esperanza. Si `escritos` se acerca a `leidos`,
        # la caché explícita no está ahorrando nada.
        self.cache["escritos"] = self.cache.get("escritos", 0) + escritos
        self.cache["escrituras"] = self.cache.get("escrituras", 0) + 1
        self._cache_g = {"nombre": d["name"], "hasta": len(prefijo),
                         "tokens": escritos}
        return self._cache_g

    def _cache_borrar(self) -> None:
        """Una caché que sobrevive a la tarea se sigue cobrando por horas."""
        vieja = getattr(self, "_cache_g", None)
        if not vieja:
            return
        try:
            import urllib.request
            urllib.request.urlopen(urllib.request.Request(
                f"{self.url}/{vieja['nombre']}?key={self.clave}", method="DELETE"),
                timeout=20)
        except Exception:  # noqa: BLE001 — el TTL la barrerá igual
            pass
        self._cache_g = None

    def cerrar(self) -> None:
        """Al acabar la tarea. Sin esto, cada carrera deja caché pagándose sola."""
        if self.dialecto == "gemini":
            self._cache_borrar()

    def _gemini(self, mensajes, herramientas, max_tokens):
        contenidos = self._gemini_contenidos(mensajes)
        sistema = self._sistema(mensajes)
        tools = None
        if herramientas:
            tools = [{"functionDeclarations": [
                {"name": h["function"]["name"],
                 "description": h["function"].get("description", ""),
                 "parameters": _limpiar_esquema(h["function"].get("parameters", {}))}
                for h in herramientas]}]

        cuerpo = {"generationConfig": {"temperature": self.temperatura,
                                       "maxOutputTokens": max_tokens}}
        # El prefijo cacheable es todo menos el último turno: ese cambia siempre, y
        # meterlo en la caché obligaría a recrearla cada vuelta, que es justo la
        # operación que no sale a cuenta.
        prefijo, cola = contenidos[:-1], contenidos[-1:]
        c = getattr(self, "_cache_g", None)
        if self.cachear and prefijo:
            # el mínimo del API se estima antes de pedirlo: un 400 previsible no se
            # provoca para luego capturarlo
            aprox = _aprox_tokens(prefijo)
            if aprox >= self.CACHE_MINIMO and (
                    not c
                    # la cola sin cachear ya pesa la mitad de lo cacheado: reescribir
                    or _aprox_tokens(contenidos[c["hasta"]:-1])
                    >= self.CACHE_COLA_MAX * max(1, c["tokens"])):
                c = self._cache_crear(prefijo, sistema, tools)
            elif c and len(prefijo) < c["hasta"]:
                # la transcripción encogió (renacimiento): la caché ya no es prefijo
                self._cache_borrar()
                c = None

        if c:
            cuerpo["cachedContent"] = c["nombre"]
            cuerpo["contents"] = contenidos[c["hasta"]:]
        else:
            cuerpo["contents"] = contenidos
            if sistema:
                cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
            if tools:
                cuerpo["tools"] = tools

        if self.asist:
            # Code Assist no lleva la clave en la URL sino en la cabecera, y envuelve
            # tanto la petición como la respuesta. Por dentro es el mismo Gemini.
            url = f"{self.url}:generateContent"
            cuerpo = {"model": self.modelo, "project": self.asist, "request": cuerpo}
            cabs = {"Authorization": f"Bearer {self.clave}"}
        else:
            url = f"{self.url}/models/{self.modelo}:generateContent?key={self.clave}"
            cabs = {}
        try:
            d = _pedir(url, cuerpo, cabs)
        except (Exception, SystemExit):
            if not c:
                raise
            # La caché pudo caducar entre que se creó y se usó. Se reintenta entera y
            # sin ella: perder el ahorro es aceptable, perder la vuelta no.
            self._cache_borrar()
            cuerpo.pop("cachedContent", None)
            cuerpo["contents"] = contenidos
            if sistema:
                cuerpo["systemInstruction"] = {"parts": [{"text": sistema}]}
            if tools:
                cuerpo["tools"] = tools
            d = _pedir(url, cuerpo, cabs)
        if self.asist:
            d = d.get("response", d)          # Code Assist envuelve la respuesta
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
        self._anotar_cache(u.get("cachedContentTokenCount", 0),
                           u.get("promptTokenCount", 0))
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
        # CACHÉ DE PREFIJO (docs/ahorro.md): Anthropic cobra ~0,1× por token leído de
        # caché, y el gasto de una carrera es entrada en proporción 40:1. El prefijo
        # aquí es estable POR CONSTRUCCIÓN (C22: la transcripción solo crece por el
        # final), así que basta marcar dónde acaba lo estable. Se marca el sistema y
        # el penúltimo turno: lo último cambia siempre y marcarlo no cachearía nada.
        if self.cachear:
            if isinstance(cuerpo.get("system"), str) and cuerpo["system"]:
                cuerpo["system"] = [{"type": "text", "text": cuerpo["system"],
                                     "cache_control": {"type": "ephemeral"}}]
            msgs = cuerpo["messages"]
            if len(msgs) >= 3:
                bloques = msgs[-3]["content"]
                if isinstance(bloques, str):
                    msgs[-3]["content"] = bloques = [{"type": "text", "text": bloques}]
                if bloques:
                    bloques[-1]["cache_control"] = {"type": "ephemeral"}
        cab = {"x-api-key": self.clave, "anthropic-version": "2023-06-01"}
        # Cabeceras extra del proveedor. Existen porque una clave de Anthropic ligada a
        # identidad exige `anthropic-workspace-id` y responde 400 sin ella; y porque un
        # proxy corporativo delante de cualquier proveedor suele pedir las suyas. Se
        # ponen en claves.json y no hay que tocar código.
        cab.update(self.cabeceras)
        d = _pedir(self.url, cuerpo, cab)
        texto, llamadas = "", []
        for bloque in d.get("content", []):
            if bloque.get("type") == "text":
                texto += bloque.get("text", "")
            elif bloque.get("type") == "tool_use":
                llamadas.append(Llamada(bloque.get("name", ""),
                                        bloque.get("input") or {},
                                        id=bloque.get("id", "")))
        u = d.get("usage") or {}
        self._anotar_cache(u.get("cache_read_input_tokens", 0),
                           u.get("input_tokens", 0))
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
        # OpenAI, DeepSeek y compatibles cachean el prefijo SOLOS: no hay que pedirlo,
        # solo no romperlo. Lo que sí hay que hacer es CONTARLO, porque un ahorro que
        # no se mide no existe (docs/ahorro.md).
        cacheados = ((u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                     or u.get("prompt_cache_hit_tokens", 0))
        self._anotar_cache(cacheados, u.get("prompt_tokens", 0))
        return ((msg.get("content") or "").strip(), llamadas,
                u.get("prompt_tokens", 0), u.get("completion_tokens", 0))

    def contar_tokens(self, texto: str) -> int:
        """Aproximación declarada (~4 caracteres por token). No pretende ser el
        tokenizador del proveedor: pretende no mentir con un 0. Las cifras REALES de
        cada llamada vienen del `usage` que devuelve la API y esas son las que van
        al registro."""
        return max(1, len(texto) // 4)


def _aprox_tokens(partes) -> float:
    """Tamaño en tokens, a ojo pero suficiente: solo decide CUÁNDO reescribir la caché,
    y equivocarse por un 20 % cambia el momento, no la corrección."""
    return sum(len(json.dumps(p, ensure_ascii=False)) for p in partes) / 4


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
