"""Acceso a la web (M7.3), **apagado por defecto** y con la puerta bien cerrada.

La honestidad que META.md ya tiene escrita: un arnés que presume de local y abre la red
sin decirlo está mintiendo sobre lo que es. Por eso esto se enciende a mano
(`estandar(web=True)`, `genai tarea … --web`) y en local el agente ni sabe que la red
es una posibilidad: la herramienta no aparece en sus firmas.

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
import socket
import urllib.error
import urllib.parse
import urllib.request

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


HERRAMIENTAS = [
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
