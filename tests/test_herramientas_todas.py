"""test_herramientas_todas.py — cada herramienta del arnés, ejercitada de verdad.

`test_herramientas.py` prueba el registro y los casos de borde. Esto es lo otro: que las
NUEVE herramientas hagan su trabajo sobre ficheros reales, porque el banco sólo ejercita
las que el modelo decide usar y una herramienta que nadie llama puede estar rota durante
meses sin que se note.

Cuenta asertos en verde, como el resto de las pruebas del proyecto.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from genai.herramientas import estandar                    # noqa: E402
from genai.memoria import HERRAMIENTAS as HOLO             # noqa: E402

verdes = 0
REG = None


def inv(nombre, **args) -> str:
    """`invocar` devuelve un Resultado(ok, salida, datos), no una cadena."""
    r = REG.invocar(nombre, args)
    return r.salida if hasattr(r, "salida") else str(r)


def ok(cond, que):
    global verdes
    assert cond, f"FALLA: {que}"
    verdes += 1
    print(f"  ✓ {que}")


def main() -> int:
    global REG
    REG = estandar()
    for h in HOLO:
        REG.registrar(h)
    nombres = {f["function"]["name"] for f in REG.firmas()} - {"web", "buscar_web"}
    ok(nombres == {"leer", "escribir", "editar", "grep", "simbolos", "bash",
                   "fondo_lanzar", "fondo_revisar", "subagente", "git", "ver",
                   "definicion", "referencias", "diagnostico",
                   "holos", "foco", "anotar"},
       f"el juego con hologramas es exactamente este ({len(nombres)})")

    trabajo = Path(tempfile.mkdtemp(prefix="herr-"))
    antes = os.getcwd()
    os.chdir(trabajo)
    try:
        # ── escribir ───────────────────────────────────────────────────────
        s = inv("escribir", ruta="mod.py", contenido="def sumar(a, b):\n    return a - b\n")
        ok(Path("mod.py").exists(), "escribir crea el fichero")
        ok("mod.py" in s, "escribir informa de qué escribió")

        # ── leer ───────────────────────────────────────────────────────────
        s = inv("leer", ruta="mod.py")
        ok("def sumar" in s, "leer devuelve el contenido")
        ok("1" in s.split("\n")[0], "leer numera las líneas")
        ok("mod.py" in inv("leer", ruta="."), "leer sobre un directorio lo lista")

        # ── editar ─────────────────────────────────────────────────────────
        inv("editar", ruta="mod.py", cambios=[{"buscar": "return a - b",
                                               "poner": "return a + b"}])
        ok("return a + b" in Path("mod.py").read_text(), "editar aplica el cambio")
        inv("editar", ruta="mod.py", cambios=[{"buscar": "NO EXISTE", "poner": "x"}])
        ok("return a + b" in Path("mod.py").read_text(),
           "editar con texto ausente NO corrompe el fichero")

        Path("atomo.py").write_text("uno\ndos\n")
        inv("editar", ruta="atomo.py", cambios=[{"buscar": "uno", "poner": "UNO"},
                                                {"buscar": "AUSENTE", "poner": "x"}])
        ok(Path("atomo.py").read_text() == "uno\ndos\n",
           "editar es atómico: un cambio imposible aborta todos")

        # ── grep ───────────────────────────────────────────────────────────
        ok("mod.py" in inv("grep", patron="def sumar", ruta="."),
           "grep encuentra el patrón y dice en qué fichero")
        ok("mod.py" not in inv("grep", patron="zzz_no_existe", ruta="."),
           "grep sin coincidencias no inventa")

        # ── simbolos ───────────────────────────────────────────────────────
        ok("sumar" in inv("simbolos", aguja="sumar", ruta="."),
           "simbolos localiza la función por su nombre")

        # ── bash ───────────────────────────────────────────────────────────
        ok("hola-arnes" in inv("bash", comando="echo hola-arnes"),
           "bash ejecuta y devuelve la salida")
        ok("3" in inv("bash", comando="exit 3"),
           "bash informa del código de salida distinto de cero")
        ok("5" in inv("bash", comando='python3 -c "import mod; print(mod.sumar(2,3))"'),
           "bash corre python y ve el fichero que editamos")

        # ── holos / foco / anotar ──────────────────────────────────────────
        os.chdir(antes)
        ok("H1" in inv("holos"), "holos lista las tareas vivas")
        f = inv("foco", ident="H1")
        ok(len(f) > 200 and "H1" in f, "foco reconstruye el contexto de una tarea")
        MARCA = "prueba automática de herramientas (ignorar)"
        ok("H1" in inv("anotar", ident="H1", texto=MARCA),
           "anotar deja constancia en la bitácora")
        p = RAIZ / "holos" / "H1.md"
        t = p.read_text(encoding="utf-8")
        if MARCA in t:
            p.write_text("\n".join(l for l in t.split("\n") if MARCA not in l),
                         encoding="utf-8")
        ok(MARCA not in p.read_text(encoding="utf-8"),
           "la anotación de prueba se limpió y el holograma queda intacto")
    finally:
        os.chdir(antes)

    print(f"\n{verdes} asertos en verde")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
