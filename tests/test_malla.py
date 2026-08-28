"""La malla (M6): un par sirve, otro delega, y el resultado llega EN CUARENTENA.

Lo que se vigila no es el camino feliz: es que la malla sea OPT-IN (en local ni existe
la herramienta), que la clave separe de verdad, que un sobre hostil no escape del
destino, y que nada remoto toque el árbol de trabajo del que delegó."""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from _util import Cuenta

RAIZ = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp(prefix="malla-prueba-"))
os.environ["MG_MALLA_CONFIG"] = str(tmp / "malla.json")

from genai import malla                       # noqa: E402
from genai.herramientas import estandar       # noqa: E402

c = Cuenta("malla")

# ── opt-in: en modo local la malla NO existe ────────────────────────────────
c("malla_delegar" not in estandar(), "en local, el agente no ve la malla siquiera")
c("malla_delegar" in estandar(malla=True), "con --malla, la herramienta aparece")
c(estandar(malla=True)["malla_delegar"].peligrosa,
  "delegar es peligrosa: sacar tu código de tu máquina pasa por permisos")

# ── sin configuración, delegar se niega sin romper nada ─────────────────────
r = malla.delegar("haz algo", "n1")
c(not r.ok and "no esta configurada" in r.salida,
  "sin malla.json, delegar avisa y el modo local sigue intacto")

# ── sobre hostil: no se escapa del destino ──────────────────────────────────
import io                                      # noqa: E402
import tarfile                                 # noqa: E402

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as t:
    info = tarfile.TarInfo("../fuera.txt")
    datos = b"deberia quedarse fuera"
    info.size = len(datos)
    t.addfile(info, io.BytesIO(datos))
import base64                                  # noqa: E402

hostil = base64.b64encode(buf.getvalue()).decode()
destino = tmp / "destino"
destino.mkdir()
try:
    malla._desempaquetar(hostil, destino)
    escapo = (tmp / "fuera.txt").exists()
except ValueError:
    escapo = False
c(not escapo, "una ruta con .. en el sobre se rechaza: no escribe fuera del destino")

# ── la malla de verdad: un par sirve con eco y otro delega ───────────────────
clave = "clave-de-prueba-1234"
Path(os.environ["MG_MALLA_CONFIG"]).write_text(
    json.dumps({"clave": clave, "pares": []}), encoding="utf-8")

s = socket.socket()
s.bind(("127.0.0.1", 0))
puerto = s.getsockname()[1]
s.close()

hilo = threading.Thread(
    target=malla.servir, args=(puerto, clave, 2, "eco"), daemon=True)
hilo.start()
time.sleep(0.5)

# el par rechaza a quien no trae la clave
try:
    malla._pedir(f"127.0.0.1:{puerto}", "/tarea", {"encargo": "x", "semilla": ""},
                 "clave-equivocada")
    paso_sin_clave = True
except Exception:
    paso_sin_clave = False
c(not paso_sin_clave, "sin la clave compartida, el par no acepta la tarea")

# ahora sí: delegar de verdad desde un directorio de trabajo
Path(os.environ["MG_MALLA_CONFIG"]).write_text(
    json.dumps({"clave": clave, "pares": [f"127.0.0.1:{puerto}"]}), encoding="utf-8")
trabajo = tmp / "trabajo"
trabajo.mkdir()
(trabajo / "dato.txt").write_text("el par debe verme", encoding="utf-8")
antes = os.getcwd()
os.chdir(trabajo)
r = malla.delegar("saluda y termina", "tarea1")
c(r.ok and "CUARENTENA" in r.salida,
  "delegar devuelve el control al momento y avisa de la cuarentena")
c((Path(".genai") / "fondo" / "tarea1.pid").exists(),
  "queda un fondo esperando: el aviso llegará por el bucle, como cualquier otro")

listo = False
for _ in range(120):                       # el par corre con eco: es cosa de segundos
    if (Path(".genai") / "fondo" / "tarea1.rc").exists():
        listo = True
        break
    time.sleep(0.5)
c(listo, "el poller escribe el .rc del fondo cuando el par termina")

cuarentena = Path(".genai") / "malla" / "tarea1"
c((cuarentena / "informe.json").exists(),
  "el resultado aterriza en cuarentena con su informe")
informe = json.loads((cuarentena / "informe.json").read_text(encoding="utf-8"))
c("segundos" in informe and informe.get("motivo"),
  "el informe trae motivo y segundos (la contabilidad de reciprocidad)")
c((cuarentena / "dato.txt").exists(),
  "la semilla viajó al par y volvió dentro de la cuarentena")
c(not (trabajo / "informe.json").exists(),
  "NADA remoto toca el árbol de trabajo: el verificador local decide después")
cta = malla.cuenta()
c("donados" in cta and "consumidos" in cta,
  "la cuenta anota segundos donados y consumidos, sin monedas ni cadenas")
os.chdir(antes)
shutil.rmtree(tmp, ignore_errors=True)

raise SystemExit(c.fin())
