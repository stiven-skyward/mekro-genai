"""GitHub Copilot por device flow: la máquina de estados, sin tocar GitHub.

El device flow es una conversación con estados que solo se ven cuando algo va mal:
esperando autorización, «vas muy rápido», código caducado, cancelado. Probar eso contra
GitHub de verdad exigiría una cuenta y no sería repetible, así que aquí GitHub se
sustituye por una función que devuelve lo que se le diga.

Lo que se vigila:

1. que **cada respuesta de GitHub lleve a lo que debe** — sobre todo las malas;
2. que el token de Copilot, que **caduca en minutos**, se renueve antes de caducar;
3. que el token viva en **su propio fichero con permisos 600**, no mezclado con las
   claves que el usuario escribió a mano;
4. que cuando no hay suscripción se diga ESO, y no un 403 pelado.
"""
import json
import stat
import tempfile
import time
import urllib.error
from pathlib import Path

from _util import Cuenta

from genai import copilot

c = Cuenta("copilot")
tmp = Path(tempfile.mkdtemp(prefix="copilot-"))
copilot.FICHERO = tmp / "copilot.json"

_posts: list = []
_gets: list = []


def falso_post(url, datos, cabeceras=None):
    return _posts.pop(0)


def falso_get(url, cabeceras):
    r = _gets.pop(0)
    if isinstance(r, Exception):
        raise r
    return r


copilot._post = falso_post
copilot._get = falso_get
copilot.time = type("t", (), {"time": time.time, "sleep": lambda *_: None})()

DEV = {"device_code": "dc", "user_code": "ABCD-1234", "interval": 0,
       "expires_in": 900, "verification_uri": "https://github.com/login/device"}

# ── 1. el camino bueno ─────────────────────────────────────────────────────
_posts[:] = [DEV, {"error": "authorization_pending"}, {"access_token": "gho_xyz"}]
ok, msg = copilot.entrar(imprimir=lambda *_: None)
c(ok and "guardada" in msg,
  "«authorization_pending» NO es un fallo: es la respuesta normal mientras el humano "
  "va al navegador, y se sigue esperando")
c(json.loads(copilot.FICHERO.read_text())["github"] == "gho_xyz",
  "y al autorizar se guarda el token de GitHub")
c(stat.S_IMODE(copilot.FICHERO.stat().st_mode) == 0o600,
  "en un fichero 600 y PROPIO: no es una clave que escribiera el usuario sino una "
  "credencial que este programa obtuvo en su nombre, y mezclarlas haría que borrar "
  "una borrase la otra")

# ── 2. las respuestas malas, una a una ─────────────────────────────────────
for err, espera in (("expired_token", "caducó"), ("access_denied", "cancelaste"),
                    ("otra_cosa", "otra_cosa")):
    _posts[:] = [DEV, {"error": err}]
    ok, msg = copilot.entrar(imprimir=lambda *_: None)
    c(not ok and espera in msg, f"«{err}» se traduce a algo que se entiende")

_posts[:] = [DEV, {"error": "slow_down", "interval": 1},
             {"access_token": "gho_2"}]
ok, _ = copilot.entrar(imprimir=lambda *_: None)
c(ok, "«slow_down» afloja el sondeo en vez de rendirse: es un aviso, no un error")

_posts[:] = [{"nada": "que ver"}]
ok, msg = copilot.entrar(imprimir=lambda *_: None)
c(not ok and "inesperada" in msg,
  "una respuesta sin device_code se dice, no revienta con un KeyError")

# ── 3. el token de Copilot caduca en minutos y se renueva ──────────────────
copilot.FICHERO.write_text(json.dumps({"github": "gho_xyz"}), encoding="utf-8")
_gets[:] = [{"token": "cop_1", "expires_at": time.time() + 1500}]
t, q = copilot.token()
c(t == "cop_1" and not q, "con sesión de GitHub se canjea un token de Copilot")

_gets[:] = []                                   # si volviera a pedir, reventaría
t2, _ = copilot.token()
c(t2 == "cop_1",
  "y mientras siga válido se REUTILIZA: pedirlo en cada llamada sería una petición de "
  "más por vuelta")

d = json.loads(copilot.FICHERO.read_text())
d["caduca"] = time.time() + 30                  # dentro del margen de 60 s
copilot.FICHERO.write_text(json.dumps(d), encoding="utf-8")
_gets[:] = [{"token": "cop_2", "expires_at": time.time() + 1500}]
t3, _ = copilot.token()
c(t3 == "cop_2",
  "a menos de 60 s de caducar se renueva ANTES: si no, caducaría a mitad de una "
  "petición larga y la vuelta se perdería")

# ── 4. sin suscripción se dice ESO ─────────────────────────────────────────
copilot.FICHERO.write_text(json.dumps({"github": "gho_xyz"}), encoding="utf-8")
_gets[:] = [urllib.error.HTTPError("u", 403, "Forbidden", {}, None)]
t, q = copilot.token()
c(not t and "suscripción" in q,
  "un 403 al pedir el token de Copilot se traduce a «no tienes suscripción activa o "
  "tu organización no lo permite», que es lo que casi siempre significa")
_gets[:] = [urllib.error.HTTPError("u", 500, "Server Error", {}, None)]
t, q = copilot.token()
c(not t and "500" in q, "y un error de servidor se dice tal cual, sin adivinar")

copilot.FICHERO.unlink(missing_ok=True)
t, q = copilot.token()
c(not t and "genai copilot entrar" in q,
  "sin sesión, la queja trae el comando exacto para arreglarlo")
c("suscripción activa" in q, "y avisa de que hace falta suscripción de Copilot")

# ── salir borra ────────────────────────────────────────────────────────────
copilot.FICHERO.write_text("{}", encoding="utf-8")
copilot.salir()
c(not copilot.FICHERO.exists(), "salir borra la credencial del disco")
c("sin sesión" in copilot.estado(), "y el estado lo refleja")

# ── lo que NO se promete ───────────────────────────────────────────────────
fuente = (Path(__file__).resolve().parents[1] / "genai" / "copilot.py"
          ).read_text(encoding="utf-8")
c("no oficial" in fuente or "no* es una integración" in fuente or
  "no es una integración" in fuente,
  "el módulo dice en su cabecera que esto NO es una integración bendecida por GitHub: "
  "usa el identificador de cliente del editor, funciona hoy, y puede dejar de "
  "funcionar sin aviso")
c("suscripción activa" in fuente, "y que hace falta suscripción de Copilot")

raise SystemExit(c.fin())
