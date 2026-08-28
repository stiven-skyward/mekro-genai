"""La extensión de editor, probada contra el servidor de verdad.

Una extensión de VS Code no se puede ejecutar fuera de VS Code, pero **casi todo lo que
puede fallar no necesita VS Code**: leer la clave del disco, hablar con el servidor,
entender sus respuestas y traducir sus fallos a algo accionable. Eso es lo que se prueba
aquí, cargando el mismo `extension.js` con `vscode` simulado y hablando con un servidor
Python real.

Lo que se vigila:

1. que el cliente **lea la clave del mismo sitio donde el servidor la escribe** — no de
   la configuración de VS Code, que se sincroniza entre máquinas;
2. que el fallo más común —**no hay servidor**— diga el comando exacto que lo arregla;
3. que la extensión **no reimplemente el arnés**: solo habla HTTP;
4. que la tarea se lance **en una terminal**, donde los frenos de permisos funcionan.
"""
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import threading
import time
from pathlib import Path

from _util import Cuenta

from genai import servidor, sesiones

c = Cuenta("editor")
RAIZ = Path(__file__).resolve().parents[1]
EXT = RAIZ / "editor" / "vscode"

# ── el manifiesto ──────────────────────────────────────────────────────────
man = json.loads((EXT / "package.json").read_text(encoding="utf-8"))
c(man["license"] == "Apache-2.0", "la extensión lleva la misma licencia que el proyecto")
ordenes = {x["command"] for x in man["contributes"]["commands"]}
c(ordenes == {"mekro.sesiones", "mekro.tarea", "mekro.transcripcion"},
  "tres órdenes: ver sesiones, ver una transcripción y encargar una tarea")
props = man["contributes"]["configuration"]["properties"]
c("mekro.puerto" in props and "mekro.cerebro" in props and "mekro.modo" in props,
  "y se configura puerto, cerebro y modo de permisos")
c(props["mekro.modo"]["default"] == "preguntar",
  "el modo por defecto es `preguntar`: dentro de un editor, donde es más fácil dar a "
  "todo que sí, el defecto tiene que ser el que para antes de cada acción peligrosa")

fuente = (EXT / "extension.js").read_text(encoding="utf-8")
c("servidor.clave" in fuente,
  "la clave se lee del fichero que escribe el servidor, no de la configuración de "
  "VS Code — que se sincroniza entre máquinas y llevaría la credencial con ella")
c("createTerminal" in fuente,
  "la tarea se lanza en una TERMINAL: el modo `preguntar` para antes de cada acción "
  "peligrosa y ese diálogo vive ahí")
c("127.0.0.1" in fuente and "http.request" in fuente,
  "y solo habla HTTP contra la máquina local: la extensión no reimplementa el arnés")
c("require(\"child_process\")" not in fuente and "spawn(" not in fuente,
  "no ejecuta nada por su cuenta: lo que corra, corre por la terminal a la vista")

# ── contra el servidor de verdad ───────────────────────────────────────────
if not shutil.which("node"):
    c(True, "(node no está instalado: la mitad de cliente no se pudo probar)")
    raise SystemExit(c.fin())

tmp = Path(tempfile.mkdtemp(prefix="editor-"))
os.environ["MG_SESIONES"] = str(tmp / "s")
sesiones.crear("refactor del carrito")
sesiones.crear("subir cobertura")
srv = servidor.servir(puerto=0, bloquear=False)
puerto = srv.server_address[1]

guion = textwrap.dedent(f"""
    const Module = require("module");
    const orig = Module._load;
    // VS Code no existe fuera del editor: se simula lo justo para cargar el módulo.
    Module._load = function (p, ...r) {{
      if (p === "vscode") return {{
        workspace: {{ getConfiguration: () => ({{ get: (k, d) => (k === "puerto" ? PUERTO : d) }}) }},
        window: {{}}, commands: {{}},
      }};
      return orig.apply(this, [p, ...r]);
    }};
    const ext = require({str(EXT / 'extension.js')!r});
    (async () => {{
      const fuera = {{ clave: !!ext.clave() }};
      try {{
        const s = await ext.pedir("/sesiones");
        fuera.sesiones = s.sesiones.length;
        fuera.titulos = s.sesiones.map(x => x.titulo).sort();
        const tr = await ext.pedir(`/sesiones/${{s.sesiones[0].id}}/transcripcion`);
        fuera.aviso = tr.aviso || "";
      }} catch (e) {{ fuera.error = e.message; }}
      try {{ await ext.pedir("/sesiones/inventada"); }}
      catch (e) {{ fuera.no_existe = e.message; }}
      console.log(JSON.stringify(fuera));
    }})();
""").replace("PUERTO", str(puerto))

f = tmp / "cliente.js"
f.write_text(guion, encoding="utf-8")
r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
d = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}

c(d.get("clave") is True,
  f"el cliente encuentra la clave en el disco (dijo: {r.stderr[:120]})")
c(d.get("sesiones") == 2, "y ve las dos sesiones del proyecto por HTTP")
c(d.get("titulos") == ["refactor del carrito", "subir cobertura"],
  "con sus títulos, que es lo que el usuario reconoce")
c("aún no ha guardado" in (d.get("aviso") or ""),
  "una sesión sin transcripción lo DICE: devolver una conversación vacía como si fuera "
  "la verdad sería peor que no devolver nada")
c("no existe" in (d.get("no_existe") or ""),
  "y un id inventado da un error legible, no un volcado")

srv.shutdown()

# ── el fallo más común: no hay servidor ────────────────────────────────────
f.write_text(guion.replace(f"? {puerto} :", "? 9 :"), encoding="utf-8")
r2 = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
d2 = json.loads(r2.stdout.strip().splitlines()[-1]) if r2.stdout.strip() else {}
c("genai sesiones servir" in (d2.get("error", "") + d2.get("no_existe", "")),
  "sin servidor, el mensaje trae el COMANDO EXACTO que lo arregla: es el fallo que "
  "va a ver todo el mundo la primera vez, y «ECONNREFUSED» no le dice nada a nadie")

raise SystemExit(c.fin())
