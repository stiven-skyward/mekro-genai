"""Acceso a la web (M7.3): `web` trae una URL y `buscar_web` busca.

**Viene ENCENDIDO** por decisión del autor (2026-08-28): el agente necesita comprobar
una URL y consultar documentación que no está en el proyecto. Lo que no cambia es que
sea visible y apagable (`genai tarea … --sin-web`, `estandar(web=False)`) y que pase por
`permisos.py` igual que `bash`. El banco lo deja apagado a propósito, para no hacer
incomparables sus cifras con las de M2 y M3.

Que la red esté encendida **no** convierte esto en un arnés de nube: el cerebro sigue
siendo local, y leer una página es tan «nube» como leer un fichero es «disco».

**El guardarraíl que de verdad importa no es el opt-in, es el SSRF.** Un agente con
`leer` y con red puede ser convencido —por el contenido de una página, que es texto
ajeno— de pedir `http://169.254.169.254/` y volcar las credenciales de la máquina. Por
eso aquí se resuelve el nombre y se comprueba la IP **antes** de conectar, y se vuelve a
comprobar en cada redirección: un dominio público que redirige a `127.0.0.1` es el truco
clásico y no basta con mirar la URL que escribió el modelo.

Y lo que trae de vuelta es **texto**, no HTML. Traer 400 KB de etiquetas a una
transcripción que se reenvía cada vuelta es la forma más cara de no leer nada
(docs/ahorro.md).
"""
from __future__ import annotations

import html
import ipaddress
import re
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .base import Herramienta, Resultado

TOPE = 40_000            # caracteres de texto que vuelven como mucho
AGENTE = "Mekro-Genai/1.0 (+arnés agéntico local)"


def _publica(host: str) -> tuple[bool, str]:
    """¿Apunta este nombre a una dirección de internet, o a la casa de uno?

    Se resuelve el nombre y se miran TODAS sus direcciones: si cualquiera es privada,
    se rechaza. Un nombre que resuelve a la vez a una pública y a 127.0.0.1 es un
    ataque, no una casualidad."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, f"no se pudo resolver «{host}»"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, f"dirección ininteligible para «{host}»"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False, (f"«{host}» resuelve a {ip}, que es una dirección interna. "
                           f"La red del agente sale a internet, no entra en esta "
                           f"máquina ni en esta red.")
    return True, ""


class _SinSaltos(urllib.request.HTTPRedirectHandler):
    """Cada redirección se vuelve a validar. Un dominio público que redirige a
    169.254.169.254 es el camino corto a las credenciales de la máquina."""

    def redirect_request(self, req, fp, code, msg, headers, nueva):
        p = urllib.parse.urlparse(nueva)
        if p.scheme not in ("http", "https"):
            raise urllib.error.URLError(f"redirección a esquema no permitido: {p.scheme}")
        ok, motivo = _publica(p.hostname or "")
        if not ok:
            raise urllib.error.URLError(f"redirección bloqueada: {motivo}")
        return super().redirect_request(req, fp, code, msg, headers, nueva)


def _a_texto(bruto: str) -> str:
    """HTML → texto legible. Sin dependencias: el proyecto tiene UNA y no se toca."""
    t = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", bruto)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", t)
    t = re.sub(r"(?i)<li\b[^>]*>", "\n· ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip()


def web(url: str, tope: int = TOPE) -> Resultado:
    url = (url or "").strip()
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return Resultado(False, "solo http y https. `file://` no es la web: para leer "
                                "un fichero de esta máquina está `leer`.")
    if not p.hostname:
        return Resultado(False, f"esa URL no tiene servidor: {url!r}")
    ok, motivo = _publica(p.hostname)
    if not ok:
        return Resultado(False, motivo)

    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE,
                                                  "Accept": "text/html,text/plain,*/*"})
    abridor = urllib.request.build_opener(_SinSaltos)
    try:
        with abridor.open(pedido, timeout=30) as r:
            tipo = (r.headers.get("Content-Type") or "").lower()
            if not any(k in tipo for k in ("text/", "json", "xml", "javascript")):
                return Resultado(False, f"{url} devuelve «{tipo or 'desconocido'}», que "
                                        f"no es texto. Traer binario a la transcripción "
                                        f"no sirve de nada.")
            crudo = r.read(4_000_000)
            juego = r.headers.get_content_charset() or "utf-8"
            final = r.geturl()
    except urllib.error.HTTPError as e:
        return Resultado(False, f"{url} respondió {e.code} {e.reason}")
    except urllib.error.URLError as e:
        return Resultado(False, f"no se pudo abrir {url}: {e.reason}")
    except (TimeoutError, socket.timeout):
        return Resultado(False, f"{url} tardó más de 30 s")
    except OSError as e:
        return Resultado(False, f"no se pudo abrir {url}: {e}")

    texto = crudo.decode(juego, errors="replace")
    if "html" in tipo:
        texto = _a_texto(texto)
    cabecera = f"── {final}" + ("" if final == url else f"  (redirigido desde {url})")
    tope = max(1000, min(int(tope or TOPE), TOPE))
    if len(texto) > tope:
        texto = texto[:tope] + (f"\n\n[… la página sigue; {len(texto) - tope} caracteres "
                                f"más. Si necesitas otra parte, dilo y se pide de nuevo "
                                f"con un tope mayor …]")
    return Resultado(True, f"{cabecera}\n{texto}", datos={"url": final})


# ── búsqueda ───────────────────────────────────────────────────────────────────
# No hay buscador gratis y estable que raspar: DuckDuckGo responde con un CAPTCHA
# («bots use DuckDuckGo too», comprobado 2026-08-28) y construir sobre raspado es
# frágil por definición. Así que la búsqueda va con clave, como los cerebros: BYOK.
#
# Y hay una segunda vía que sirve para el caso que más importa aquí. Si no hay clave de
# buscador pero sí de Gemini, se le pide a Gemini que busque —tiene Google Search
# nativo— y se devuelven sus fuentes. Con eso **el Qwen local tiene búsqueda web** sin
# ser él quien la haga, que es exactamente la doctrina híbrida de M7.1b: la nube hace el
# recado auxiliar y nunca es la carga crítica.
BUSCADORES = {
    "brave":  ("https://api.search.brave.com/res/v1/web/search?q=",
               lambda k: {"X-Subscription-Token": k, "Accept": "application/json"}),
    "serper": ("https://google.serper.dev/search?q=",
               lambda k: {"X-API-KEY": k}),
}


def _claves() -> dict:
    f = Path.home() / ".config" / "genai" / "claves.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _por_gemini(consulta: str, clave: str, n: int) -> Resultado:
    """Gemini busca y devuelve sus fuentes. No se pide la respuesta del modelo: se
    piden las URLs, porque quien tiene que leer y decidir es el agente, no Gemini."""
    cuerpo = {"contents": [{"role": "user", "parts": [{"text":
              f"Busca en la web: {consulta}\nResume en tres líneas lo hallado."}]}],
              "tools": [{"googleSearch": {}}],
              "generationConfig": {"maxOutputTokens": 2000}}
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-3.7-flash:generateContent?key={clave}")
    try:
        pedido = urllib.request.Request(url, json.dumps(cuerpo).encode(),
                                        {"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(pedido, timeout=90))
    except Exception as e:  # noqa: BLE001
        return Resultado(False, f"la búsqueda por Gemini falló: {e}")
    cand = (d.get("candidates") or [{}])[0]
    texto = "".join(p.get("text", "")
                    for p in (cand.get("content") or {}).get("parts", []))
    gm = cand.get("groundingMetadata") or {}
    fuentes = []
    for ch in (gm.get("groundingChunks") or [])[:n]:
        w = ch.get("web") or {}
        if w.get("uri"):
            fuentes.append(f"· {w.get('title', '(sin título)')}\n  {w['uri']}")
    if not fuentes and not texto:
        return Resultado(False, f"sin resultados para «{consulta}»")
    cab = f"── búsqueda: {consulta}  (vía Gemini; consultas reales: "
    cab += ", ".join(gm.get("webSearchQueries") or ["?"]) + ")"
    cuerpo_txt = texto.strip()[:2000]
    if fuentes:
        cuerpo_txt += "\n\nFUENTES (léelas con `web` si necesitas el detalle):\n"
        cuerpo_txt += "\n".join(fuentes)
    return Resultado(True, f"{cab}\n{cuerpo_txt}")


def buscar(consulta: str, n: int = 6) -> Resultado:
    consulta = (consulta or "").strip()
    if not consulta:
        return Resultado(False, "una búsqueda vacía no busca nada")
    n = max(1, min(int(n or 6), 15))
    cl = _claves()

    for nombre, (base, cabs) in BUSCADORES.items():
        k = (cl.get(nombre) or {}).get("clave")
        if not k:
            continue
        try:
            pedido = urllib.request.Request(base + urllib.parse.quote(consulta),
                                            headers=cabs(k))
            d = json.load(urllib.request.urlopen(pedido, timeout=45))
        except Exception as e:  # noqa: BLE001
            return Resultado(False, f"el buscador «{nombre}» falló: {e}")
        crudos = (d.get("web", {}).get("results")
                  or d.get("organic") or [])[:n]
        if not crudos:
            return Resultado(False, f"sin resultados para «{consulta}»")
        filas = [f"· {r.get('title', '')}\n  {r.get('url') or r.get('link')}\n"
                 f"  {(r.get('description') or r.get('snippet') or '')[:200]}"
                 for r in crudos]
        return Resultado(True, f"── búsqueda: {consulta}  ({nombre})\n"
                               + "\n".join(filas))

    g = (cl.get("gemini") or {}).get("clave")
    if g:
        return _por_gemini(consulta, g, n)

    return Resultado(False, (
        "no hay con qué buscar. Añade en ~/.config/genai/claves.json una clave de "
        "buscador —`brave` o `serper`— o una de `gemini`, que trae Google Search "
        "nativo. Mientras tanto, `web` sí puede traer una URL que ya conozcas."))


HERRAMIENTAS = [
    Herramienta(
        nombre="buscar_web",
        descripcion=("Busca en internet y devuelve títulos, URLs y un extracto. "
                     "Úsala cuando necesites algo que no está en el proyecto y no "
                     "sepas la URL; luego lee la que sirva con `web`."),
        parametros={
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "qué buscar"},
                "n": {"type": "integer", "description": "cuántos resultados (6)"},
            },
            "required": ["consulta"],
        },
        funcion=buscar,
        peligrosa=True,
    ),
    Herramienta(
        nombre="web",
        descripcion=("Trae el TEXTO de una página web pública (http/https). Devuelve "
                     "texto limpio, no HTML. No alcanza direcciones internas ni de esta "
                     "máquina. Úsala para documentación y referencias que no estén en "
                     "el proyecto; para lo que sí está, `leer` y `grep` son gratis."),
        parametros={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "la URL, con http:// o https://"},
                "tope": {"type": "integer",
                         "description": f"caracteres máximos (por defecto {TOPE})"},
            },
            "required": ["url"],
        },
        funcion=web,
        peligrosa=True,        # toca la red: pasa por permisos.py como bash
    ),
]
