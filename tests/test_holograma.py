"""El holograma: reconstruir contexto y —lo importante— detectar cuándo miente."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _util import Cuenta

c = Cuenta("holograma")
RAIZ = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp())
(tmp / "holos").mkdir()
entorno = {**os.environ, "MG_HOLOS": str(tmp / "holos")}


def holo(*args):
    return subprocess.run([sys.executable, "holograma.py", *args], cwd=RAIZ,
                          capture_output=True, text=True, env=entorno)


import holograma  # noqa: E402

# ── extracción por AST, no por subcadena ────────────────────────────────────
fuente = """
def leer_ventana():
    return 1

def leer():
    '''el corto'''
    return 2

class Cosa:
    def leer(self):
        return 3
"""
c.igual(holograma._extraer_simbolo(fuente, "leer"), (5, 7),
        "«leer» resuelve a la función leer, no a leer_ventana")
c.igual(holograma._extraer_simbolo(fuente, "Cosa.leer"), (10, 11),
        "Clase.metodo desambigua métodos con nombre repetido")
c.igual(holograma._extraer_simbolo(fuente, "no_existe"), None,
        "un símbolo inexistente devuelve None en vez de casar por accidente")

# ── iluminar y detectar anclas podridas ─────────────────────────────────────
trozo = holograma.iluminar("genai/cerebro/base.py:Uso")
c("class Uso" in trozo and "tokens_por_segundo" in trozo, "iluminar trae el símbolo entero")
c(holograma.iluminar("genai/cerebro/base.py:SimboloQueNoExiste").startswith("⚠"),
  "un ancla a un símbolo que ya no existe se declara ROTA")
c(holograma.iluminar("fichero/que/no/existe.py:X").startswith("⚠"),
  "un ancla a un fichero que no existe se declara ROTA")
c("│" in holograma.iluminar("genai/cerebro/base.py:1-10"), "los rangos también valen")

# ── el ciclo de vida por CLI ────────────────────────────────────────────────
c(holo("nuevo", "T1", "prueba").returncode == 0, "se crea un holograma")
c(holo("nuevo", "T1", "otra vez").returncode != 0, "no se pisa uno existente")
c("T1" in holo("listar").stdout, "listar lo enseña")

t1 = tmp / "holos" / "T1.md"
t1.write_text(t1.read_text().replace("# el comando que decide si esto esta arreglado",
                                     "true"), encoding="utf-8")
c(holo("cerrar", "T1").returncode == 0, "cerrar con comprobación que pasa → 0")
c("estado: cerrado" in t1.read_text(), "y el estado queda cerrado")

t1.write_text(t1.read_text().replace("estado: cerrado", "estado: abierto")
              .replace("\ntrue", "\nfalse"), encoding="utf-8")
c(holo("cerrar", "T1").returncode != 0, "cerrar con comprobación que falla → no 0")
c("estado: abierto" in t1.read_text(),
  "un cierre fallido NO cierra: el holograma se cierra ejecutando, no declarando")

c(holo("retirar", "T1", "cambió el plan").returncode == 0, "se puede retirar")
txt = t1.read_text()
c("estado: retirado" in txt and "≠ cerrado" in txt,
  "retirado se distingue de cerrado en el propio fichero")

c(holo("anotar", "T1", "una nota").returncode == 0, "se anota en la bitácora")
c("una nota" in t1.read_text(), "y la nota queda")

raise SystemExit(c.fin())
