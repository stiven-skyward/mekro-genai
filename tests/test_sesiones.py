"""Multi-sesión y servidor: varios agentes a la vez sobre el mismo proyecto.

Lo que se vigila son las tres formas de que esto salga mal, y las tres son silenciosas:

1. **Un candado huérfano** —el proceso murió con la sesión cogida— dejaría la sesión
   bloqueada para siempre, y la única salida sería borrar ficheros a mano.
2. **Un candado que no protege**: dos procesos escribiendo el mismo hilo lo corrompen.
3. **Prometer más de lo que se puede cumplir**: el candado es de sesión, no de
   ficheros. Dos agentes pueden editar el mismo fichero del repositorio y eso no lo
   arregla ningún candado. Se AVISA, que es lo honesto.

Y del servidor: que sin clave no se entre, y que no escuche fuera de esta máquina.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from _util import Cuenta

from genai import servidor, sesiones

c = Cuenta("sesiones")
tmp = Path(tempfile.mkdtemp(prefix="ses-"))
raiz = tmp / "s"

# ── crear y listar ─────────────────────────────────────────────────────────
a = sesiones.crear("arreglar el carrito", raiz=raiz)
b = sesiones.crear("subir la cobertura", raiz=raiz)
c(a["id"] != b["id"], "cada sesión tiene su identidad")
todas = sesiones.listar(raiz=raiz)
c(len(todas) == 2, "las dos aparecen en el listado")
c(all("viva" in s and "rancia" in s for s in todas),
  "y el listado dice de cada una si está viva y si está rancia, sin tener que abrirla")

# ── escritura atómica: un lector no puede ver un fichero de sesión a medias ──
# El fallo real que esto reproduce: `_guardar()` hacía `write_text()` a secas
# (trunca a 0 bytes, LUEGO escribe), y `listar()` DESCARTA cualquier sesión cuya
# lectura falle —un `GET /sesiones/<id>` real podía devolver 404 en ese instante.
# Con `os.replace()` atómico, un `listar()` concurrente tiene que ver SIEMPRE el
# fichero viejo entero o el nuevo entero. Se estresa de verdad con un hilo
# escribiendo sin parar mientras el principal lee sin parar — no una prueba de
# temporización con sleep(), que la habría dejado pasar igual que antes.
import threading  # noqa: E402

s_estres = sesiones.crear("estrés de escritura", raiz=raiz)
parar_escritura = threading.Event()


def _escribir_sin_parar():
    v = 0
    while not parar_escritura.is_set():
        sesiones.latir(s_estres["id"], raiz=raiz, vueltas=v)
        v += 1


hilo_escritor = threading.Thread(target=_escribir_sin_parar, daemon=True)
hilo_escritor.start()
lecturas_malas = 0
for _ in range(400):
    encontrada = next((x for x in sesiones.listar(raiz=raiz) if x["id"] == s_estres["id"]),
                      None)
    if encontrada is None or "vueltas" not in encontrada:
        lecturas_malas += 1
parar_escritura.set()
hilo_escritor.join(timeout=5)
c(lecturas_malas == 0,
  f"{lecturas_malas} de 400 lecturas concurrentes vieron la sesión a medio "
  "escribir o desaparecida — con escritura atómica tienen que ser 0")
c(not list(raiz.glob("*.tmp-*")),
  "y no queda ningún fichero temporal suelto: el rename limpia tras de sí")

# ── el candado ─────────────────────────────────────────────────────────────
s, q = sesiones.tomar(a["id"], raiz=raiz)
c(s and s["duenyo"] == os.getpid(), "tomar una sesión la marca con el PID de quien la coge")
s2, q2 = sesiones.tomar(a["id"], raiz=raiz)
c(s2 is not None, "el MISMO proceso puede volver a tomarla: no se bloquea a sí mismo")

# un dueño vivo y ajeno: se respeta
otro = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
sesiones.latir(a["id"], raiz=raiz, duenyo=otro.pid)
s3, q3 = sesiones.tomar(a["id"], raiz=raiz)
c(s3 is None and str(otro.pid) in q3,
  "si otro proceso VIVO la tiene, se niega y se dice quién la tiene")
c("mismo proyecto" in q3,
  "y la queja explica la salida: abrir otra sesión, porque dos agentes SÍ pueden "
  "trabajar en el mismo proyecto")
otro.terminate(); otro.wait()

# un dueño muerto: el candado se recoge
s4, q4 = sesiones.tomar(a["id"], raiz=raiz)
c(s4 is not None and s4["duenyo"] == os.getpid(),
  "con el dueño MUERTO el candado se recoge: si no, un Ctrl-C dejaría la sesión "
  "bloqueada para siempre y habría que borrar ficheros a mano")
c(s4.get("recogidas") == 1,
  "y queda anotado que se recogió, porque eso significa que alguien murió a medias")

sesiones.soltar(a["id"], raiz=raiz)
c(sesiones.listar(raiz=raiz)[0].get("duenyo") in (0, None) or
  all(x["duenyo"] == 0 for x in sesiones.listar(raiz=raiz) if x["id"] == a["id"]),
  "soltar deja la sesión libre para el siguiente")

c(sesiones.tomar("no-existe", raiz=raiz)[0] is None, "una sesión que no está se dice")
c(not sesiones._vivo(0) and not sesiones._vivo(999999),
  "un PID imposible no se toma por vivo")
c(sesiones._vivo(os.getpid()), "y el proceso actual sí lo está")

# ── lo que el candado NO puede impedir, se avisa ───────────────────────────
sesiones.tomar(a["id"], raiz=raiz)
sesiones.tomar(b["id"], raiz=raiz)
sesiones.latir(a["id"], raiz=raiz, tocados=["carrito.py", "prueba.py"])
sesiones.latir(b["id"], raiz=raiz, tocados=["prueba.py", "otro.py"])
ch = sesiones.conflictos(raiz=raiz)
c([f for f, _ in ch] == ["prueba.py"],
  "dos sesiones vivas tocando el mismo fichero salen como CONFLICTO: el candado es de "
  "sesión, no de ficheros, y fingir lo contrario sería peor que no tenerlo")
c(len(ch[0][1]) == 2, "y se dice qué dos sesiones son")
sesiones.latir(a["id"], raiz=raiz, tocados=["carrito.py"])
c([f for f, _ in sesiones.conflictos(raiz=raiz)] == ["prueba.py"],
  "los ficheros tocados se acumulan: haber dejado de tocarlo no borra que se tocó")

# ── limpieza de rancias ────────────────────────────────────────────────────
sesiones.soltar(b["id"], raiz=raiz)
f = raiz / f"{b['id']}.json"
d = json.loads(f.read_text(encoding="utf-8"))
d["latido"] = time.time() - sesiones.CADUCA - 10
f.write_text(json.dumps(d), encoding="utf-8")
c(sesiones.limpiar(raiz=raiz) == 1, "una sesión rancia y sin dueño se recoge")
c(f.exists() is False, "y desaparece del disco")
sesiones.tomar(a["id"], raiz=raiz)
c(sesiones.limpiar(raiz=raiz) == 0,
  "pero una sesión VIVA no se limpia aunque lleve tiempo: matarla sería peor que "
  "dejar un fichero de más")

# ── el servidor ────────────────────────────────────────────────────────────
os.environ["MG_SESIONES"] = str(raiz)
srv = servidor.servir(puerto=0, bloquear=False)
base = f"http://127.0.0.1:{srv.server_address[1]}"
k = servidor.clave()


def pide(ruta, cuerpo=None, clave=None):
    cab = {"Content-Type": "application/json"}
    if clave:
        cab["X-Genai-Clave"] = clave
    r = urllib.request.Request(
        base + ruta, json.dumps(cuerpo).encode() if cuerpo is not None else None, cab)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


c(pide("/salud")[0] == 200,
  "`/salud` responde SIN clave: sirve para saber si el servidor está ahí, y no "
  "revela nada")
c(pide("/sesiones")[0] == 401, "todo lo demás sin clave da 401")
c(pide("/sesiones", clave="clave-equivocada")[0] == 401, "y con clave mala, también")
c(pide("/sesiones", clave=k)[0] == 200, "con la clave buena, entra")

cod, s = pide("/sesiones", {"titulo": "desde el servidor"}, clave=k)
c(cod == 201 and s["titulo"] == "desde el servidor", "se crea una sesión por HTTP")
cod, det = pide(f"/sesiones/{s['id']}", clave=k)
c(cod == 200 and det["id"] == s["id"], "y se consulta una concreta")
c(pide("/sesiones/inventada", clave=k)[0] == 404, "una que no existe da 404, no 500")
cod, tr = pide(f"/sesiones/{s['id']}/transcripcion", clave=k)
c(cod == 200 and "aviso" in tr,
  "si aún no hay transcripción se dice, en vez de devolver una conversación vacía "
  "como si fuera la verdad")
c(pide("/conflictos", clave=k)[0] == 200, "los conflictos también se consultan por HTTP")
c(pide("/ruta/inventada", clave=k)[0] == 404, "una ruta que no existe da 404")

c(srv.server_address[0] == "127.0.0.1",
  "el servidor escucha SOLO en 127.0.0.1: en 0.0.0.0 estaría abriendo un agente con "
  "permiso de escritura a toda la red local")
fuente = (Path(__file__).resolve().parents[1] / "genai" / "servidor.py"
          ).read_text(encoding="utf-8")
c("compare_digest" in fuente,
  "la clave se compara en tiempo constante: con `==` el tiempo de respuesta filtra "
  "información, y aquí hacerlo bien no cuesta nada")
if servidor.FICHERO_CLAVE.is_file():
    import stat
    c(stat.S_IMODE(servidor.FICHERO_CLAVE.stat().st_mode) == 0o600,
      "y el fichero de la clave es 600: «solo local» no es «solo tuyo» en una máquina "
      "compartida")

srv.shutdown()
raise SystemExit(c.fin())
