"""Entrar con la cuenta de Google y usar la cuota de la suscripción.

El flujo de OAuth es una conversación con estados que solo se ven cuando algo va mal, y
uno de esos estados es un ataque. Se prueba con Google simulado, salvo la parte que sí
se puede verificar de verdad sin la cuenta de nadie: **que el cliente exista**.

Lo que se vigila:

1. que el **`state` se compruebe** — sin eso, cualquier página que tengas abierta puede
   mandarle a tu servidor local un código suyo y dejarte con la sesión de otra cuenta;
2. que el token se **renueve antes de caducar**, y que una sesión invalidada por Google
   se traduzca a «vuelve a entrar» y no a un 400;
3. que Code Assist **envuelva y desenvuelva** bien: por dentro es el mismo Gemini, pero
   la clave va en cabecera y el cuerpo viaja dentro de `request`;
4. que la credencial viva **en su propio fichero con 600**.
"""
import json
import os
import stat
import tempfile
import threading
import time
import urllib.error
import urllib.parse
from pathlib import Path

from _util import Cuenta

from genai import google_cuenta as G

c = Cuenta("google_cuenta")
tmp = Path(tempfile.mkdtemp(prefix="goog-"))
G.FICHERO = tmp / "google.json"

# ── las credenciales no están en el repositorio ────────────────────────────
# Las credenciales del cliente NO están en el repositorio, a propósito: son de
# gemini-cli, no nuestras, y GitHub rechazó con razón el primer intento de subirlas.
fuente_mod = (Path(__file__).resolve().parents[1] / "genai" / "google_cuenta.py"
              ).read_text(encoding="utf-8")
import re as _re
c(not _re.search(r"[0-9]{6,}-[a-z0-9]{10,}\.apps\.googleusercontent\.com", fuente_mod),
  "el identificador de cliente NO está escrito en el módulo: publicarlo en un "
  "repositorio público lo esparciría, y no es nuestro")
c(not _re.search(r"GOCSPX-[A-Za-z0-9_\-]{20,}", fuente_mod),
  "ni el secreto")

os.environ.pop("GENAI_GOOGLE_CLIENTE", None)
os.environ.pop("GENAI_GOOGLE_SECRETO", None)
G.CLIENTE_FICHERO = tmp / "no-existe.json"
# La máquina que corre esto puede TENER gemini-cli instalado —la del autor lo tiene—,
# así que se aísla: lo que se prueba es qué pasa cuando no hay de dónde sacarlas.
_gemini_real = G._de_gemini_cli
G._de_gemini_cli = lambda: ("", "")
cid, sec, q = G.credenciales()
c(not cid and "gemini-cli" in q and "AI Studio" in q,
  "sin ellas se dice CÓMO conseguirlas —tres formas, la fácil primero— y se recuerda "
  "la alternativa que no depende de nada de esto")

os.environ["GENAI_GOOGLE_CLIENTE"] = "111-abc" + ".apps.googleuser" + "content.com"
os.environ["GENAI_GOOGLE_SECRETO"] = "GOC" + "SPX-" + "de-mentira-para-prueba"
cid, sec, q = G.credenciales()
c(cid.endswith(".apps.googleusercontent.com") and not q,
  "y con las variables de entorno puestas, se usan")

# ── emparejar de gemini-cli: DOS clientes y un secreto ─────────────────────
# Con gemini-cli 0.57.0 de verdad, coger el primero de cada patrón emparejaba mal y
# Google respondía «client secret is invalid». Se empareja por cercanía y se verifica.
fuente_mod2 = fuente_mod
c("_pareja_valida" in fuente_mod2 and "cercanía" in fuente_mod2.lower(),
  "las credenciales se emparejan por CERCANÍA en el fichero y la pareja se verifica "
  "contra Google antes de aceptarla: gemini-cli lleva dos client_id y un solo secreto")
c("invalid_grant" in fuente_mod2,
  "y la verificación no autoriza nada: manda un código inventado y mira de qué se "
  "queja Google — del código si la pareja casa, del cliente si no")

G.CLIENTE_FICHERO = tmp / "cliente.json"
G.CLIENTE_FICHERO.write_text(json.dumps(
    {"cliente": "222-xyz" + ".apps.googleuser" + "content.com", "secreto": "GOC" + "SPX-" + "del-fichero"}),
    encoding="utf-8")
os.environ.pop("GENAI_GOOGLE_CLIENTE"); os.environ.pop("GENAI_GOOGLE_SECRETO")
c(G.credenciales()[0].startswith("222-"),
  "o del fichero de configuración del usuario, si no hay variables")
os.environ["GENAI_GOOGLE_CLIENTE"] = "111-abc" + ".apps.googleuser" + "content.com"
os.environ["GENAI_GOOGLE_SECRETO"] = "GOC" + "SPX-" + "de-mentira-para-prueba"
c("cloud-platform" in G.AMBITOS,
  "se pide `cloud-platform`, que es el ámbito que Code Assist necesita — y es también "
  "la razón de usar bucle local en vez de flujo de dispositivo, que no lo admite")

# ── 1. el `state`: la parte que impide que te cuelen una sesión ────────────
_orig_post = G._post
G._post = lambda *a, **k: (_ for _ in ()).throw(
    AssertionError("no se debe canjear un código con `state` que no cuadra"))

srv_salida = []
hilo = threading.Thread(
    target=lambda: srv_salida.append(G.entrar(imprimir=lambda *_: None, espera=6,
                                              abrir_navegador=False)), daemon=True)
hilo.start()
time.sleep(1.0)
# se simula lo que haría una página cualquiera: mandar un código con otro `state`
G._Recogida.recibido = {"code": "codigo-de-otro", "state": "no-es-el-mio"}
hilo.join(10)
ok, msg = srv_salida[0]
c(not ok and "state" in msg and "No se guarda nada" in msg,
  "un código con `state` que no cuadra se RECHAZA sin canjearlo: si no, cualquier "
  "página abierta podría dejarte con la sesión de otra cuenta")
G._post = _orig_post
c(not G.FICHERO.exists(), "y no se guardó nada en el disco")

# ── el camino bueno ────────────────────────────────────────────────────────
G._post = lambda url, datos, cab=None, json_cuerpo=None: {
    "refresh_token": "ref_1", "access_token": "acc_1", "expires_in": 3600}
ok, msg = G.canjear("codigo", "http://localhost:1")
c(ok and "guardada" in msg, "con un código bueno se canjea y se guarda")
c(stat.S_IMODE(G.FICHERO.stat().st_mode) == 0o600,
  "en un fichero 600 y propio: no es una clave que escribiera el usuario, sino una "
  "credencial que este programa obtuvo en su nombre")
c(json.loads(G.FICHERO.read_text())["refresco"] == "ref_1",
  "lo que se guarda es el `refresh_token`, que es lo que sobrevive")

G._post = lambda *a, **k: {"access_token": "acc_1", "expires_in": 3600}
c(G.acceso()[0] == "acc_1", "y el acceso está disponible")

# sin refresh_token, Google no dio lo que hace falta
G.FICHERO.unlink(missing_ok=True)
G._post = lambda *a, **k: {"access_token": "solo_acceso"}
ok, msg = G.canjear("codigo", "http://localhost:1")
c(not ok and "refresh_token" in msg,
  "si Google no da `refresh_token` se dice: sin él, la sesión moriría en una hora y "
  "el usuario no entendería por qué")

# ── 2. renovación ──────────────────────────────────────────────────────────
G.FICHERO.write_text(json.dumps(
    {"refresco": "ref_1", "acceso": "viejo", "caduca": time.time() + 30}),
    encoding="utf-8")
G._post = lambda *a, **k: {"access_token": "nuevo", "expires_in": 3600}
c(G.acceso()[0] == "nuevo",
  "a menos de 60 s de caducar se renueva ANTES: si no, caducaría a mitad de una "
  "petición larga y se perdería la vuelta")

G.FICHERO.write_text(json.dumps(
    {"refresco": "ref_1", "acceso": "vale", "caduca": time.time() + 9999}),
    encoding="utf-8")
G._post = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no tocaba renovar"))
c(G.acceso()[0] == "vale", "y mientras valga no se renueva: sería una petición de más")


def _http(codigo, cuerpo=b"{}"):
    return urllib.error.HTTPError("u", codigo, "x", {}, None)


G.FICHERO.write_text(json.dumps({"refresco": "ref_1"}), encoding="utf-8")


def _falla_invalid_grant(*a, **k):
    e = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
    e.read = lambda: json.dumps({"error": "invalid_grant"}).encode()
    raise e


G._post = _falla_invalid_grant
t, q = G.acceso()
c(not t and "genai google entrar" in q,
  "una sesión que Google invalidó —contraseña cambiada, permiso revocado— se traduce "
  "a «vuelve a entrar», no a un 400 pelado")

G.FICHERO.unlink(missing_ok=True)
t, q = G.acceso()
c(not t and "AI Studio" in q,
  "y sin sesión se recuerda la alternativa que NO depende de esto: una clave de AI "
  "Studio, que tiene nivel gratuito")

# ── 3. Code Assist envuelve y desenvuelve ──────────────────────────────────
from genai.cerebro.base import Mensaje  # noqa: E402
from genai.cerebro.nube import CerebroNube  # noqa: E402

n = CerebroNube.__new__(CerebroNube)
n.dialecto, n.modelo, n.clave = "gemini", "gemini-2.5-pro", "acc_tok"
n.url, n.temperatura, n.asist = G.ASIST, 0.0, "proyecto-x"
n.cache = {"leidos": 0, "totales": 0, "escritos": 0, "escrituras": 0}
n._cache_g, n.cachear, n._firmas_pensamiento = None, False, {}

visto = {}
import genai.cerebro.nube as NU  # noqa: E402

_pedir_real = NU._pedir
NU._pedir = lambda url, cuerpo, cabs: (
    visto.update(url=url, cuerpo=cuerpo, cabs=cabs),
    {"response": {"candidates": [{"content": {"parts": [{"text": "hola"}]}}],
                  "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 2}}})[1]
texto, llamadas, ent, sal = n._gemini([Mensaje("usuario", "di hola")], [], 16)
NU._pedir = _pedir_real

c(texto == "hola" and ent == 9,
  "la respuesta de Code Assist viene envuelta en `response` y se DESENVUELVE: por "
  "dentro es el mismo Gemini")
c(visto["cabs"].get("Authorization", "").startswith("Bearer "),
  "la credencial va en cabecera, no en la URL como con la clave de AI Studio")
c(visto["cuerpo"].get("project") == "proyecto-x" and "request" in visto["cuerpo"],
  "y la petición viaja dentro de `request`, con el proyecto de la cuenta al lado")
c("?key=" not in visto["url"] and visto["url"].endswith(":generateContent"),
  "la URL no lleva clave: mezclar las dos formas daría un 401 difícil de leer")

# ── 4. salir borra ─────────────────────────────────────────────────────────
G.FICHERO.write_text("{}", encoding="utf-8")
G.salir()
c(not G.FICHERO.exists(), "salir borra la credencial del disco")
c("sin sesión" in G.estado(), "y el estado lo refleja")

# ── lo que NO se promete ───────────────────────────────────────────────────
fuente = (Path(__file__).resolve().parents[1] / "genai" / "google_cuenta.py"
          ).read_text(encoding="utf-8")
c("no es una integración que Google bendiga" in fuente,
  "el módulo dice en su cabecera que esto NO está bendecido para terceros: usa el "
  "cliente de gemini-cli, funciona hoy, y puede cortarse sin aviso")
c("AI Studio" in fuente,
  "y señala la alternativa sin incertidumbre, que además tiene nivel gratuito")

raise SystemExit(c.fin())
