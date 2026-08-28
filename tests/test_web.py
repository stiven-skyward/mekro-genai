"""Acceso a la web (M7.3): opt-in y SSRF, que son las dos mitades del diseño.

Lo que se vigila NO es que sepa descargar una página —eso lo sabe `urllib`— sino:

1. que **no exista** si nadie la encendió, porque un arnés que presume de local y abre
   la red sin decirlo miente sobre lo que es;
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
from genai.herramientas.web import _a_texto, _publica, web

c = Cuenta("web")

# ── 1. opt-in: si nadie la enciende, no existe ──────────────────────────────
c("web" not in estandar(), "por defecto NO hay web: el agente ni sabe que es posible")
c("web" not in estandar(incluir_peligrosas=True),
  "ni siquiera con las peligrosas puestas: la red es una decisión aparte, no un grado")
c("web" in estandar(web=True), "y con web=True aparece, que es la única forma")
c(estandar(web=True)["web"].peligrosa,
  "es peligrosa: toca la red, así que pasa por permisos.py como bash")

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

raise SystemExit(c.fin())
