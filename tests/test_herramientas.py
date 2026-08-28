"""Las herramientas: lo que hacen y —sobre todo— cómo fallan.

Se prueba con especial saña el fallo, porque el fallo de una herramienta es lo que el
modelo lee para corregirse. Un mensaje de error inútil cuesta vueltas caras."""
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.herramientas import estandar
from genai.herramientas.base import MAX_SALIDA, Resultado
from genai.herramientas.ficheros import editar, escribir, leer

c = Cuenta("herramientas")
tmp = Path(tempfile.mkdtemp())

# ── leer ────────────────────────────────────────────────────────────────────
f = tmp / "a.py"
f.write_text("uno\ndos\ntres\ncuatro\n", encoding="utf-8")
r = leer(str(f))
c(r.ok, "leer un fichero existente")
c("    2 │ dos" in r.salida, "leer numera las líneas")
c(not leer(str(tmp / "no-existe")).ok, "leer un fichero inexistente devuelve ok=False")
c("directorio" in leer(str(tmp)).salida, "leer un directorio lo lista")
r = leer(str(f), desde=2, lineas=1)
c("dos" in r.salida and "tres" not in r.salida, "leer respeta desde/lineas")

# ── editar: atómico ─────────────────────────────────────────────────────────
r = editar(str(f), [{"buscar": "uno", "poner": "UNO"}, {"buscar": "dos", "poner": "DOS"}])
c(r.ok, "editar aplica varios cambios")
c.igual(f.read_text(), "UNO\nDOS\ntres\ncuatro\n", "editar aplicó ambos")

antes = f.read_text()
r = editar(str(f), [{"buscar": "tres", "poner": "TRES"},
                    {"buscar": "no aparece", "poner": "x"}])
c(not r.ok, "editar rechaza si un cambio no casa")
c.igual(f.read_text(), antes, "ATÓMICO: ni el cambio válido entró")
c("NO se aplicó ningún cambio" in r.salida, "el error lo dice explícitamente")

f.write_text("hola\nhola\n", encoding="utf-8")
r = editar(str(f), [{"buscar": "hola", "poner": "adios"}])
c(not r.ok and "2 veces" in r.salida, "editar rechaza texto ambiguo y dice cuántas veces")

# ── escribir ────────────────────────────────────────────────────────────────
r = escribir(str(tmp / "sub" / "b.txt"), "contenido\n")
c(r.ok and (tmp / "sub" / "b.txt").exists(), "escribir crea directorios intermedios")

# ── recorte de salida ───────────────────────────────────────────────────────
gordo = Resultado(True, "x" * (MAX_SALIDA * 3))
c(len(gordo.recortado()) < MAX_SALIDA + 400, "una salida enorme se recorta")
c("omitidos" in gordo.recortado(), "el recorte se declara, no se disimula")

# ── registro ────────────────────────────────────────────────────────────────
reg = estandar()
# el CONJUNTO y no el número: un conteo se rompe con cada herramienta nueva y no
# dice cuál cambió; el conjunto documenta el juego y falla señalando el culpable
# `estandar()` trae web desde 2026-08-28; el juego SIN red es el que se fija aquí,
# porque es el que usan el banco y el modo plan.
reg = estandar(web=False)
c({h["function"]["name"] for h in reg.firmas()} ==
  {"leer", "escribir", "editar", "grep", "simbolos", "bash",
   "fondo_lanzar", "fondo_revisar", "subagente", "git", "ver",
   "definicion", "referencias", "diagnostico"},
  "el juego estándar es exactamente este")
c("bash" not in estandar(incluir_peligrosas=False), "sin peligrosas no hay bash")
c("fondo_lanzar" not in estandar(incluir_peligrosas=False),
  "sin peligrosas tampoco hay fondo_lanzar: ejecuta shell igual que bash")
c(all("function" in fi and "name" in fi["function"] for fi in reg.firmas()),
  "las firmas van en formato Hermes/OpenAI")
r = reg.invocar("no_existe", {})
c(not r.ok and "no existe la herramienta" in r.salida, "invocar algo inexistente no revienta")
r = reg.invocar("leer", {"parametro_inventado": 1})
c(not r.ok and "argumentos inválidos" in r.salida,
  "argumentos que no casan devuelven un error accionable, no una excepción")

raise SystemExit(c.fin())
