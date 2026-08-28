"""ciclo.py — el ciclo de investigación: nada se afirma sin haberlo predicho antes.

EL PROBLEMA QUE RESUELVE
------------------------
La lección más cara que traen Mekro_Gen y QuantModels no es técnica: es
epistemológica. Se mide algo, sale un número, y **se le busca una explicación después**.
Como cualquier número admite explicación a posteriori, así nunca se descarta nada y el
proyecto camina en círculos gastando carreras de treinta horas.

La cura es de una sola pieza: **la predicción se escribe ANTES de medir, y queda en
disco**. Si el número la contradice, la hipótesis está refutada y se dice. Si no se
escribió antes, no falsa nada; solo se está racionalizando.

Esto no es papeleo. Es la diferencia entre un proyecto de investigación y un paseo.

EL CICLO
--------
    abrir ──▶ revisar ──▶ predecir ──▶ sonda ──▶ medir ──▶ veredicto ──▶ (lección)
              qué ya      qué espero    prueba     la        confirma      a
              sabemos     y por qué     barata     carrera   o refuta      CONTINUIDAD

Dos puertas duras, impuestas por el código y no por la buena voluntad:

1. **`medir` se niega a correr si no hay `predecir`.** Es la única regla que hace
   falsable todo lo demás.
2. **`veredicto` exige una lección escrita** antes de cerrar el ciclo. Un ciclo que no
   dejó lección no se cierra: o no se entendió, o no valía la pena hacerlo.

CONTRATO DE MEDICIÓN
--------------------
El comando de `sonda` y el de `medir` deben imprimir en su salida al menos una línea

    CIFRA <nombre> <valor>

Es todo el acoplamiento que hay entre el ciclo y lo que se mide: cualquier script en
cualquier lenguaje puede participar imprimiendo esa línea. La comparación con lo
predicho es aritmética sobre esos valores, no interpretación de prosa.

USO
---
    python3 ciclo.py abrir C1 "¿se puede recuperar la estructura RVQ de h13b?"
    python3 ciclo.py revisar C1 "hermetic3.py:134 permuta grupos enteros, no columnas"
    python3 ciclo.py predecir C1 unicos "<0.9" --porque "si son codigos, se repiten"
    python3 ciclo.py sonda C1 -- python3 scripts/sondear_estructura.py --capa 0
    python3 ciclo.py medir C1 -- bash scripts/lanzar_empaquetado.sh
    python3 ciclo.py veredicto C1 --leccion "los grupos son contiguos: recuperable"
    python3 ciclo.py estado                # ¿hay una hipótesis sin veredicto?
    python3 ciclo.py listar
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent))
CICLOS = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
FASES = ["abierto", "revisado", "predicho", "sondado", "medido", "cerrado"]


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _ruta(ident: str) -> Path:
    return CICLOS / f"{ident.upper()}.json"


def _leer(ident: str) -> dict:
    p = _ruta(ident)
    if not p.exists():
        raise SystemExit(f"no existe el ciclo {ident.upper()} en {CICLOS}")
    return json.loads(p.read_text(encoding="utf-8"))


def _escribir(c: dict) -> None:
    CICLOS.mkdir(parents=True, exist_ok=True)
    _ruta(c["id"]).write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")


def _todos() -> list[dict]:
    if not CICLOS.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CICLOS.glob("*.json"))]


def _bitacora(c: dict, texto: str) -> None:
    c.setdefault("bitacora", []).append({"cuando": _ahora(), "que": texto})


# ───────────────────────────────────────────────────────────────────────────
#  el contrato de medición: CIFRA <nombre> <valor>
# ───────────────────────────────────────────────────────────────────────────

_RE_CIFRA = re.compile(r"^\s*CIFRA\s+([A-Za-z_][\w.-]*)\s+(-?[\d.]+(?:[eE][-+]?\d+)?)\s*$", re.M)


def _cifras(salida: str) -> dict[str, float]:
    """Extrae las cifras declaradas. Deliberadamente estricto: una línea mal formada
    NO se adivina. Adivinar aquí sería inventar el resultado de un experimento."""
    return {m.group(1): float(m.group(2)) for m in _RE_CIFRA.finditer(salida)}


def _cumple(valor: float, espero: str) -> bool:
    """`espero` es una comparación textual: «<3000», «>=0.5», «~7.46±2%»."""
    espero = espero.strip().replace(" ", "")
    m = re.fullmatch(r"~(-?[\d.]+)±([\d.]+)(%?)", espero)
    if m:
        centro, tol, pct = float(m.group(1)), float(m.group(2)), m.group(3)
        margen = abs(centro) * tol / 100 if pct else tol
        return abs(valor - centro) <= margen
    m = re.fullmatch(r"(<=|>=|<|>|==|!=)(-?[\d.]+(?:[eE][-+]?\d+)?)", espero)
    if not m:
        raise SystemExit(f"predicción ininteligible: {espero!r} "
                         "(usa «<3000», «>=0.5», «==1» o «~7.46±2%»)")
    op, ref = m.group(1), float(m.group(2))
    return {"<": valor < ref, "<=": valor <= ref, ">": valor > ref,
            ">=": valor >= ref, "==": valor == ref, "!=": valor != ref}[op]


def _correr(cmd: list[str], etiqueta: str) -> dict:
    """Corre el comando enseñando su salida y guardándola. Sin capturar a ciegas:
    una carrera de horas que no se ve por pantalla es una carrera que nadie vigila."""
    linea = " ".join(cmd)
    print(f"$ {linea}\n" + "─" * 66, flush=True)
    t0 = datetime.now(timezone.utc)
    # Línea a línea y no `capture_output`: una carrera de horas cuya salida solo aparece
    # al terminar es una carrera que nadie puede vigilar —ni decidir abortar a tiempo.
    trozos: list[str] = []
    proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert proc.stdout is not None
    for l in proc.stdout:
        trozos.append(l)
        print(l, end="", flush=True)
    codigo = proc.wait()
    salida = "".join(trozos)
    seg = (datetime.now(timezone.utc) - t0).total_seconds()
    cif = _cifras(salida)
    print("─" * 66)
    print(f"{etiqueta}: código {codigo} · {seg:.0f} s · "
          f"cifras {cif if cif else '(NINGUNA — falta la línea «CIFRA nombre valor»)'}")
    return {"cuando": _ahora(), "comando": linea, "codigo": codigo,
            "segundos": round(seg, 1), "cifras": cif,
            "salida_cola": "\n".join(salida.splitlines()[-40:])}


def _tras_doble_guion(args: list[str]) -> tuple[list[str], list[str]]:
    if "--" in args:
        i = args.index("--")
        return args[:i], args[i + 1:]
    return args, []


# ───────────────────────────────────────────────────────────────────────────
#  órdenes
# ───────────────────────────────────────────────────────────────────────────

def cmd_abrir(args: list[str]) -> int:
    if len(args) < 2:
        raise SystemExit('uso: ciclo.py abrir C1 "la pregunta que se quiere zanjar"')
    ident = args[0].upper()
    if _ruta(ident).exists():
        raise SystemExit(f"{ident} ya existe: {_ruta(ident)}")
    c = {"id": ident, "pregunta": " ".join(args[1:]), "fase": "abierto",
         "abierto": _ahora(), "revision": None, "prediccion": None,
         "sonda": None, "medicion": None, "veredicto": None, "leccion": None,
         "bitacora": []}
    _bitacora(c, "abierto")
    _escribir(c)
    print(f"{ident} abierto · siguiente: ciclo.py revisar {ident} \"qué sabemos ya\"")
    return 0


def cmd_revisar(args: list[str]) -> int:
    """Qué se sabe ya. Sirve para no volver a pagar por algo que CONTINUIDAD ya contestó."""
    if len(args) < 2:
        raise SystemExit('uso: ciclo.py revisar C1 "lo que ya sabemos y de dónde sale"')
    c = _leer(args[0])
    c["revision"] = {"cuando": _ahora(), "texto": " ".join(args[1:])}
    c["fase"] = "revisado"
    _bitacora(c, "revisado")
    _escribir(c)
    print(f"{c['id']} revisado · siguiente: ciclo.py predecir {c['id']} <metrica> \"<3000\" --porque \"...\"")
    return 0


def cmd_predecir(args: list[str]) -> int:
    """LA PUERTA. Sin esto, `medir` se niega a correr."""
    porque = ""
    if "--porque" in args:
        i = args.index("--porque")
        porque = " ".join(args[i + 1:])
        args = args[:i]
    if len(args) < 3:
        raise SystemExit('uso: ciclo.py predecir C1 tokens "<3000" --porque "razón"')
    c = _leer(args[0])
    metrica, espero = args[1], args[2]
    _cumple(0.0, espero)                      # valida la sintaxis ahora, no después
    if not porque.strip():
        raise SystemExit("una predicción sin --porque no es una predicción: es una apuesta")
    if c.get("prediccion"):
        raise SystemExit(f"{c['id']} ya predijo {c['prediccion']['metrica']} "
                         f"{c['prediccion']['espero']}. Reescribirla después de ver el "
                         "número es exactamente lo que este fichero existe para impedir. "
                         "Abre un ciclo nuevo.")
    c["prediccion"] = {"cuando": _ahora(), "metrica": metrica,
                       "espero": espero, "porque": porque.strip()}
    c["fase"] = "predicho"
    _bitacora(c, f"predicho {metrica} {espero}")
    _escribir(c)
    print(f"{c['id']}: predicho {metrica} {espero}\n  porque: {porque.strip()}\n"
          f"siguiente: ciclo.py sonda {c['id']} -- <comando barato>")
    return 0


def cmd_sonda(args: list[str]) -> int:
    """La comprobación barata que zanja antes de gastar la cara."""
    args, cmd = _tras_doble_guion(args)
    if not args or not cmd:
        raise SystemExit("uso: ciclo.py sonda C1 -- python3 scripts/sondear_estructura.py")
    c = _leer(args[0])
    c["sonda"] = _correr(cmd, "sonda")
    c["fase"] = "sondado"
    _bitacora(c, f"sonda: código {c['sonda']['codigo']}")
    _escribir(c)
    if c.get("prediccion"):
        _informe(c, c["sonda"], "sonda")
    return 0


def cmd_medir(args: list[str]) -> int:
    args, cmd = _tras_doble_guion(args)
    if not args or not cmd:
        raise SystemExit("uso: ciclo.py medir C1 -- bash scripts/lanzar_carrera.sh")
    c = _leer(args[0])
    if not c.get("prediccion"):
        raise SystemExit(
            f"{c['id']} no tiene predicción escrita. NO se mide.\n"
            "  El número que salga de aquí no podría refutar nada: cualquier resultado\n"
            "  admitiría una explicación inventada después. Escribe primero:\n"
            f"    python3 ciclo.py predecir {c['id']} <metrica> \"<valor>\" --porque \"...\"")
    c["medicion"] = _correr(cmd, "medición")
    c["fase"] = "medido"
    _bitacora(c, f"medido: código {c['medicion']['codigo']}")
    _escribir(c)
    _informe(c, c["medicion"], "medición")
    print(f"\nsiguiente: ciclo.py veredicto {c['id']} --leccion \"...\"")
    return 0


def _informe(c: dict, corrida: dict, etiqueta: str) -> None:
    p = c["prediccion"]
    v = corrida["cifras"].get(p["metrica"])
    if v is None:
        print(f"\n⚠ la {etiqueta} no imprimió «CIFRA {p['metrica']} <valor>»: "
              "no se puede contrastar con la predicción.")
        return
    ok = _cumple(v, p["espero"])
    print(f"\n{'✓ CONFIRMA' if ok else '✗ REFUTA'} · {p['metrica']} = {v} "
          f"vs predicho {p['espero']}\n  se predijo porque: {p['porque']}")


def cmd_veredicto(args: list[str]) -> int:
    """Confirma o refuta, y exige la lección. Un ciclo sin lección no se cierra."""
    leccion = ""
    if "--leccion" in args:
        i = args.index("--leccion")
        leccion = " ".join(args[i + 1:])
        args = args[:i]
    if not args:
        raise SystemExit('uso: ciclo.py veredicto C1 --leccion "lo que ahora sabemos"')
    c = _leer(args[0])
    # Asimetría deliberada: una sonda barata que REFUTA cierra el ciclo —para eso está,
    # para zanjar antes de gastar la carrera cara—, pero una sonda que confirma NO basta.
    # Confirmar sobre una muestra pequeña es justo el error que este fichero existe para
    # impedir: creerse la primera señal favorable.
    fuente = "medicion" if c.get("medicion") else ("sonda" if c.get("sonda") else None)
    if fuente is None:
        raise SystemExit(f"{c['id']} no se ha medido ni sondeado todavía")
    if not leccion.strip():
        raise SystemExit(
            f"{c['id']} no se cierra sin --leccion.\n"
            "  Un ciclo que no dejó lección o no se entendió o no valía la pena.\n"
            "  La lección va también a CONTINUIDAD.md, donde no se borra nunca.")
    p = c["prediccion"]
    v = c[fuente]["cifras"].get(p["metrica"])
    if v is None:
        raise SystemExit(f"la {fuente} no imprimió «CIFRA {p['metrica']} <valor>»: "
                         f"arregla el script y vuelve a {'medir' if fuente == 'medicion' else 'sondear'}")
    ok = _cumple(v, p["espero"])
    if ok and fuente == "sonda":
        raise SystemExit(
            f"{c['id']}: la SONDA confirma ({p['metrica']} = {v}), y eso no cierra nada.\n"
            "  Una comprobación barata sirve para REFUTAR pronto, no para dar por bueno\n"
            "  un resultado sobre una muestra. Corre la medición de verdad:\n"
            f"    python3 ciclo.py medir {c['id']} -- <la carrera cara>")
    c["veredicto"] = {"cuando": _ahora(), "confirma": ok, "fuente": fuente,
                      "metrica": p["metrica"], "valor": v, "espero": p["espero"]}
    c["leccion"] = leccion.strip()
    c["fase"] = "cerrado"
    _bitacora(c, f"veredicto: {'CONFIRMA' if ok else 'REFUTA'} ({p['metrica']}={v})")
    _escribir(c)

    cont = RAIZ / "CONTINUIDAD.md"
    if cont.exists():
        with cont.open("a", encoding="utf-8") as fh:
            fh.write(f"\n- **[{_ahora()}] {c['id']} · "
                     f"{'CONFIRMA' if ok else 'REFUTA'}** ({fuente}) — {p['metrica']} = {v} "
                     f"(se predijo {p['espero']}). {c['leccion']}\n")
    print(f"{'✓ CONFIRMA' if ok else '✗ REFUTA'} · {c['id']} cerrado.\n"
          f"  {p['metrica']} = {v} vs predicho {p['espero']}\n"
          f"  lección → CONTINUIDAD.md: {c['leccion']}")
    return 0


def cmd_listar(_: list[str]) -> int:
    cs = _todos()
    if not cs:
        print(f"sin ciclos en {CICLOS}")
        return 0
    abiertos = [c for c in cs if c["fase"] != "cerrado"]
    print(f"{len(abiertos)} en curso de {len(cs)} · {CICLOS}\n")
    for c in cs:
        if c["fase"] == "cerrado":
            marca = "✓" if c["veredicto"]["confirma"] else "✗"
        else:
            marca = "·"
        pred = (f"{c['prediccion']['metrica']}{c['prediccion']['espero']}"
                if c.get("prediccion") else "—")
        print(f"{marca} {c['id']:4s} {c['fase']:9s} {pred:16s} {c['pregunta'][:44]}")
    return 0


def cmd_estado(_: list[str]) -> int:
    """¿Hay algo a medias? Es lo que una sesión nueva necesita saber en una línea."""
    cs = _todos()
    vivos = [c for c in cs if c["fase"] != "cerrado"]
    if not vivos:
        print(f"ningún ciclo en curso ({len(cs)} cerrados). "
              "Abre uno antes de tocar nada: ciclo.py abrir CN \"pregunta\"")
        return 0
    for c in vivos:
        sig = {"abierto": "revisar", "revisado": "predecir", "predicho": "sonda",
               "sondado": "medir (o veredicto, si la sonda ya refutó)",
               "medido": "veredicto"}[c["fase"]]
        print(f"‼ {c['id']} en fase «{c['fase']}» — {c['pregunta']}")
        if c.get("prediccion"):
            print(f"   predicho: {c['prediccion']['metrica']} {c['prediccion']['espero']} "
                  f"· porque {c['prediccion']['porque']}")
        print(f"   siguiente: python3 ciclo.py {sig} {c['id']} ...")
    return 0


def racha_sin_confirmar(ciclos: list[dict] | None = None) -> tuple[int, list[str]]:
    """Cuántos ciclos CERRADOS seguidos, contando desde el último, acabaron sin
    confirmar. Es el instrumento del vigilante de H6: un bucle autónomo que encadena
    refutaciones no está midiendo mal, está ESTANCADO —repite hipótesis o busca donde
    no hay— y a partir de un umbral debe parar y pedir revisión, no seguir gastando."""
    cs = ciclos if ciclos is not None else _todos()
    cerrados = [c for c in cs if c["fase"] == "cerrado" and c.get("veredicto")]
    cerrados.sort(key=lambda c: int(c["id"][1:]))
    racha: list[str] = []
    for c in reversed(cerrados):
        if c["veredicto"].get("confirma"):
            break
        racha.append(c["id"])
    return len(racha), list(reversed(racha))


def cmd_racha(args: list[str]) -> int:
    """`ciclo.py racha [umbral]` — código 1 si la racha alcanza el umbral (defecto 4)."""
    umbral = int(args[0]) if args else 4
    n, ids = racha_sin_confirmar()
    print(f"racha sin confirmar: {n}" + (f" ({', '.join(ids)})" if ids else ""))
    if n >= umbral:
        print(f"‼ estancamiento: {n} ciclos seguidos sin confirmar (umbral {umbral}). "
              "Un bucle autónomo debe PARAR aquí y pedir revisión humana.")
        return 1
    return 0


ORDENES = {"abrir": cmd_abrir, "revisar": cmd_revisar, "predecir": cmd_predecir,
           "sonda": cmd_sonda, "medir": cmd_medir, "veredicto": cmd_veredicto,
           "listar": cmd_listar, "estado": cmd_estado, "racha": cmd_racha}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ORDENES:
        print(__doc__)
        return 0
    return ORDENES[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
