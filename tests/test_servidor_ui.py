"""La interfaz gráfica (`genai ui`): lanzar tareas en vivo desde el servidor.

Lo que se vigila, con el cerebro `eco` para no depender de ningún modelo real:

1. que el **id de la `Sesion` sea el mismo que el del registro de sesiones** — el
   fallo real que esto encontró: `Sesion` generaba su propio UUID al azar, y
   `/transcripcion` (y `genai sesiones compartir`, que ya existía antes de esta
   interfaz) buscaban el fichero por el id del registro. Dos identidades para la
   misma sesión que por construcción nunca coincidían, y la transcripción salía
   siempre vacía;
2. que un permiso pendiente en modo `preguntar` se vea por HTTP y se pueda
   responder desde fuera del proceso — es lo que sustituye al `input()` de consola
   cuando quien pregunta es una página y no una terminal;
3. que la página (`GET /`) cargue SIN clave pero la lleve embebida, y que todo lo
   demás siga exigiéndola;
4. que `/claves` nunca devuelva un secreto, solo si existe.
"""
import json
import os
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

from _util import Cuenta

from genai import servidor, sesiones

c = Cuenta("servidor_ui")
tmp = Path(tempfile.mkdtemp(prefix="ui-"))
os.chdir(tmp)
os.environ["MG_SESIONES"] = str(tmp / "s")
# MG_CLAVES aísla /claves de ~/.config/genai/claves.json —el fichero REAL de
# secretos del usuario—, que es lo que esta prueba tocaba antes con un backup/
# restore manual. Eso corría carrera con `scripts/guardian.py` (ejecuta la misma
# suite cada 15 min en segundo plano): la primera vez que se probó `genai ui` en
# frío, guardián y esta prueba escribieron el fichero real a la vez y una de las
# dos rondas vio el estado a medio restaurar de la otra. Con ruta propia, ninguna
# ejecución concurrente de esta prueba —ni la del guardián, ni una manual— puede
# ya rozar el fichero de nadie más.
os.environ["MG_CLAVES"] = str(tmp / "claves.json")

srv = servidor.servir(puerto=0, bloquear=False)
base = f"http://127.0.0.1:{srv.server_address[1]}"
K = servidor.clave()


def pide(ruta, cuerpo=None, k=K):
    cab = {"Content-Type": "application/json"}
    if k:
        cab["X-Genai-Clave"] = k
    r = urllib.request.Request(
        base + ruta, json.dumps(cuerpo).encode() if cuerpo is not None else None, cab)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── la página: sin clave, pero con la clave dentro ──────────────────────────
r = urllib.request.urlopen(base + "/", timeout=10)
html = r.read().decode()
c(r.status == 200, "`GET /` responde sin cabecera de clave")
c(K in html, "y la página trae la clave real embebida: sin eso, sus propias "
             "llamadas fetch() no podrían autenticarse")

# ── el resto de rutas sigue exigiendo clave ─────────────────────────────────
c(pide("/sesiones", k="")[0] == 401, "sin clave, /sesiones sigue dando 401")
c(pide("/cerebros", k="")[0] == 401, "y /cerebros también")
c(pide("/claves", k="")[0] == 401, "y /claves también")

# ── /cerebros y /claves: forma y honestidad ─────────────────────────────────
cod, cer = pide("/cerebros")
c(cod == 200 and {"local", "fabrica", "configurados", "suscripciones"} <= set(cer),
  "/cerebros trae las cuatro fuentes que la interfaz necesita para el selector")

# ruta AISLADA (MG_CLAVES, fijada arriba) — nunca ~/.config/genai/claves.json real,
# así que no hace falta backup/restore ni compartir el fichero con nadie más
_claves_prueba = Path(os.environ["MG_CLAVES"])
_claves_prueba.parent.mkdir(parents=True, exist_ok=True)
_claves_prueba.write_text(json.dumps({"gemini": {"clave": "SECRETO-DE-PRUEBA-12345"}}),
                          encoding="utf-8")

cod, cl = pide("/claves")
c(cod == 200 and cl.get("gemini", {}).get("configurada") is True,
  "/claves dice que gemini está configurado")
c("SECRETO-DE-PRUEBA-12345" not in json.dumps(cl),
  "pero NUNCA el secreto — ni siquiera truncado: la interfaz de ajustes solo "
  "necesita saber que existe, no verlo")

# guardar una clave nueva no debe pisar la que ya había
cod, r2 = pide("/claves", {"proveedor": "openai", "clave": "otra-clave-de-prueba"})
c(cod == 200, "se puede guardar una clave nueva por HTTP")
tras = json.loads(_claves_prueba.read_text(encoding="utf-8"))
c(tras["gemini"]["clave"] == "SECRETO-DE-PRUEBA-12345",
  "y la que ya había (gemini) sigue intacta: se completa el fichero, no se "
  "sobrescribe entero")
c(tras["openai"]["clave"] == "otra-clave-de-prueba", "la nueva sí quedó guardada")

cod, r3 = pide("/claves", {"proveedor": "", "clave": ""})
c(cod == 400, "proveedor o clave vacíos se rechazan, no se guardan como entrada vacía")

# ── lanzar una tarea real con `eco`, y el ID UNIFICADO ──────────────────────
s = sesiones.crear("prueba de la interfaz")
cod, r = pide(f"/sesiones/{s['id']}/lanzar",
             {"encargo": "di hola", "cerebro": "eco", "modo": "lista"})
c(cod == 200 and r["ok"], "lanzar una tarea responde de inmediato, sin esperar a que "
                          "termine (corre en un hilo de fondo)")

limite = time.time() + 10
while time.time() < limite:
    _, s2 = pide(f"/sesiones/{s['id']}")
    if not s2.get("en_curso"):
        break
    time.sleep(0.2)
c(s2.get("motivo") == "fin", "la tarea con `eco` termina, y el estado lo refleja")

# pequeño reintento: entre que `en_curso` pasa a False y el hilo de fondo termina de
# escribir el fichero y soltar la sesión hay una ventana de milisegundos — un cliente
# real (esta misma página) también volvería a sondear, así que la prueba hace lo mismo
# en vez de exigir que ambas cosas sean atómicas cuando no hace falta que lo sean.
tr = {}
for _ in range(20):
    cod, tr = pide(f"/sesiones/{s['id']}/transcripcion")
    if tr.get("mensajes"):
        break
    time.sleep(0.1)
c(cod == 200 and len(tr.get("mensajes", [])) >= 2,
  "la transcripción SE ENCUENTRA por el id del registro: es el fallo real que esto "
  "encontró — antes `Sesion` generaba su propio id al azar, distinto del id con el "
  "que se pedía, y esta llamada devolvía siempre «aún no ha guardado transcripción»")
c(not tr.get("aviso"), "y no lleva el aviso de «sin transcripción», porque sí la hay")

guardado = list((tmp / "logs" / "sesiones").glob(f"*{s['id']}*.json"))
c(len(guardado) == 1,
  "el fichero en disco se llama con el MISMO id que el registro, no con uno propio "
  "de la Sesion")

cod, r4 = pide(f"/sesiones/{s['id']}/lanzar", {"encargo": "otra vez", "cerebro": "eco"})
c(cod == 200 and r4["ok"],
  "sobre una sesión ya libre (la primera terminó), lanzar de nuevo funciona: no "
  "queda bloqueada para siempre por haberse usado una vez")
limite = time.time() + 10
while time.time() < limite and pide(f"/sesiones/{s['id']}")[1].get("en_curso"):
    time.sleep(0.1)

# el guardián de verdad: NO se puede lanzar una segunda tarea MIENTRAS la primera
# sigue en memoria (`_EN_VIVO`). Se prueba el guardián directamente y no por una
# carrera de hilos, que sería un test que a veces pasa y a veces no.
otra = sesiones.crear("ocupada")
servidor._EN_VIVO[otra["id"]] = object()
ok, msg = servidor._lanzar(otra["id"], {"encargo": "x", "cerebro": "eco"})
c(not ok and "en curso" in msg,
  "y si SÍ hay una tarea viva para ese id, lanzar otra se rechaza en vez de correr "
  "dos turno() a la vez sobre la misma Sesion")
del servidor._EN_VIVO[otra["id"]]

# ── el permiso pendiente: lo que sustituye a input() cuando pregunta una página ──
# `lanzar` no acepta un `guion` por HTTP a propósito —no tiene sentido pedirle a una
# interfaz que apunte a un fichero del disco del SERVIDOR—, así que para forzar una
# herramienta peligrosa en modo `preguntar` se arma un `eco` con guion directamente y
# se sustituye la función `cargar` que `_lanzar` usa por dentro.
s3 = sesiones.crear("prueba de permiso")
from genai.cerebro import cargar as _cargar  # noqa: E402

cerebro_con_guion = _cargar("eco", guion=[
    "<tool_call>\n" + json.dumps(
        {"name": "bash", "arguments": {"comando": "echo hola"}}) + "\n</tool_call>",
    "listo"])

import genai.cerebro as _cer_mod  # noqa: E402

_orig_cargar_real = _cer_mod.cargar
_cer_mod.cargar = lambda nombre, **kw: cerebro_con_guion
try:
    ok, msg = servidor._lanzar(s3["id"], {"encargo": "haz algo", "cerebro": "eco",
                                          "modo": "preguntar"})
    c(ok, f"se lanza en modo preguntar con una herramienta peligrosa en el guion ({msg})")

    limite = time.time() + 10
    pendiente = None
    while time.time() < limite:
        _, s4 = pide(f"/sesiones/{s3['id']}")
        if s4.get("pregunta_pendiente"):
            pendiente = s4["pregunta_pendiente"]
            break
        time.sleep(0.1)
    c(pendiente is not None and pendiente["herramienta"] == "bash",
      "el permiso pendiente aparece en el estado de la sesión, con la herramienta "
      "que lo pidió — es lo que la página sondea para abrir el modal")
    c(pendiente["argumentos"].get("comando") == "echo hola",
      "y con los argumentos exactos, para que quien decide sepa qué está aprobando")

    cod, r6 = pide(f"/sesiones/{s3['id']}/responder", {"permitido": True})
    c(cod == 200, "responder al permiso pendiente se acepta")

    limite = time.time() + 10
    while time.time() < limite:
        _, s5 = pide(f"/sesiones/{s3['id']}")
        if not s5.get("en_curso"):
            break
        time.sleep(0.1)
    c(s5.get("motivo") == "fin", "tras permitir, la tarea sigue y termina")

    cod, r7 = pide(f"/sesiones/{s3['id']}/responder", {"permitido": True})
    c(cod == 409, "responder cuando NO hay nada pendiente se rechaza, no se acepta "
                  "como si nada")
finally:
    _cer_mod.cargar = _orig_cargar_real

srv.shutdown()
raise SystemExit(c.fin())
