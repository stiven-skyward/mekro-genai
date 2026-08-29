"""tui.py — la estética de terminal, biblioteca estándar y punto.

Claude Code y OpenCode comparten un vocabulario visual: una tarjeta por llamada a
herramienta (intención primero, resultado después), un diff de verdad en vez de un
volcado de argumentos, una caja para pedir permiso, y colores que se apagan solos si la
salida no es una terminal. Nada de eso necesita una dependencia — es ANSI y
`difflib`, que ya están en cualquier Python. Igual que el resto del arnés («sin nada
que compilar», ver pyproject.toml), esto se queda en la biblioteca estándar a propósito:
quien solo quiere BYOK o MCP no tiene por qué instalar un framework de TUI para verlo
bonito.

**Se apaga sola cuando toca.** `activo()` mira `sys.stdout.isatty()`, `NO_COLOR` y
`TERM=dumb` antes de pintar un solo código ANSI — la misma disciplina que costó cara con
`servidor.py` (prints sin flush(), salida bufferizada en redirección): una CLI que
asume terminal interactiva rompe en CI, en logs y en pipes. `MG_COLOR=0/1` fuerza el
comportamiento para pruebas o para quien prefiera lo plano siempre.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time

_RESET = "\033[0m"
_CODIGOS = {
    "negrita": "\033[1m",
    "atenuado": "\033[2m",
    "verde": "\033[32m",
    "rojo": "\033[31m",
    "amarillo": "\033[33m",
    "cian": "\033[36m",
    "magenta": "\033[35m",
}
_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def activo() -> bool:
    forzar = os.environ.get("MG_COLOR")
    if forzar is not None:
        return forzar.strip().lower() not in ("0", "no", "false")
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _c(nombre: str, texto: str) -> str:
    return f"{_CODIGOS[nombre]}{texto}{_RESET}" if activo() else texto


def negrita(t: str) -> str: return _c("negrita", t)
def atenuado(t: str) -> str: return _c("atenuado", t)
def exito(t: str) -> str: return _c("verde", t)
def fallo(t: str) -> str: return _c("rojo", t)
def aviso(t: str) -> str: return _c("amarillo", t)
def resalte(t: str) -> str: return _c("cian", t)


def ancho_visible(s: str) -> int:
    """La longitud que ocupa en pantalla, sin contar los códigos de color."""
    return len(_ESCAPE.sub("", s))


# ── cajas ─────────────────────────────────────────────────────────────────────
def _ancho_terminal() -> int:
    # 80 de suelo: el ancho por defecto más común de cualquier consola (incluida la
    # mayoría de configuraciones de Windows) cuando no se puede preguntar de verdad
    # —salida redirigida, o la terminal no responde el ioctl—.
    return shutil.get_terminal_size(fallback=(80, 24)).columns


def caja(lineas: list[str], titulo: str = "") -> str:
    """Un recuadro de esquinas redondeadas — la misma firma visual que el modal de
    permiso de Claude Code y la ventana de bienvenida de OpenCode. Los bordes son
    caracteres Unicode, no ANSI: se ven igual con o sin color.

    Una línea más ancha que la terminal real ROMPE el recuadro entero —el borde de
    cierre acaba en la fila de abajo, desalineado—, así que aquí se envuelve por
    palabras a lo que quepa antes de calcular nada más. El envoltorio actúa sobre el
    texto SIN color: las pocas líneas que de verdad desbordan hoy son texto plano de
    ayuda, no código coloreado, y perder el color de una línea que se parte es mejor
    que un recuadro que ya no lo es."""
    disponible = max(20, _ancho_terminal() - 4)
    expandidas: list[str] = []
    for l in lineas:
        if ancho_visible(l) <= disponible:
            expandidas.append(l)
        else:
            sin_color = _ESCAPE.sub("", l)
            expandidas.extend(textwrap.wrap(sin_color, disponible) or [""])

    # el título necesita, además de su propio ancho, sitio para al menos un guion
    # de relleno detrás — sin este +2, un título que es la línea más larga de la
    # caja deja el borde de arriba UN CARÁCTER más corto que las filas de abajo.
    minimo_titulo = ancho_visible(titulo) + 2 if titulo else 0
    interior = max([ancho_visible(l) for l in expandidas] + [minimo_titulo] + [10])
    interior = min(interior, disponible)
    if titulo:
        relleno = "─" * max(1, interior - ancho_visible(titulo) - 1)
        sup = f"╭─ {negrita(titulo)} {relleno}╮"
    else:
        sup = "╭" + "─" * (interior + 2) + "╮"
    filas = []
    for l in expandidas:
        pad = " " * max(0, interior - ancho_visible(l))
        filas.append(f"│ {l}{pad} │")
    inf = "╰" + "─" * (interior + 2) + "╯"
    return "\n".join([sup, *filas, inf])


def tabla(filas: list[tuple[str, str]]) -> list[str]:
    """Dos columnas alineadas por el ancho REAL de la primera —nunca espacios
    contados a mano, que es como una descripción larga acaba desbordando la
    terminal sin que nadie lo note hasta que se ve roto en una consola distinta.

    Si una descripción no cabe en una sola línea, se envuelve con SANGRÍA
    COLGANTE bajo la propia columna de descripción —no bajo el margen izquierdo—:
    dejar que `caja()` envolviera esto a ciegas alineaba la continuación como si
    fuera una fila nueva, deshaciendo la tabla entera."""
    ancho = max((ancho_visible(a) for a, _ in filas), default=0)
    disponible = max(16, _ancho_terminal() - 4 - ancho - 2)
    salida = []
    for a, b in filas:
        primera_col = f"{a}{' ' * (ancho - ancho_visible(a))}  "
        envueltas = textwrap.wrap(b, disponible) or [""]
        salida.append(primera_col + envueltas[0])
        sangria = " " * ancho_visible(primera_col)
        salida.extend(sangria + cont for cont in envueltas[1:])
    return salida


def banner(titulo: str, lineas: list[str]) -> str:
    return caja(lineas, titulo=titulo)


# ── llamadas a herramienta ──────────────────────────────────────────────────────
def linea_herramienta(firma: str) -> str:
    """Se imprime ANTES de ejecutar: la intención, no el resultado — lo que Claude
    Code marca con «●» y OpenCode con su propio glifo de turno.

    `Llamada.firma()` corta a los 120 caracteres porque eso también alimenta
    registros y trazas donde el detalle vale la pena; en pantalla, con la terminal
    real de por medio, 120 caracteres siguen desbordando cualquier consola de 80
    columnas (el caso más común). Aquí se recorta OTRA VEZ, más corto, solo para
    lo que se ve en vivo — el registro que ya se guardó con la firma completa no
    se toca."""
    disponible = max(20, _ancho_terminal() - 2)   # "● " ocupa 2 columnas
    if ancho_visible(firma) > disponible:
        firma = firma[:disponible - 1] + "…"
    return f"{resalte('●')} {firma}"


def linea_resultado(ok: bool, resumen: str, segundos: float | None = None) -> str:
    marca = exito("✓") if ok else fallo("✗")
    cola = f"  ({segundos:.1f} s)" if segundos is not None else ""
    primera, _, resto = resumen.partition("\n")
    # la primera línea de una salida real (ruta larga, línea de `bash`, resumen de
    # `git`) puede ser tan larga como la propia firma de la llamada — mismo recorte
    # que linea_herramienta(), por la misma razón: en pantalla manda la terminal
    # real, no un tope fijo pensado para el registro guardado en disco.
    disponible = max(20, _ancho_terminal() - 6 - ancho_visible(cola))
    if ancho_visible(primera) > disponible:
        primera = primera[:disponible - 1] + "…"
    cuerpo = atenuado(primera) if ok else primera
    if resto:
        cuerpo += "\n" + "\n".join(atenuado("  " + l) for l in resto.splitlines())
    # «└», del mismo bloque Unicode que los bordes de caja (muy soportado en
    # cualquier fuente de terminal) — antes iba «⎿», el símbolo de odontología
    # (U+23BF, bloque «Miscellaneous Technical»): casi ninguna fuente de consola lo
    # trae, y en Windows en particular se ve como un cuadro vacío.
    return f"  └ {marca} {cuerpo}{cola}"


# ── diffs ────────────────────────────────────────────────────────────────────
def diff(antes: str, despues: str, tope: int = 40) -> str:
    """Lo que Claude Code/OpenCode enseñan tras un `editar`: qué cambió de verdad, no
    el JSON de argumentos con el que se pidió. `n=1` de contexto basta para ubicarse
    sin inundar una terminal con un cambio de una fichero entero."""
    crudo = list(difflib.unified_diff(antes.splitlines(), despues.splitlines(),
                                      lineterm="", n=1))
    cuerpo = [l for l in crudo if not l.startswith(("---", "+++", "@@"))]
    if not cuerpo:
        return atenuado("    (sin cambios de texto)")
    salida = []
    for l in cuerpo[:tope]:
        if l.startswith("+"):
            salida.append(exito("    + " + l[1:]))
        elif l.startswith("-"):
            salida.append(fallo("    - " + l[1:]))
        else:
            salida.append(atenuado("      " + l[1:]))
    if len(cuerpo) > tope:
        salida.append(atenuado(f"    […{len(cuerpo) - tope} líneas más omitidas…]"))
    return "\n".join(salida)


# ── prosa ────────────────────────────────────────────────────────────────────
_NEGRITA_MD = re.compile(r"\*\*(.+?)\*\*")
_CODIGO_MD = re.compile(r"`([^`]+)`")


def markdown_ligero(texto: str) -> str:
    """No es un parser de Markdown: es lo mínimo que un cerebro suele emitir en
    prosa (negrita, código en línea, viñetas) traducido a ANSI. Se aplica solo a
    texto YA COMPLETO —el resumen de vuelta, la respuesta final—, nunca al streaming
    token a token, porque un `**` puede llegar partido entre dos trozos."""
    if not activo():
        return texto
    salida = []
    for linea in texto.split("\n"):
        l = _NEGRITA_MD.sub(lambda m: negrita(m.group(1)), linea)
        l = _CODIGO_MD.sub(lambda m: resalte(m.group(1)), l)
        despojada = l.lstrip()
        if despojada[:2] in ("- ", "* "):
            l = l[:len(l) - len(despojada)] + atenuado("•") + despojada[1:]
        salida.append(l)
    return "\n".join(salida)


# ── el latido ────────────────────────────────────────────────────────────────
class Heartbeat:
    """El hueco de silencio real de un cerebro local —cargar 9 GB, prefillar el
    contexto, un `<think>` de varios minutos antes del primer carácter— se ve
    IDÉNTICO a un proceso colgado si no hay nada en pantalla. Claude Code y OpenCode
    no necesitan esto: su prefill es sub-segundo. Aquí es la diferencia entre saber
    que sigue vivo y preguntarse si hay que matarlo con Ctrl-C."""

    def __init__(self, etiqueta: str = "generando"):
        self._etiqueta = etiqueta
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._t0 = 0.0

    def iniciar(self) -> None:
        try:
            en_terminal = sys.stdout.isatty()
        except Exception:
            en_terminal = False
        if not en_terminal or self._hilo is not None:
            return
        self._t0 = time.monotonic()
        self._parar.clear()

        def _tick() -> None:
            while not self._parar.wait(0.5):
                seg = time.monotonic() - self._t0
                print(f"\r{atenuado(f'  ·· {self._etiqueta}… {seg:,.0f} s')}",
                     end="", flush=True)

        self._hilo = threading.Thread(target=_tick, daemon=True)
        self._hilo.start()

    def parar(self) -> None:
        if self._hilo is None:
            return
        self._parar.set()
        self._hilo.join(timeout=1)
        self._hilo = None
        print("\r" + " " * 60 + "\r", end="", flush=True)


UMBRAL_AVISO = 15.0   # segundos: por debajo, un aviso es más ruido que ayuda


def avisar_fin(segundos: float, resumen: str) -> None:
    """Campanita de terminal + notificación de escritorio, best-effort, cuando el
    turno fue LARGO — quien se fue a hacer otra cosa mientras el cerebro local
    trabajaba necesita que algo le avise, no que vuelva a mirar la terminal cada
    rato. La campanita (`\\a`) es lo único universal: sobrevive a SSH, tmux y WSL sin
    depender de ningún daemon; la notificación es una capa extra que se calla sola
    si `notify-send`/`osascript` no existen."""
    if segundos < UMBRAL_AVISO:
        return
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass
    for cmd in (["notify-send", "Mekro-Genai", resumen],
               ["osascript", "-e",
                f'display notification {json.dumps(resumen)} with title "Mekro-Genai"']):
        try:
            subprocess.run(cmd, capture_output=True, timeout=2)
            return
        except (OSError, subprocess.SubprocessError):
            continue


def linea_costo(tok_entrada: int, tok_salida: int, precio: dict | None,
                ahorro_cache: float = 0.0) -> str | None:
    """Coste real en USD, SOLO cuando el catálogo conoce el precio del modelo (BYOK).
    `None` para local, suscripción, o un proveedor que models.dev no cataloga —nunca
    una cifra inventada donde no hay dato: la regla del proyecto es cifra medida o
    silencio, nunca una aproximación disfrazada de medición."""
    if not precio:
        return None
    costo = (tok_entrada / 1_000_000) * precio.get("input", 0) \
           + (tok_salida / 1_000_000) * precio.get("output", 0)
    partes = [f"${costo:.4f}"]
    if ahorro_cache > 0:
        partes.append(f"caché: {ahorro_cache * 100:.0f}% de la entrada")
    return atenuado("   " + " · ".join(partes))


def resumen_final(motivo: str, vueltas: int, tok_salida: int, tok_entrada: int,
                  segundos: float, intervenciones: int) -> str:
    partes = [f"{atenuado('──')} {motivo} · {vueltas} vueltas · "
             f"{tok_salida} tok salida / {tok_entrada} entrada · "
             f"{segundos:.1f} s"]
    if intervenciones:
        partes.append(aviso(f"{intervenciones} intervenciones"))
    return " · ".join(partes)
