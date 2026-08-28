"""holograma.py — Holograma de Tarea: contexto que se reconstruye, no que se carga.

Adaptado de `E:\\QuantModels\\holograma.py`, que a su vez viene de `E:\\Mekro`
(`mekro-lex/holograma.py`). Aquí no es una herramienta auxiliar: es **la arquitectura
de contexto del arnés** (META.md §puerta 1), y la ensayamos con nosotros mismos antes
de exigírsela a un cerebro que genera a 1-3 tokens/s.

EL PROBLEMA
-----------
Lo que se pierde cuando muere una sesión no es el código —ese está en disco— sino **por
qué se estaba mirando ese trozo**: el hilo entre un síntoma observado y las veinte líneas
que lo causan. Ese hilo se reconstruye a mano cada vez, y es lo más caro de todo.

LA INVENCIÓN
------------
Un holograma óptico no guarda la imagen: guarda el patrón de interferencia desde el que la
imagen se reconstruye al iluminarlo, y un fragmento pequeño basta para recuperar la escena
entera. Aquí igual. Un Holograma de Tarea no guarda el contexto: guarda las **anclas**
—punteros a símbolos concretos— más la razón por la que importan. Al «iluminarlo» (`foco`),
la herramienta va al disco, extrae exactamente esos símbolos y reconstruye el contexto.

    contexto = f(anclas)        en vez de        contexto = payload

Tres propiedades que se siguen de eso:

1. **Sobrevive a la muerte de la sesión.** El holograma está en disco; la ventana no. Una
   sesión nueva hace `foco H1` y está trabajando en treinta segundos, sin resumen.
2. **No envejece en silencio.** Si alguien renombra el símbolo al que apunta un ancla,
   `verificar` lo grita. Un resumen en prosa se pudre sin avisar.
3. **Cuesta lo que decidir, no lo que leer.** Un fichero de 2 KB regenera lo que habría
   que leer en decenas de KB. Ese factor es exactamente el presupuesto que le falta al
   cerebro local.

USO
---
    python3 holograma.py listar              # el mapa: ~40 tokens por tarea
    python3 holograma.py foco H1             # ilumina: tarea + código reconstruido
    python3 holograma.py buscar rvq          # ¿qué símbolos contienen «rvq»?
    python3 holograma.py verificar           # ¿se pudrió alguna ancla?
    python3 holograma.py anotar H1 "..."     # deja constancia para la sesión siguiente
    python3 holograma.py cerrar H1           # ejecuta su comprobación y decide
    python3 holograma.py retirar H1 "..."    # su SUJETO dejó de existir (≠ cerrado)
    python3 holograma.py nuevo H9 "título"   # abre uno
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent))
HOLOS = Path(os.environ.get("MG_HOLOS", RAIZ / "holos"))
CODIGO = [RAIZ / "genai", RAIZ / "tests", RAIZ / "scripts", RAIZ / "banco", RAIZ]

PLANTILLA = """# {ident} · {titulo}

estado: abierto
gravedad: media
hito: M1

## SINTOMA
lo que hace:
lo que debia hacer:

## ANCLAS
# una por linea, sin «#»: genai/cerebro/base.py:Cerebro · scripts/sonda.py:1-40

## CAUSA
(por determinar)

## CIERRE
# el comando que decide si esto esta arreglado

## BITACORA
"""

# ───────────────────────────────────────────────────────────────────────────
#  lectura de hologramas
# ───────────────────────────────────────────────────────────────────────────

def _ruta(ident: str) -> Path:
    return HOLOS / f"{ident.upper()}.md"


def _leer(ident: str) -> dict:
    p = _ruta(ident)
    if not p.exists():
        raise SystemExit(f"no existe el holograma {ident.upper()} en {HOLOS}")
    sec: dict = {"_titulo": "", "_cab": {}, "_id": ident.upper(), "_ruta": p}
    actual = None
    for linea in p.read_text(encoding="utf-8").splitlines():
        if linea.startswith("# ") and not sec["_titulo"]:
            sec["_titulo"] = re.sub(rf"^{sec['_id']}\s*·\s*", "", linea[2:].strip())
        elif linea.startswith("## "):
            actual = linea[3:].strip().upper()
            sec[actual] = []
        elif actual is None and ":" in linea and not linea.startswith("#"):
            k, _, v = linea.partition(":")
            sec["_cab"][k.strip().lower()] = v.strip()
        elif actual is not None:
            sec[actual].append(linea)
    for k in list(sec):
        if isinstance(sec[k], list):
            sec[k] = "\n".join(sec[k]).strip()
    return sec


def _todos() -> list[dict]:
    if not HOLOS.exists():
        return []
    return [_leer(p.stem) for p in sorted(HOLOS.glob("*.md"))]


def _anclas(h: dict) -> list[str]:
    return [a.strip() for a in h.get("ANCLAS", "").splitlines()
            if a.strip() and not a.strip().startswith("#")]


# ───────────────────────────────────────────────────────────────────────────
#  EL NÚCLEO: resolver un ancla contra el disco
# ───────────────────────────────────────────────────────────────────────────

def _fichero(nombre: str) -> Path | None:
    p = Path(nombre)
    if p.is_absolute() and p.exists():
        return p
    if (RAIZ / p).exists():
        return RAIZ / p
    for base in CODIGO:                       # búsqueda por nombre de fichero
        if not base.exists():
            continue
        for c in base.rglob(p.name):
            if c.is_file():
                return c
    return None


def _extraer_simbolo(fuente: str, nombre: str) -> tuple[int, int] | None:
    """Rango de líneas de una función, método, clase o constante de módulo.

    Se usa el AST y no una expresión regular a propósito: una subcadena casa por
    accidente («leer» está dentro de «leer_ventana», «_leer» y una docena de
    comentarios). Un ancla que casa por accidente reconstruiría el contexto
    EQUIVOCADO, que es peor que no reconstruir ninguno.

    Admite `Clase.metodo` para desambiguar métodos con nombres repetidos.
    """
    try:
        arbol = ast.parse(fuente)
    except SyntaxError:
        return None
    padre, _, hijo = nombre.rpartition(".")
    ambito: ast.AST = arbol
    if padre:
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef) and nodo.name == padre:
                ambito = nodo
                break
        else:
            return None
    for nodo in ast.walk(ambito):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if nodo.name == hijo:
                ini = min([nodo.lineno] + [d.lineno for d in nodo.decorator_list])
                return ini, nodo.end_lineno or nodo.lineno
        elif isinstance(nodo, ast.Assign):
            for t in nodo.targets:
                if isinstance(t, ast.Name) and t.id == hijo:
                    return nodo.lineno, nodo.end_lineno or nodo.lineno
        elif isinstance(nodo, ast.AnnAssign):
            if isinstance(nodo.target, ast.Name) and nodo.target.id == hijo:
                return nodo.lineno, nodo.end_lineno or nodo.lineno
    return None


def iluminar(ancla: str) -> str:
    """Un ancla `fichero:selector` → el trozo de disco al que apunta.

    Selector: un símbolo (`Cerebro`, `Sesion.turno`) o un rango (`1-40`).
    """
    ancla = ancla.strip()
    nombre, _, sel = ancla.partition(":")
    p = _fichero(nombre)
    if p is None:
        return f"⚠ ANCLA ROTA: no existe el fichero {nombre!r}"
    texto = p.read_text(encoding="utf-8", errors="replace")
    lineas = texto.splitlines()
    rel = p.relative_to(RAIZ) if p.is_relative_to(RAIZ) else p

    if not sel:
        ini, fin = 1, min(len(lineas), 40)
    elif re.fullmatch(r"\d+-\d+", sel):
        a, b = sel.split("-")
        ini, fin = int(a), int(b)
    else:
        r = _extraer_simbolo(texto, sel)
        if r is None:
            return f"⚠ ANCLA ROTA: {rel} ya no define {sel!r}"
        ini, fin = r

    ini, fin = max(1, ini), min(len(lineas), fin)
    cuerpo = "\n".join(f"{i:>5} │ {lineas[i - 1]}" for i in range(ini, fin + 1))
    return f"── {rel}:{sel or f'{ini}-{fin}'}  (L{ini}-{fin})\n{cuerpo}"


# ───────────────────────────────────────────────────────────────────────────
#  órdenes
# ───────────────────────────────────────────────────────────────────────────

def cmd_listar(_: list[str]) -> int:
    hs = _todos()
    if not hs:
        print(f"sin hologramas en {HOLOS}")
        return 0
    abiertos = [h for h in hs
                if h["_cab"].get("estado", "abierto") not in ("cerrado", "retirado")]
    print(f"{len(abiertos)} abiertos de {len(hs)} · {HOLOS}\n")
    for h in hs:
        est = h["_cab"].get("estado", "abierto")
        # `retirado` NO es `cerrado`, y la distinción no es cosmética: cerrado significa
        # que la comprobación PASÓ; retirado, que la tarea dejó de existir por un cambio
        # de plan. Confundirlos hace creer que se resolvió algo que solo se abandonó.
        marca = {"cerrado": "✓", "retirado": "⊘"}.get(
            est, "‼" if h["_cab"].get("gravedad") == "grave" else "·")
        hito = h["_cab"].get("hito", "")
        print(f"{marca} {h['_id']:4s} {h['_titulo'][:58]:58s} "
              f"{hito:3s} {len(_anclas(h))} anclas")
    return 0


def cmd_foco(args: list[str]) -> int:
    """Ilumina el holograma: la tarea y, detrás, el código exacto que la toca."""
    if not args:
        raise SystemExit("uso: holograma.py foco H1")
    h = _leer(args[0])
    print(f"╔═ {h['_id']} · {h['_titulo']}")
    for k, v in h["_cab"].items():
        print(f"║ {k}: {v}")
    print("╚" + "═" * 66)
    for s in ("SINTOMA", "CAUSA", "CIERRE", "BITACORA"):
        if h.get(s):
            print(f"\n【{s}】\n{h[s]}")
    anclas = _anclas(h)
    if not anclas:
        return 0
    print(f"\n【CÓDIGO RECONSTRUIDO】 {len(anclas)} anclas\n")
    reconstruido = bruto = 0
    for a in anclas:
        trozo = iluminar(a)
        print(trozo + "\n")
        reconstruido += len(trozo)
        p = _fichero(a.partition(":")[0])
        if p is not None:
            bruto += len(p.read_text(encoding="utf-8", errors="replace"))
    if bruto:
        print(f"── {reconstruido / 1024:.1f} KB reconstruidos de "
              f"{bruto / 1024:.1f} KB en bruto ({100 * (1 - reconstruido / bruto):.0f} % ahorrado)")
    return 0


def cmd_buscar(args: list[str]) -> int:
    """Qué símbolos contienen un texto. Por AST, no por grep: devuelve símbolos."""
    if not args:
        raise SystemExit("uso: holograma.py buscar rvq")
    aguja = args[0].lower()
    n = 0
    vistos: set[Path] = set()
    for base in CODIGO:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.py")):
            if p in vistos or ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            vistos.add(p)
            try:
                arbol = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            rel = p.relative_to(RAIZ) if p.is_relative_to(RAIZ) else p
            for nodo in ast.walk(arbol):
                if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if aguja in nodo.name.lower():
                        tipo = "clase" if isinstance(nodo, ast.ClassDef) else "def"
                        largo = (nodo.end_lineno or nodo.lineno) - nodo.lineno + 1
                        print(f"{rel}:{nodo.name}  ({tipo}, {largo} líneas, L{nodo.lineno})")
                        n += 1
    if not n:
        print(f"ningún símbolo contiene «{args[0]}»")
    return 0


def cmd_verificar(_: list[str]) -> int:
    """¿Se ha podrido alguna ancla? Es la revisión que evita reconstruir mentiras."""
    rotas = 0
    for h in _todos():
        for a in _anclas(h):
            trozo = iluminar(a)
            if trozo.startswith("⚠"):
                print(f"{h['_id']} → {a}\n   {trozo}")
                rotas += 1
    total = sum(len(_anclas(h)) for h in _todos())
    print(f"\n{total - rotas}/{total} anclas vivas" if total else "sin anclas")
    return 1 if rotas else 0


def cmd_anotar(args: list[str]) -> int:
    if len(args) < 2:
        raise SystemExit('uso: holograma.py anotar H1 "lo que pasó"')
    h = _leer(args[0])
    sello = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    with h["_ruta"].open("a", encoding="utf-8") as fh:
        fh.write(f"\n- [{sello}] {' '.join(args[1:])}")
    print(f"anotado en {h['_id']}")
    return 0


def cmd_cerrar(args: list[str]) -> int:
    """Ejecuta la comprobación del holograma. Solo si pasa, lo cierra."""
    if not args:
        raise SystemExit("uso: holograma.py cerrar H1")
    h = _leer(args[0])
    cmd = "\n".join(l for l in h.get("CIERRE", "").splitlines()
                    if l.strip() and not l.strip().startswith("#")).strip()
    if not cmd:
        raise SystemExit(f"{h['_id']} no tiene comando de CIERRE: no se puede verificar")
    print(f"$ {cmd}\n" + "─" * 66)
    r = subprocess.run(cmd, shell=True, cwd=RAIZ)
    sello = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    txt = h["_ruta"].read_text(encoding="utf-8")
    if r.returncode == 0:
        txt = re.sub(r"^estado:.*$", "estado: cerrado", txt, count=1, flags=re.M)
        txt += f"\n- [{sello}] CERRADO: la comprobación pasó."
        h["_ruta"].write_text(txt, encoding="utf-8")
        print(f"\n✓ {h['_id']} cerrado.")
        return 0
    txt += f"\n- [{sello}] intento de cierre FALLIDO (código {r.returncode})."
    h["_ruta"].write_text(txt, encoding="utf-8")
    print(f"\n‼ {h['_id']} SIGUE ABIERTO: la comprobación falló.")
    return 1


def cmd_retirar(args: list[str]) -> int:
    """Su SUJETO dejó de existir. No es lo mismo que cerrado y no debe parecerlo."""
    if len(args) < 2:
        raise SystemExit('uso: holograma.py retirar H1 "por qué dejó de existir"')
    h = _leer(args[0])
    razon = " ".join(args[1:])
    sello = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    txt = h["_ruta"].read_text(encoding="utf-8")
    txt = re.sub(r"^estado:.*$", "estado: retirado", txt, count=1, flags=re.M)
    txt += f"\n- [{sello}] RETIRADO (≠ cerrado): {razon}"
    h["_ruta"].write_text(txt, encoding="utf-8")
    print(f"⊘ {h['_id']} retirado. NO es lo mismo que cerrado: su comprobación nunca pasó.")
    return 0


def cmd_nuevo(args: list[str]) -> int:
    if len(args) < 2:
        raise SystemExit('uso: holograma.py nuevo H9 "título"')
    ident = args[0].upper()
    p = _ruta(ident)
    if p.exists():
        raise SystemExit(f"{ident} ya existe: {p}")
    HOLOS.mkdir(parents=True, exist_ok=True)
    p.write_text(PLANTILLA.format(ident=ident, titulo=" ".join(args[1:])), encoding="utf-8")
    print(f"creado {p}")
    return 0


ORDENES = {"listar": cmd_listar, "foco": cmd_foco, "buscar": cmd_buscar,
           "verificar": cmd_verificar, "anotar": cmd_anotar, "cerrar": cmd_cerrar,
           "retirar": cmd_retirar, "nuevo": cmd_nuevo}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ORDENES:
        print(__doc__)
        return 0
    return ORDENES[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
