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
c(len({tui.ancho_visible(l) for l in con_titulo.split("\n")}) == 1,
  "y el borde CON título mide exactamente igual que las filas de abajo — el bug "
  "real: un título que es la línea más larga dejaba el borde de arriba un "
  "carácter más corto, porque el relleno de guiones no reservaba sitio para sí "
  "mismo antes de calcular cuánto haría falta")

titulo_largo = tui.caja(["x"], titulo="un título bastante más largo que el contenido")
c(len({tui.ancho_visible(l) for l in titulo_largo.split("\n")}) == 1,
  "y sigue midiendo igual incluso cuando el título ES la línea más larga de todas "
  "—el caso límite exacto que rompía antes—")

# ── linea_herramienta()/linea_resultado(): tampoco desbordan la terminal ────
os.environ["COLUMNS"] = "80"
firma_larga = "editar(" + "x" * 200 + ")"
c(tui.ancho_visible(tui.linea_herramienta(firma_larga)) <= 80,
  "una firma de 200+ caracteres (un `editar` con muchos cambios, por ejemplo) NO "
  "desborda una terminal de 80 columnas, aunque firma() la deje pasar hasta 120")
c("…" in tui.linea_herramienta(firma_larga),
  "y el recorte lo dice, no lo hace en silencio")

salida_larga = "x" * 200
c(tui.ancho_visible(tui.linea_resultado(True, salida_larga, 1.2)) <= 80,
  "y una primera línea de salida real (ruta larga, línea de bash) tampoco desborda")
os.environ.pop("COLUMNS", None)

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

# ── Heartbeat: sin terminal real, no hace NADA (ni un hilo, ni un carácter) ─
import io
from contextlib import redirect_stdout

latido = tui.Heartbeat("probando")
buf = io.StringIO()
with redirect_stdout(buf):
    latido.iniciar()   # sys.stdout.isatty() es False bajo una prueba: no debe arrancar hilo
    latido.parar()
c(buf.getvalue() == "", "sin TTY, Heartbeat no imprime nada — ni al iniciar ni al parar")
latido.parar()   # una segunda parada sin haber arrancado tampoco debe reventar
c(True, "parar() dos veces seguidas no revienta")

# ── avisar_fin(): campanita solo por encima del umbral, y nunca revienta ────
buf2 = io.StringIO()
with redirect_stdout(buf2):
    tui.avisar_fin(1.0, "turno corto")
c("\a" not in buf2.getvalue(), "un turno corto (bajo el umbral) no suena campanita")

buf3 = io.StringIO()
with redirect_stdout(buf3):
    tui.avisar_fin(tui.UMBRAL_AVISO + 1, "turno largo de prueba")
c("\a" in buf3.getvalue(), "un turno largo sí suena la campanita")
c(True, "y el intento de notificación de escritorio (notify-send/osascript, "
        "ninguno instalado aquí) no rompe nada: es best-effort de verdad")

# ── caja(): NUNCA más ancha que la terminal real — el bug que reportó el usuario ──
_col_vieja = os.environ.get("COLUMNS")
try:
    os.environ["COLUMNS"] = "40"
    larga = "esta línea es bastante más larga que cuarenta columnas de ancho, de sobra"
    recuadro = tui.caja([larga])
    anchos = {len(l) for l in recuadro.split("\n")}
    c(len(anchos) == 1, "con terminal angosta, TODAS las filas miden exactamente igual")
    c(next(iter(anchos)) <= 40,
      "y ninguna fila —ni con una línea que antes desbordaba— pasa del ancho real "
      "de la terminal: esto es justo lo que rompía el /ayuda en una consola de 80 "
      "columnas (81 de ancho real contra 80 disponibles)")
    c(len(recuadro.split("\n")) > 3, "la línea larga se partió en varias filas, no "
                                     "se dejó desbordar ni se cortó en silencio")
finally:
    if _col_vieja is None:
        os.environ.pop("COLUMNS", None)
    else:
        os.environ["COLUMNS"] = _col_vieja

# ── tabla(): alineación por ancho REAL, no espacios contados a mano ─────────
filas = tui.tabla([("/x", "una"), ("/comando-largo", "otra")])
c(filas[0].index("una") == filas[1].index("otra"),
  "la columna de descripción empieza en la MISMA posición en ambas filas, "
  "calculada del comando más largo — no de contar espacios en el código fuente")

# ── linea_resultado(): sin el símbolo de odontología (casi ninguna fuente lo trae) ──
os.environ["MG_COLOR"] = "0"
c("⎿" not in tui.linea_resultado(True, "algo"),
  "el conector de resultado ya NO es el símbolo de odontología (U+23BF)")
c("└" in tui.linea_resultado(True, "algo"),
  "sino uno del bloque de caracteres de caja — el mismo que ya usan los bordes, "
  "así que si esos se ven bien, este también")
os.environ.pop("MG_COLOR", None)

raise SystemExit(c.fin())
