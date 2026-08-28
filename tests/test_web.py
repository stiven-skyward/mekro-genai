"""Acceso a la web (M7.3): `web` trae una URL, `buscar_web` busca.

Viene encendida por decisión del autor. Lo que se vigila NO es que sepa descargar una
página —eso lo sabe `urllib`— sino:

1. que siga siendo **visible y apagable**, y que el BANCO la deje fuera, porque dos
   herramientas más en el prompt de cada vuelta harían incomparables sus cifras;
2. que **no alcance esta máquina ni esta red**, ni por URL directa ni por redirección,
   porque un agente con red puede ser convencido por texto ajeno de ir a pedir las
   credenciales de la instancia;
3. que devuelva **texto y no HTML**, porque cada carácter se reenvía en cada vuelta.

Ninguna de estas pruebas toca internet: las tres se deciden antes de abrir un socket.
"""
import http.server
import socket
import threading

from _util import Cuenta

from genai.herramientas import estandar
from genai.herramientas.base import Resultado
from genai.herramientas.web import BUSCADORES, _a_texto, _publica, buscar, web

RAIZ = __import__("pathlib").Path(__file__).resolve().parents[1]

c = Cuenta("web")

# ── 1. encendida, pero visible y apagable ──────────────────────────────────
c({"web", "buscar_web"} <= set(estandar()._por_nombre),
  "la red viene ENCENDIDA por decisión del autor: traer una URL y buscar")
c("web" not in estandar(web=False),
  "y se apaga entera con web=False (`--sin-web`): sigue siendo una decisión visible")
c(estandar()["web"].peligrosa and estandar()["buscar_web"].peligrosa,
  "las dos son peligrosas: tocan la red, así que pasan por permisos.py como bash")
c("web" not in estandar(incluir_peligrosas=False),
  "en modo plan no hay red, como no hay bash: quien no puede escribir tampoco sale")

_banco = (RAIZ / "scripts" / "correr_banco.py").read_text(encoding="utf-8")
c("estandar(web=False" in _banco,
  "el BANCO corre sin web a propósito: dos herramientas más engordan el prompt de "
  "sistema en cada vuelta y harían incomparables las carreras nuevas con las cifras "
  "de M2 y M3")

# ── 2. SSRF: la casa de uno no es internet ──────────────────────────────────
for url, que in [("http://127.0.0.1:9/x", "loopback por IP"),
                 ("http://localhost/x", "loopback por nombre"),
                 ("http://169.254.169.254/latest/meta-data/", "metadatos de la nube"),
                 ("http://10.0.0.1/", "red privada"),
                 ("http://192.168.1.1/", "red doméstica"),
                 ("http://[::1]/", "loopback IPv6")]:
    r = web(url)
    c(not r.ok and "interna" in r.salida, f"bloqueado: {que}")

c(not web("file:///etc/passwd").ok, "`file://` no es la web y se dice por qué")
c(not web("gopher://x/").ok, "ni ningún otro esquema: solo http y https")
c(not web("http:///sin-servidor").ok, "una URL sin servidor se rechaza sin reventar")
c("leer" in web("file:///etc/passwd").salida,
  "y el rechazo señala la herramienta correcta en vez de solo negarse")

c(_publica("127.0.0.1") == (False, "") or not _publica("127.0.0.1")[0],
  "la comprobación mira la IP RESUELTA, no el texto de la URL: por eso un nombre "
  "público que apunte a 127.0.0.1 tampoco pasa")
c(not _publica("no-existe.invalid")[0],
  "un nombre que no resuelve se rechaza, no se intenta a ciegas")

# ── 3. la redirección se vuelve a comprobar ─────────────────────────────────
# El truco clásico: un servidor legítimo que responde 302 hacia 127.0.0.1. Validar
# solo la URL que escribió el modelo no basta, así que aquí se monta ese servidor.
class Salto(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "http://127.0.0.1:9/secreto")
        self.end_headers()

    def log_message(self, *a):
        pass


s = http.server.HTTPServer(("127.0.0.1", 0), Salto)
puerto = s.server_address[1]
threading.Thread(target=s.serve_forever, daemon=True).start()
# Se salta la validación de entrada a propósito para llegar al handler de redirección,
# que es lo que se quiere probar aquí.
import urllib.request  # noqa: E402

from genai.herramientas.web import _SinSaltos  # noqa: E402

try:
    urllib.request.build_opener(_SinSaltos).open(
        f"http://127.0.0.1:{puerto}/", timeout=5)
    saltó = True
except Exception as e:  # noqa: BLE001
    saltó = False
    motivo = str(e)
s.shutdown()
c(not saltó and "bloqueada" in motivo,
  "una redirección hacia dentro se corta EN la redirección: mirar solo la URL de "
  "entrada dejaría la puerta abierta")

# ── 4. vuelve texto, no HTML ────────────────────────────────────────────────
t = _a_texto("<html><head><style>p{color:red}</style></head><body>"
             "<script>alert('x')</script><h1>T&iacute;tulo</h1>"
             "<p>Uno</p><ul><li>dos</li></ul></body></html>")
c("Título" in t and "Uno" in t and "dos" in t, "el texto legible sobrevive")
c("alert" not in t and "color:red" not in t,
  "el script y el estilo no: son bytes que se pagarían en cada vuelta sin decir nada")
c("<" not in t and ">" not in t, "y no queda ni una etiqueta")

# ── 5. la búsqueda: sin clave lo dice, y dice cuál ─────────────────────────
c(not buscar("").ok, "una búsqueda vacía no busca nada")
c(set(BUSCADORES) >= {"brave", "serper"},
  "hay más de un buscador posible: no se ata el proyecto a uno")

import genai.herramientas.web as _w  # noqa: E402

_orig = _w._claves
_w._claves = lambda: {}
r = buscar("lo que sea")
_w._claves = _orig
c(not r.ok and "claves.json" in r.salida,
  "sin ninguna clave, dice EXACTAMENTE qué añadir en vez de fallar en seco")
c("gemini" in r.salida and "`web`" in r.salida,
  "y recuerda las dos salidas: una clave de Gemini vale como buscador, y `web` sigue "
  "sirviendo para una URL que ya se conozca")

# ── la búsqueda sale por el proveedor QUE YA SE ESTÁ PAGANDO ───────────────
# Quien trabaja con GPT no espera que su búsqueda salga por Google. Se comprueba el
# ENRUTADO sin tocar la red: se sustituyen los backends por marcadores.
c(set(_w.POR_CEREBRO) == {"gemini", "openai"},
  "los dos proveedores de cerebro que además saben buscar están declarados")

_reales = dict(_w.POR_CEREBRO)
llamado = []
_w.POR_CEREBRO.update({p: (lambda con, k, n, _p=p: (llamado.append(_p),
                                                    Resultado(True, f"via {_p}"))[1])
                       for p in _w.POR_CEREBRO})
_w._claves = lambda: {"gemini": {"clave": "g"}, "openai": {"clave": "o"}}


class _Cer:
    def __init__(self, p):
        self.proveedor = p


llamado.clear(); _w.buscar("x", cerebro=_Cer("openai"))
c(llamado == ["openai"], "con cerebro de OpenAI, la búsqueda sale por OpenAI")
llamado.clear(); _w.buscar("x", cerebro=_Cer("gemini"))
c(llamado == ["gemini"], "con cerebro de Gemini, por Gemini")
llamado.clear(); _w.buscar("x", cerebro=None)
c(len(llamado) == 1,
  "sin cerebro de nube —el caso del Qwen LOCAL— se usa la primera clave que haya: "
  "el cerebro local no sabe buscar, pero el usuario no se queda sin búsqueda")

# si el propio falla, se intenta el otro antes de rendirse
_w.POR_CEREBRO["openai"] = lambda con, k, n: Resultado(False, "caído")
llamado.clear(); r2 = _w.buscar("x", cerebro=_Cer("openai"))
c(r2.ok and llamado == ["gemini"],
  "y si el proveedor propio falla se intenta el otro: quedarse sin buscar por una "
  "caída ajena sería peor que cambiar de puerta")
_w.POR_CEREBRO.clear(); _w.POR_CEREBRO.update(_reales)
_w._claves = _orig

# ── motores dedicados: el descriptor, ejecutado contra un servidor de mentira ──
# No hay claves de brave/serper/tavily, pero lo que hay que probar no es su nube:
# es que el DESCRIPTOR se convierta en la petición correcta y que la respuesta se
# parsee. Un servidor local con la forma de cada uno lo decide sin cuenta ninguna.
import json as _json  # noqa: E402


class _Falso(http.server.BaseHTTPRequestHandler):
    visto = {}

    def _responde(self, cuerpo):
        b = _json.dumps(cuerpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        _Falso.visto = {"metodo": "GET", "ruta": self.path,
                        "cabeceras": self.headers}
        self._responde({"web": {"results": [
            {"title": "Uno", "url": "https://ej.com/1", "description": "extracto uno"},
            {"title": "Dos", "url": "https://ej.com/2", "description": "extracto dos"}]}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _Falso.visto = {"metodo": "POST", "ruta": self.path,
                        "cabeceras": self.headers,
                        "cuerpo": _json.loads(self.rfile.read(n) or b"{}")}
        self._responde({"organic": [
            {"title": "Tres", "link": "https://ej.com/3", "snippet": "extracto tres"}]})

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), _Falso)
pto = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{pto}"

# GET con la clave en cabecera y la consulta escapada en la URL (forma de brave)
d_get = {**_w.BUSCADORES["brave"], "url": base + "/buscar?q={q}&count={n}"}
r = _w._por_motor("falso-get", d_get, {"clave": "SECRETA"}, "gatos y perros", 2)
c(r.ok and "Uno" in r.salida and "https://ej.com/1" in r.salida,
  "un motor GET devuelve título, URL y extracto de cada resultado")
c(_Falso.visto["cabeceras"].get("X-Subscription-Token") == "SECRETA",
  "la clave viaja en la cabecera que el descriptor dice, no en la URL")
c("gatos%20y%20perros" in _Falso.visto["ruta"] or "gatos+y+perros" in _Falso.visto["ruta"],
  "la consulta se escapa al ir en la URL")
c("count=2" in _Falso.visto["ruta"], "y el número de resultados también se sustituye")

# POST con cuerpo JSON (forma de serper y tavily)
d_post = {**_w.BUSCADORES["serper"], "url": base + "/search"}
r = _w._por_motor("falso-post", d_post, {"clave": "K2"}, "gatos y perros", 3)
c(r.ok and "Tres" in r.salida, "un motor POST parsea su lista propia («organic»)")
c(_Falso.visto["cuerpo"] == {"q": "gatos y perros", "num": 3},
  "en el cuerpo la consulta va SIN escapar —es JSON, no una URL— y `num` es un entero")
c(_Falso.visto["cabeceras"].get("X-API-KEY") == "K2",
  "y la clave en su cabecera — buscada sin distinguir mayúsculas, porque urllib "
  "normaliza el nombre y HTTP las trata como iguales")

c(_w._hondo({"web": {"results": [1, 2]}}, "web.results") == [1, 2],
  "el resultado se saca de donde cada motor lo anide («web.results»)")
c(_w._hondo({"a": 1}, "no.existe.aqui") == [],
  "y una ruta que no existe da lista vacía en vez de reventar")

# ── el motor se ELIGE, y si no está se dice ────────────────────────────────
_w._claves = lambda: {"busqueda": {"motor": "brave"}, "brave": {"clave": "b"},
                      "gemini": {"clave": "g"}}
op = _w._elegir_motor(_w._claves(), None)
c(len(op) == 1 and op[0][1] == "brave",
  "con `busqueda.motor` fijado se usa ESE motor, aunque haya otros configurados")

_w._claves = lambda: {"busqueda": {"motor": "tavily"}, "gemini": {"clave": "g"}}
r = _w.buscar("x")
c(not r.ok and "tavily" in r.salida and "callada" in r.salida,
  "y si el motor pedido no está configurado se DICE, en vez de usar otro a la callada: "
  "quien fija un motor quiere ese motor")

_w._claves = lambda: {"busqueda": {"motor": "proveedor"}, "brave": {"clave": "b"},
                      "openai": {"clave": "o"}}
op = _w._elegir_motor(_w._claves(), _Cer("openai"))
c([x[1] for x in op] == ["openai"],
  "«proveedor» fuerza a buscar por el proveedor del cerebro, ignorando los dedicados")

_w._claves = lambda: {"brave": {"clave": "b"}, "gemini": {"clave": "g"}}
op = _w._elegir_motor(_w._claves(), _Cer("gemini"))
c([x[1] for x in op] == ["brave", "gemini"],
  "en «auto» —el defecto— gana el dedicado, y el proveedor queda de reserva")

# el hueco para cualquier buscador que no venga de fábrica
_w._claves = lambda: {"mi_buscador": {"url": base, "lista": "web.results",
                                      "titulo": "title", "enlace": "url",
                                      "extracto": "description",
                                      "clave": "x"}}
op = _w._elegir_motor(_w._claves(), None)
c(len(op) == 1 and op[0][1] == "mi_buscador",
  "un buscador que NO viene de fábrica se describe en claves.json y funciona igual: "
  "es el hueco para cualquier otro, sin tocar código")

srv.shutdown()
_w._claves = _orig

raise SystemExit(c.fin())
