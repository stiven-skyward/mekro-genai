"""Poda en el origen: gastar menos entrada sin perder lo que decide la tarea.

El porqué está medido en docs/ahorro.md y cabe en una frase: **el gasto de una carrera
es entrada en proporción ~40:1**, y la entrada es la transcripción reenviada cada
vuelta. De ahí las dos leyes que gobiernan este fichero:

1. **Un dato cuesta su tamaño POR lo que le queda de vida.** Una observación que entra
   en la vuelta 2 de una tarea de 10 se paga 9 veces; la misma en la vuelta 9, una. Por
   eso la poda aquí no es un tope fijo: **aprieta cuando quedan muchas vueltas y afloja
   cuando quedan pocas**. Ni RTK ni headroom ni ponytail hacen esto.
2. **Se poda ANTES de entrar, jamás después.** Reescribir transcripción ya enviada
   rompe el prefijo cacheado del proveedor y sale MÁS caro que no tocar nada
   (la aritmética, en docs/ahorro.md). Aquí solo se toca lo que aún no ha entrado.

Y la regla que lo hace honesto: **podar no es perder**. Todo lo podado se guarda entero
en `.genai/podado/` y el aviso dice cómo recuperarlo. Un ahorro que le esconde al modelo
algo que necesitaba no es ahorro: es una avería que además miente.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

MAX_SALIDA = 12_000        # el tope de siempre, cuando quedan pocas vueltas
MIN_FACTOR = 0.20          # ni con 30 vueltas por delante se baja de un 20 % del tope
VUELTAS_HOLGADAS = 3       # con 3 o menos por delante, no se aprieta nada


def factor_vueltas(restantes: int) -> float:
    """Cuánto del tope se concede, según lo que le queda de vida al dato.

    La forma sale de la ley 1: el coste es tamaño × vueltas restantes, así que para
    mantener el coste acotado el tamaño concedido va como 1/restantes."""
    if restantes <= VUELTAS_HOLGADAS:
        return 1.0
    return max(MIN_FACTOR, VUELTAS_HOLGADAS / float(restantes))


# ── filtros por herramienta ────────────────────────────────────────────────────
# Cada uno quita ruido ESTRUCTURAL: repetición, progreso, decoración. Ninguno decide
# qué es importante — esa decisión es del modelo y no se le quita.

_RUIDO = re.compile(
    r"^\s*(?:"
    r"\d+%\s|\[[=>\-#\s]+\]|"                       # barras de progreso
    r"(?:Collecting|Downloading|Installing|Requirement already satisfied|"
    r"npm (?:WARN|notice)|added \d+ packages|Using cached)\b|"
    r"warning: unused|note: `#\[warn"                # ruido de compiladores
    r")", re.I)


def _sin_ruido(texto: str) -> str:
    return "\n".join(l for l in texto.splitlines() if not _RUIDO.match(l))


def _dedup(texto: str) -> str:
    """Líneas idénticas repetidas → una con su cuenta. Los logs viven de esto."""
    fuera, previa, veces = [], None, 0
    for l in texto.splitlines():
        if l == previa:
            veces += 1
            continue
        if veces:
            fuera.append(f"    […  la línea anterior se repite {veces} veces más]")
        fuera.append(l)
        previa, veces = l, 0
    if veces:
        fuera.append(f"    […  la línea anterior se repite {veces} veces más]")
    return "\n".join(fuera)


def _pruebas(texto: str) -> str:
    """Salida de pruebas: lo que importa es lo que FALLA y el resumen.

    Un `pytest` verde de 400 líneas dice exactamente lo mismo que su última línea, y
    cuesta 400 veces más durante el resto de la tarea."""
    if not re.search(r"\b(passed|failed|OK|FAILED|asertos|\d+ tests?)\b", texto):
        return texto
    lineas = texto.splitlines()
    if not any(re.search(r"\b(FAIL|FAILED|ERROR|Traceback|assert)\b", l) for l in lineas):
        cola = [l for l in lineas[-6:] if l.strip()]
        if len(lineas) > 12:
            return ("[poda: la suite pasó entera; se conserva el resumen. "
                    f"{len(lineas)} líneas en .genai/podado/]\n" + "\n".join(cola))
    # hay fallos: se conservan con su contexto, se tira el verde de en medio
    guardar, fuera = set(), []
    for i, l in enumerate(lineas):
        if re.search(r"\b(FAIL|FAILED|ERROR|Traceback|assert)\b", l):
            guardar.update(range(max(0, i - 2), min(len(lineas), i + 12)))
    guardar.update(range(max(0, len(lineas) - 5), len(lineas)))
    ultimo = -2
    for i in sorted(guardar):
        if i > ultimo + 1:
            fuera.append("    […]")
        fuera.append(lineas[i])
        ultimo = i
    return "\n".join(fuera)


def _grep(texto: str) -> str:
    """`ruta:linea:contenido` repetido por fichero → un encabezado por fichero.

    Cuando 40 aciertos caen en 3 ficheros, la ruta se paga 40 veces para decir 3 cosas."""
    filas = [l.split(":", 2) for l in texto.splitlines() if l.count(":") >= 2]
    if len(filas) < 6 or not all(len(f) == 3 for f in filas):
        return texto
    por_fichero: dict[str, list[str]] = {}
    for ruta, num, cont in filas:
        por_fichero.setdefault(ruta, []).append(f"{num}: {cont}")
    if len(por_fichero) >= len(filas):
        return texto                       # un acierto por fichero: agrupar no ahorra
    fuera = []
    for ruta, aciertos in por_fichero.items():
        fuera.append(f"{ruta}  ({len(aciertos)} aciertos)")
        fuera.extend("  " + a for a in aciertos)
    return "\n".join(fuera)


FILTROS = {
    "bash":     (_sin_ruido, _dedup, _pruebas),
    "grep":     (_grep,),
    "listar":   (_dedup,),
    "subagente": (),
    "leer":     (),                        # leer ya lo acota quien llama
}


def _guardar(salida: str) -> str:
    """Lo podado se guarda entero. Devuelve la referencia con la que recuperarlo."""
    ref = hashlib.sha256(salida.encode("utf-8", "replace")).hexdigest()[:12]
    try:
        d = Path(os.environ.get("MG_PODADO", ".genai/podado"))
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ref}.txt"
        if not f.exists():
            f.write_text(salida, encoding="utf-8")
    except OSError:
        return ""                          # sin sitio donde guardar, no se poda a ciegas
    return ref


def podar(herramienta: str, salida: str, vueltas_restantes: int = 8,
          activo: bool = True) -> tuple[str, dict]:
    """Devuelve (texto que entra en la transcripción, cifras del ahorro).

    `activo=False` deja pasar todo tal cual: es el brazo de control del A/B, porque un
    ahorro solo cuenta si se ha medido contra su propia ausencia."""
    antes = len(salida)
    if not activo or antes < 400:
        return salida, {"antes": antes, "despues": antes, "ref": ""}

    texto = salida
    for f in FILTROS.get(herramienta, (_sin_ruido, _dedup)):
        texto = f(texto)

    tope = max(1200, int(MAX_SALIDA * factor_vueltas(vueltas_restantes)))
    if len(texto) > tope:
        ref = _guardar(salida)
        mitad = tope // 2
        aviso = (f"\n\n[… {len(texto) - tope} caracteres podados. "
                 f"Quedan {vueltas_restantes} vueltas y cada carácter que entre aquí se "
                 f"reenvía en todas ellas, así que se aprieta. "
                 + (f"Entero en .genai/podado/{ref}.txt si te hace falta. " if ref else "")
                 + "Mejor que releer: acota (una ruta, un patrón más estrecho) …]\n\n")
        texto = texto[:mitad] + aviso + texto[-mitad:]
    return texto, {"antes": antes, "despues": len(texto),
                   "ref": "" if len(texto) >= antes else "podado"}
