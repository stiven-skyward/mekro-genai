"""Verificador del renombrado. Comprueba las DOS mitades del trabajo."""
import ast
import sys
from pathlib import Path

fallos = []


def comprueba(que, cond):
    print(("✓ " if cond else "✗ ") + que)
    if not cond:
        fallos.append(que)


def defs(fichero):
    """Nombres definidos con `def`, y a qué nivel."""
    arbol = ast.parse(Path(fichero).read_text(encoding="utf-8"))
    modulo, metodos = set(), set()
    for n in arbol.body:
        if isinstance(n, ast.FunctionDef):
            modulo.add(n.name)
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef):
                    metodos.add(f"{n.name}.{m.name}")
    return modulo, metodos


# ── mitad 1: la función del núcleo SÍ se renombró ──────────────────────────
mod, _ = defs("nucleo.py")
comprueba("nucleo define transformar", "transformar" in mod)
comprueba("nucleo ya no define procesar", "procesar" not in mod)

# ── mitad 2: los homónimos NO se tocaron ───────────────────────────────────
_, met = defs("cola.py")
comprueba("Cola.procesar sigue llamándose procesar", "Cola.procesar" in met)
_, met = defs("registro.py")
comprueba("Auditor.procesar sigue llamándose procesar", "Auditor.procesar" in met)

# ── y todo sigue funcionando ───────────────────────────────────────────────
sys.path.insert(0, ".")
try:
    import informes
    import lotes
    import nucleo
    import registro
    datos = [1.005, None, 2.0, 3.14159]
    comprueba("nucleo.transformar limpia y redondea",
              nucleo.transformar(datos) == [1.0, 2.0, 3.14])
    comprueba("resumir sigue bien", nucleo.resumir(datos) == {"n": 3, "suma": 6.14})
    comprueba("informes usa el nombre nuevo", informes.informe_corto(datos) == "3 valores")
    comprueba("informe_largo sigue bien",
              informes.informe_largo(datos) == "3 valores, suman 6.14")
    comprueba("lotes usa el nombre nuevo",
              lotes.por_lotes([[1.0, None], [2.5]]) == [[1.0], [2.5]])
    a = registro.Auditor()
    a.cola.mensajes = ["x", "y"]
    comprueba("el Auditor sigue procesando su cola", a.procesar() == 2)
except Exception as e:
    comprueba(f"todo importa y corre (salió {type(e).__name__}: {e})", False)

if fallos:
    raise SystemExit(f"FALLAN {len(fallos)} de 10")
print("10/10 asertos ✓")
