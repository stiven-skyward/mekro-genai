"""Subagentes de exploración (M7.1): contexto aislado, solo lectura, sin recursión.

Lo que se vigila no es que exploren bien —eso lo mide un ciclo con cerebro real— sino
los tres guardarraíles: que NO puedan escribir, que NO puedan lanzar subagentes, y que
lo que leen se quede fuera del contexto de quien pregunta."""
import os
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.herramientas import estandar
from genai.herramientas.base import Registro
from genai.herramientas.subagente import TOPES, explorar

c = Cuenta("subagente")

# ── el registro que ve un subagente: lectura y nada más ─────────────────────
base = estandar(incluir_peligrosas=False, plugins=False)
suyo = Registro([base[n] for n in sorted(base._por_nombre) if n != "subagente"])
nombres = {h["function"]["name"] for h in suyo.firmas()}
c("subagente" not in nombres,
  "un subagente NO puede lanzar subagentes: la recursión no tiene fondo")
c(not (nombres & {"escribir", "editar", "bash", "fondo_lanzar", "malla_delegar"}),
  "un subagente no escribe, no ejecuta y no delega: solo lee")
c({"leer", "grep"} <= nombres, "pero sí tiene con qué explorar")

# ── la herramienta está en el juego estándar y no es peligrosa ──────────────
c("subagente" in estandar(), "el agente principal sí puede lanzarlos")
c(not estandar()["subagente"].peligrosa,
  "explorar no es peligroso: no toca nada (lo peligroso sería que escribiera)")

# ── presupuesto propio y acotado ────────────────────────────────────────────
c(TOPES["tope_vueltas"] <= 8 and TOPES["tope_tokens"] <= 2500,
  "el subagente tiene presupuesto PROPIO y pequeño, no el del padre")

# ── entradas degeneradas: se rechazan sin romper ────────────────────────────
r = explorar([])
c(not r.ok and "nada que explorar" in r.salida, "sin encargos, lo dice y no revienta")
r = explorar(["  "])
c(not r.ok, "un encargo vacío tampoco cuela")

# ── el aislamiento, con el cerebro «eco» (sin red, sin modelo) ──────────────
tmp = Path(tempfile.mkdtemp(prefix="subag-"))
(tmp / "grande.py").write_text("# relleno\n" * 4000, encoding="utf-8")
antes = os.getcwd()
os.chdir(tmp)
os.environ["MG_CEREBRO"] = "eco"
r = explorar(["¿qué hay en grande.py?", "¿y en el directorio?"])
os.chdir(antes)
c(r.ok, "dos subagentes con cerebro eco terminan")
c("2 subagente(s)" in r.salida and "en serie" in r.salida,
  "con cerebro local van en SERIE y la cabecera no miente sobre ello")
c(len(r.salida) < 2000,
  "lo que vuelve al contexto principal es la conclusión, no lo que leyeron")
c("tokens SUYOS" in r.salida,
  "la cabecera declara el gasto propio de los subagentes, que no es del padre")

# ── el tope de cordura ──────────────────────────────────────────────────────
os.chdir(tmp)
r = explorar([f"pregunta {i}" for i in range(12)])
os.chdir(antes)
c("6 subagente(s)" in r.salida, "más de seis encargos se recortan a seis")

# ── modo híbrido (M7.1b): un cerebro por rol, con caída al principal ────────
from genai.cerebro import ROLES, cargar_rol, para_rol   # noqa: E402

os.environ["MG_CEREBRO"] = "gguf"
for r in ROLES:
    os.environ.pop(f"MG_CEREBRO_{r.upper()}", None)
os.environ["MG_CEREBROS"] = str(tmp / "cerebros-no-existe.json")
c(para_rol("subagente") == "gguf",
  "sin reparto, cada rol usa el cerebro principal: el defecto no cambia")

os.environ["MG_CEREBRO_SUBAGENTE"] = "nube:gemini"
c(para_rol("subagente") == "nube:gemini" and para_rol("principal") == "gguf",
  "con reparto, el subagente va a la nube y el principal sigue siendo el local")

(tmp / "cerebros.json").write_text('{"resumidor": "nube:deepseek"}', encoding="utf-8")
os.environ["MG_CEREBROS"] = str(tmp / "cerebros.json")
c(para_rol("resumidor") == "nube:deepseek",
  "el reparto también se configura por fichero, no solo por entorno")
os.environ["MG_CEREBRO_RESUMIDOR"] = "eco"
c(para_rol("resumidor") == "eco",
  "y el entorno gana al fichero: una carrera puede fijar el reparto sin tocar nada")

# la nube NUNCA es carga crítica
os.environ["MG_CEREBRO_SUBAGENTE"] = "nube:proveedor-inexistente"
cerebro, usado = cargar_rol("subagente", "eco")
c(usado == "eco",
  "si el cerebro del rol no está disponible, cae al principal en vez de romper")
c(cerebro is not None, "y devuelve un cerebro utilizable: la tarea continúa")

try:
    para_rol("inventado")
    rol_malo = False
except ValueError:
    rol_malo = True
c(rol_malo, "un rol que no existe se rechaza en vez de resolverse a cualquier cosa")

# la contabilidad auxiliar existe y es aparte
from genai.herramientas.subagente import GASTO_AUXILIAR   # noqa: E402
c(set(GASTO_AUXILIAR) >= {"vueltas", "tokens", "segundos", "cerebros"},
  "el gasto de los roles auxiliares se acumula APARTE del de la carrera")

for r in ROLES:
    os.environ.pop(f"MG_CEREBRO_{r.upper()}", None)
os.environ.pop("MG_CEREBROS", None)

raise SystemExit(c.fin())
