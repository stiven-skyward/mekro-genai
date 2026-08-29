"""tui.py — la estética se apaga sola sin terminal, y lo que pinta es lo que dice pintar.

Lo que importa verificar no es «se ve bonito» (eso no se automatiza) sino los dos
contratos de los que depende todo lo demás: (1) sin TTY y sin forzar, cero códigos ANSI
—si esto fallara, cualquier log o pipe de `genai tarea` saldría con basura de escape—, y
(2) MG_COLOR fuerza el comportamiento en cualquier sentido, que es como esta prueba
puede ejercitar el camino con color sin depender de tener una terminal de verdad.
"""
import os

from _util import Cuenta

from genai import tui

c = Cuenta("tui")

# ── activo(): el contrato de cuándo pintar ──────────────────────────────────
_viejo_no_color = os.environ.pop("NO_COLOR", None)
_viejo_term = os.environ.pop("TERM", None)
_viejo_mg = os.environ.pop("MG_COLOR", None)
try:
    os.environ["MG_COLOR"] = "0"
    c(not tui.activo(), "MG_COLOR=0 apaga el color pase lo que pase")
    c(tui.negrita("x") == "x", "y negrita() no añade ningún código ANSI")
    c(tui.exito("x") == "x", "ni exito()")

    os.environ["MG_COLOR"] = "1"
    c(tui.activo(), "MG_COLOR=1 lo enciende pase lo que pase")
    c(tui.negrita("x") != "x", "y ahora negrita() SÍ envuelve el texto")
    c(tui.negrita("x").endswith("\033[0m"), "todo código ANSI cierra con el reinicio")

    del os.environ["MG_COLOR"]
    os.environ["TERM"] = "dumb"
    c(not tui.activo(), "TERM=dumb apaga el color aunque no haya NO_COLOR")

    del os.environ["TERM"]
    os.environ["NO_COLOR"] = "1"
    c(not tui.activo(), "NO_COLOR apaga el color (convención estándar)")
finally:
    os.environ.pop("MG_COLOR", None)
    os.environ.pop("TERM", None)
    os.environ.pop("NO_COLOR", None)
    if _viejo_no_color is not None:
        os.environ["NO_COLOR"] = _viejo_no_color
    if _viejo_term is not None:
        os.environ["TERM"] = _viejo_term
    if _viejo_mg is not None:
        os.environ["MG_COLOR"] = _viejo_mg

# ── ancho_visible(): un código ANSI no cuenta como caracteres en pantalla ───
os.environ["MG_COLOR"] = "1"
coloreado = tui.exito("abc")
c(len(coloreado) > 3, "coloreado sí lleva bytes ANSI de más")
c(tui.ancho_visible(coloreado) == 3, "pero ancho_visible() los descuenta")

# ── caja(): el recuadro se cierra y respeta el contenido más ancho ──────────
recuadro = tui.caja(["corta", "una línea bastante más larga que la anterior"])
lineas = recuadro.split("\n")
c(lineas[0].startswith("╭") and lineas[0].endswith("╮"), "la caja abre con esquinas")
c(lineas[-1].startswith("╰") and lineas[-1].endswith("╯"), "y cierra con esquinas")
anchos = {tui.ancho_visible(l) for l in lineas}
c(len(anchos) == 1, "todas las filas de la caja miden lo mismo visiblemente")

con_titulo = tui.caja(["x"], titulo="permiso")
c("permiso" in con_titulo, "el título va incrustado en el borde superior")

# ── diff(): unified diff, sin las cabeceras ---/+++/@@ ──────────────────────
os.environ["MG_COLOR"] = "0"
d = tui.diff("uno\ndos\ntres", "uno\nDOS\ntres")
c("- dos" in d, "la línea quitada aparece con -")
c("+ DOS" in d, "la línea puesta aparece con +")
c("---" not in d and "+++" not in d, "sin las cabeceras crudas de unified_diff")
c(tui.diff("x", "x") == "    (sin cambios de texto)",
  "diff() de un texto contra sí mismo lo dice, no enseña un diff vacío")

muchas_antes = "\n".join(f"l{i}" for i in range(100))
muchas_despues = "\n".join(f"L{i}" for i in range(100))
recortado = tui.diff(muchas_antes, muchas_despues, tope=10)
c("omitidas" in recortado, "un diff largo se recorta y LO DICE, no se trunca en silencio")

# ── markdown_ligero(): solo actúa si activo() ───────────────────────────────
os.environ["MG_COLOR"] = "0"
c(tui.markdown_ligero("**hola** y `codigo`") == "**hola** y `codigo`",
  "sin color, markdown_ligero() no toca el texto (para no ensuciar logs/pipes)")

os.environ["MG_COLOR"] = "1"
render = tui.markdown_ligero("**hola** y `codigo`")
c("**" not in render, "con color, la negrita en Markdown se convierte a ANSI")
c("`" not in render, "y el código en línea también")

os.environ.pop("MG_COLOR", None)

raise SystemExit(c.fin())
