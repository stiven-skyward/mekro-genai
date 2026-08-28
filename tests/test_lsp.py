"""Cliente LSP y las tres herramientas que lo exponen.

Se prueba en dos capas, y la primera es la que importa para que esto sea portable:

1. **El PROTOCOLO, contra un servidor de mentira** que habla LSP y nada más. Así la
   suite no exige que haya un servidor de lenguaje instalado, y verifica lo único que
   es responsabilidad de este proyecto: el enmarcado `Content-Length`, la
   correspondencia de `id`, que las notificaciones intercaladas no se confundan con la
   respuesta, y que un servidor que se cuelga no cuelgue al agente.
2. **Con un servidor REAL**, si lo hay, para la única pregunta que un mock no puede
   contestar: si de verdad distingue una función de un método homónimo. Si no hay
   servidor, se dice y se sigue — que es exactamente lo que debe hacer la herramienta.
"""
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from _util import Cuenta

from genai import lsp
from genai.herramientas import estandar
from genai.herramientas.codigo import _pos, _relativa, _ruta, definicion, referencias

c = Cuenta("lsp")
RAIZ = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp(prefix="lsp-"))

# ── las herramientas están, y son de solo lectura ──────────────────────────
reg = estandar()
c({"definicion", "referencias", "diagnostico"} <= set(reg._por_nombre),
  "las tres herramientas de código están en el juego estándar")
c(not any(reg[n].peligrosa for n in ("definicion", "referencias", "diagnostico")),
  "y ninguna es peligrosa: solo leen. Renombrar en veinte ficheros lo hace el agente "
  "con `editar`, que pasa por permisos y deja diff; un workspace/applyEdit silencioso "
  "no")

# ── sin servidor instalado se DICE cuál falta ──────────────────────────────
# Es la respuesta que evita la peor avería: devolver «0 referencias» cuando lo cierto
# es «no hay quien busque» hace que el modelo concluya que el símbolo no se usa.
(tmp / "x.desconocido").write_text("nada", encoding="utf-8")
srv, queja = lsp.para(tmp / "x.desconocido")
c(srv is None and "no sé qué servidor" in queja,
  "una extensión desconocida se dice, no se intenta a ciegas")

_orig_which = shutil.which
shutil.which = lambda x: None
(tmp / "y.py").write_text("x = 1\n", encoding="utf-8")
srv, queja = lsp.para(tmp / "y.py")
shutil.which = _orig_which
c(srv is None and "pip install" in queja,
  "sin ningún servidor instalado, la queja trae el comando EXACTO para instalarlo")
c("sería mentir" in queja,
  "y explica por qué no se responde «no encontré nada»: sería mentir")

r = referencias(str(tmp / "no-existe.py"), "x")
c(not r.ok and "no existe" in r.salida, "un fichero que no está se dice sin reventar")

# ── el protocolo, contra un servidor de mentira ────────────────────────────
FALSO = tmp / "servidor_falso.py"
FALSO.write_text(textwrap.dedent('''
    """Habla LSP y nada más: enmarca, responde por id, y mete ruido en medio."""
    import json, sys

    def leer():
        cab = b""
        while not cab.endswith(b"\\r\\n\\r\\n"):
            b = sys.stdin.buffer.read(1)
            if not b:
                return None
            cab += b
        largo = 0
        for l in cab.decode().split("\\r\\n"):
            if l.lower().startswith("content-length:"):
                largo = int(l.split(":", 1)[1])
        return json.loads(sys.stdin.buffer.read(largo))

    def enviar(m):
        b = json.dumps(m).encode()
        sys.stdout.buffer.write(b"Content-Length: %d\\r\\n\\r\\n" % len(b) + b)
        sys.stdout.buffer.flush()

    while True:
        m = leer()
        if m is None:
            break
        met, ident = m.get("method"), m.get("id")
        if met == "initialize":
            enviar({"jsonrpc": "2.0", "id": ident, "capabilities": {}})
        elif met == "textDocument/references":
            # ruido ANTES de la respuesta: si el cliente lo confunde, falla
            enviar({"jsonrpc": "2.0", "method": "window/logMessage",
                    "params": {"type": 3, "message": "indexando"}})
            enviar({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
                    "params": {"uri": "file:///otro", "diagnostics": []}})
            uri = m["params"]["textDocument"]["uri"]
            enviar({"jsonrpc": "2.0", "id": ident, "result": [
                {"uri": uri, "range": {"start": {"line": 0, "character": 0}}},
                {"uri": uri, "range": {"start": {"line": 4, "character": 2}}},
                {"uri": "file:///zzz/otro.py",
                 "range": {"start": {"line": 9, "character": 0}}}]})
        elif met == "textDocument/definition":
            enviar({"jsonrpc": "2.0", "id": ident, "result": None})
        elif met == "mudo":
            pass                       # a propósito: no contesta nunca
        elif ident is not None:
            enviar({"jsonrpc": "2.0", "id": ident, "result": None})
''').strip(), encoding="utf-8")

proyecto = tmp / "proy"
proyecto.mkdir()
(proyecto / "pyproject.toml").touch()
(proyecto / "mod.py").write_text("def pagar(x):\n    return x\n\n\nclass C:\n"
                                 "    def pagar(self):\n        pass\n", encoding="utf-8")
lsp.SERVIDORES[".falso"] = [("falso", [sys.executable, str(FALSO)], "no hace falta")]
(proyecto / "a.falso").write_text("def pagar(x):\n    return x\n\n\ndef otra():\n"
                                  "    return pagar(1)\n", encoding="utf-8")

srv, queja = lsp.para(proyecto / "a.falso")
c(srv is not None, f"el servidor de mentira arranca y responde a initialize ({queja})")

r = referencias(str(proyecto / "a.falso"), "pagar", linea=1)
c(r.ok and "3 referencias en 2 ficheros" in r.salida,
  "la respuesta llega ENTERA aunque el servidor meta notificaciones por delante: "
  "el cliente empareja por `id`, no por orden de llegada")
c("a.falso  (líneas 1, 5)" in r.salida,
  "y las líneas se agrupan por fichero —repetir la ruta 40 veces para decir 3 cosas "
  "se paga en todas las vueltas que queden (docs/ahorro.md)")
c(r.datos["total"] == 3, "el arnés se queda con la cuenta exacta en `datos`")

r = definicion(str(proyecto / "a.falso"), "pagar", linea=1)
c(not r.ok and "no sabe dónde" in r.salida,
  "un `result: null` es «no lo sé», y se traduce a eso en vez de a una lista vacía")

# el servidor se REUTILIZA: arrancarlo cuesta segundos, pagarlo por llamada sería
# inservible con un cerebro que ya tarda 530 s por vuelta
antes = srv
t0 = time.time()
referencias(str(proyecto / "a.falso"), "pagar", linea=1)
c(lsp.para(proyecto / "a.falso")[0] is antes,
  "el servidor se reutiliza entre llamadas, no se arranca uno por pregunta")
c(time.time() - t0 < 2.0, "y por eso la segunda llamada es inmediata")

# un servidor que no contesta no cuelga al agente
t0 = time.time()
mudo = srv._pedir("mudo", {}, espera=1.0)
c(mudo is None and time.time() - t0 < 3.0,
  "un servidor que se queda mudo devuelve None y suelta: no cuelga la carrera")

lsp.cerrar_todos()
c(all(s.proc.poll() is not None for s in [antes]),
  "cerrar_todos mata los procesos: un servidor huérfano se come la RAM que el "
  "cerebro necesita")

# ── piezas sueltas ─────────────────────────────────────────────────────────
c(_ruta("file:///tmp/con%20espacio.py") == "/tmp/con espacio.py",
  "un URI con escapes se convierte en ruta de verdad")
c(_relativa("/a/b/c.py", Path("/a")) == "b/c.py", "las rutas vuelven relativas")
c(_relativa("/otro/sitio.py", Path("/a")) == "/otro/sitio.py",
  "y lo que cae fuera del proyecto se deja absoluto en vez de inventar «../..»")
c(_pos(proyecto / "mod.py", "pagar") == (0, 4),
  "el símbolo se busca por nombre: el agente sabe nombres, LSP quiere coordenadas")
c(_pos(proyecto / "mod.py", "pagar", linea=6) == (5, 8),
  "y `linea` desambigua cuando el nombre aparece dos veces — que es justo el caso "
  "que separa una función de un método homónimo")
c(isinstance(_pos(proyecto / "mod.py", "no_existe"), str),
  "un símbolo que no aparece devuelve el motivo, no una posición inventada")

# ── con un servidor REAL, si lo hay ────────────────────────────────────────
real = next((o[0] for o in lsp.SERVIDORES[".py"] if shutil.which(o[1][0])), None)
if real:
    (proyecto / "otro.py").write_text("from mod import pagar\n\n\ndef t():\n"
                                      "    return pagar(9)\n", encoding="utf-8")
    r = referencias(str(proyecto / "mod.py"), "pagar", linea=1)
    salida = r.salida
    c(r.ok, f"con «{real}» real, las referencias vuelven")
    c("otro.py" in salida,
      "cruza ficheros: encuentra el uso en otro módulo, que es para lo que sirve")
    metodo = referencias(str(proyecto / "mod.py"), "pagar", linea=6)
    c(metodo.ok and metodo.datos["total"] < r.datos["total"],
      "y DISTINGUE: el método homónimo de la línea 6 tiene menos referencias que la "
      "función del módulo. `grep pagar` daría el mismo número para los dos, y esa "
      "confusión es la que rompe un renombrado")
    lsp.cerrar_todos()
else:
    c(True, "(no hay servidor de lenguaje real instalado: esa mitad no se pudo probar)")

raise SystemExit(c.fin())
