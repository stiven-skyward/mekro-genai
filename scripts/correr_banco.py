#!/usr/bin/env python3
"""correr_banco.py — corre el banco y deja un registro con las cuatro cifras de META.md.

Reglas que este script impone y que no dependen de la buena fe de nadie:

- **Cada tarea parte de una copia limpia** de su `semilla/` en un temporal. Si una carrera
  dejara restos, la siguiente mediría otra cosa.
- **`verificar_intacto` se comprueba por hash.** La forma más fácil de que «la prueba pase»
  es borrar la prueba, y un modelo bajo presión de presupuesto encuentra ese atajo. Si el
  fichero cambió, la tarea NO puntúa aunque el verificador devuelva 0.
- **El modo de permiso por defecto es `lista`**, no `preguntar`: una carrera corre sola.
- **Se registran las cuatro cifras SIEMPRE**, también cuando la tarea falla. Una carrera a
  medias sin registro es una carrera que habrá que repetir.

Imprime el contrato de `ciclo.py` (`CIFRA <nombre> <valor>`) para poder medirse dentro de
un ciclo de investigación sin acoplar nada.

    python3 scripts/correr_banco.py --nivel n0 --cerebro eco
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from genai.cerebro import cargar                      # noqa: E402
from genai.herramientas import estandar               # noqa: E402
from genai.memoria import HERRAMIENTAS as HOLO        # noqa: E402
from genai.nucleo import Politica, Sesion, turno      # noqa: E402

SISTEMA = """Eres Mekro-Genai, un agente de ingeniería. Trabajas en el directorio actual.

Cada vuelta tuya cuesta segundos de cómputo local. Por eso:
- Antes de leer ficheros, orientate con `grep` o `simbolos`.
- Manda todos los cambios de un fichero en UNA llamada a `editar`.
- Verifica con `bash` lo que afirmes.
- El intérprete es `python3`; `python` a secas NO existe en esta máquina.
- Nada de `cd`: todas las rutas son relativas al directorio actual.
- Cuando la tarea esté hecha y verificada, responde SIN llamar a ninguna herramienta."""


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "AUSENTE"


def correr_tarea(dir_tarea: Path, nombre_cerebro: str, modo: str,
                 topes: dict, callado: bool, contexto: int = 0,
                 adoptados: bool = False, sin_pensar: bool = False) -> dict:
    tarea = json.loads((dir_tarea / "tarea.json").read_text(encoding="utf-8"))
    if adoptados:
        # M3: los mandos que el ciclo autónomo adoptó mandan sobre los de la línea
        # de comando. Quién los adoptó y por qué: registros/adopciones.json
        import adopcion
        mand = adopcion.vigentes().get(f"{dir_tarea.parent.name}/{tarea['id']}")
        if mand:
            topes = {**topes, **mand}
            print(f"   (mandos adoptados: {mand})")
    # Mundo reproducible, no observación filtrada (C31): los mtime de la copia eran la
    # hora de la carrera, un `ls -la` los enseñaba, y a temperatura 0 ese ruido bastó
    # para divergir el guion entre carreras idénticas. Fecha fija → observación fija.
    # La caja va ANIDADA un nivel para que hasta el «..» de un ls -la sea nuestro y
    # lleve la misma fecha, no el /tmp vivo de la máquina.
    raiz_tmp = Path(tempfile.mkdtemp(prefix=f"banco-{tarea['id']}-"))
    trabajo = raiz_tmp / "caja"
    shutil.copytree(dir_tarea / "semilla", trabajo)
    epoca = 1767225600  # 2026-01-01 00:00 UTC
    for p in [raiz_tmp, trabajo, *trabajo.rglob("*")]:
        os.utime(p, (epoca, epoca))

    intactos = {f: _hash(trabajo / f) for f in tarea.get("verificar_intacto", [])}

    if nombre_cerebro == "eco":
        cerebro = cargar("eco", guion=tarea.get("guion", []))
    else:
        # --contexto: encoger la ventana es la forma honesta de estresar los
        # mecanismos relativos al contexto (C71: engordar la tarea no sirve, el
        # modelo la adelgaza; encoger la ventana muerde haga lo que haga)
        cerebro = (cargar(nombre_cerebro, contexto_max=contexto)
                   if contexto else cargar(nombre_cerebro))

    if sin_pensar and hasattr(cerebro, "pensar"):
        cerebro.pensar = False
    os.environ["MG_CEREBRO"] = nombre_cerebro    # lo hereda el subagente
    registro = estandar()
    for h in HOLO:
        registro.registrar(h)

    sesion = Sesion(sistema=SISTEMA, cerebro=cerebro)
    politica = Politica(modo=modo)

    antes = os.getcwd()
    os.chdir(trabajo)
    t0 = time.time()
    try:
        r = turno(sesion, registro, politica, tarea["encargo"],
                  traza_por_pantalla=not callado, **topes)
    finally:
        os.chdir(antes)

    v = subprocess.run(tarea["verificar"], shell=True, cwd=trabajo,
                       capture_output=True, text=True, timeout=300)
    paso = v.returncode == 0

    tocados = [f for f, h in intactos.items() if _hash(trabajo / f) != h]
    if tocados and paso:
        paso = False
        motivo_extra = f"tocó ficheros que no debía: {tocados}"
    else:
        motivo_extra = ""

    return {"id": tarea["id"], "paso": paso, "motivo": r.motivo,
            "motivo_extra": motivo_extra,
            "vueltas": r.vueltas, "intervenciones": r.intervenciones,
            "tokens_salida": r.uso.tokens_salida,
            "tokens_entrada": r.uso.tokens_entrada,
            "segundos": round(time.time() - t0, 1),
            "verificador": v.stdout.strip()[-300:] or v.stderr.strip()[-300:],
            "trabajo": str(trabajo)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--nivel", default="n0")
    p.add_argument("--tarea", default="",
                   help="correr solo esta tarea del nivel; las medidas de un ciclo solo "
                        "son comparables si abarcan las mismas tareas")
    p.add_argument("--cerebro", default="eco",
                   help="eco · gguf · nube:PROVEEDOR[/MODELO] (nunca cuenta como local)")
    p.add_argument("--modo", default="lista")
    p.add_argument("--etiqueta", default="")
    p.add_argument("--tope-vueltas", type=int, default=24)
    p.add_argument("--tope-tokens", type=int, default=6000)
    p.add_argument("--tope-segundos", type=int, default=1800)
    p.add_argument("--pensar-vueltas", type=int, default=0,
                   help="think solo en las N primeras vueltas (0 = siempre)")
    p.add_argument("--sin-pensar", action="store_true",
                   help="apagar el razonamiento <think> del cerebro en cada vuelta (M3)")
    p.add_argument("--adoptados", action="store_true",
                   help="aplicar los mandos adoptados por el ciclo (M3)")
    p.add_argument("--contexto", type=int, default=0,
                   help="encoge contexto_max del cerebro (0 = el suyo de fábrica)")
    p.add_argument("--exigir-todo", action="store_true",
                   help="código distinto de 0 si alguna tarea falla")
    p.add_argument("--callado", action="store_true")
    a = p.parse_args()

    tareas = sorted(d for d in (RAIZ / "banco" / a.nivel).iterdir()
                    if (d / "tarea.json").exists()
                    and (not a.tarea or d.name == a.tarea))
    if not tareas:
        raise SystemExit(f"sin tareas en banco/{a.nivel}")

    topes = {"tope_vueltas": a.tope_vueltas, "tope_tokens": a.tope_tokens,
             "tope_segundos": a.tope_segundos}
    if a.pensar_vueltas:
        topes["pensar_vueltas"] = a.pensar_vueltas
    print(f"== banco {a.nivel} · cerebro {a.cerebro} · modo {a.modo} · "
          f"{len(tareas)} tareas ==\n")

    filas = []
    for d in tareas:
        print(f"── {d.name}")
        filas.append(correr_tarea(d, a.cerebro, a.modo, topes, a.callado, a.contexto,
                                  a.adoptados, a.sin_pensar))
        if a.adoptados and not filas[-1]["paso"]:
            import adopcion
            if adopcion.revertir_si_fallo(f"{a.nivel}/{filas[-1]['id']}", 0.0):
                print("   ‼ adopción REVERTIDA: la tarea falló con los mandos adoptados")
        f = filas[-1]
        print(f"   {'✓ PASA' if f['paso'] else '✗ FALLA'} · {f['motivo']}"
              + (f" · {f['motivo_extra']}" if f["motivo_extra"] else "")
              + f" · {f['vueltas']} vueltas · {f['tokens_salida']} tok · "
                f"{f['segundos']} s · {f['intervenciones']} interv.\n")

    n = len(filas)
    pasan = sum(1 for f in filas if f["paso"])
    tok = sum(f["tokens_salida"] for f in filas) / n
    seg = sum(f["segundos"] for f in filas) / n
    interv = sum(f["intervenciones"] for f in filas)

    sello = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    etiqueta = a.etiqueta or f"{a.nivel}-{a.cerebro}"
    # MG_REGISTROS existe para que las pruebas frías del lazo no siembren humo entre
    # los registros de verdad, que no se borran nunca.
    dir_reg = Path(os.environ.get("MG_REGISTROS", RAIZ / "registros"))
    dir_reg.mkdir(parents=True, exist_ok=True)
    reg = dir_reg / f"{sello}_{etiqueta}.json"
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(json.dumps(
        {"cuando": sello, "nivel": a.nivel, "cerebro": a.cerebro, "modo": a.modo,
         "topes": topes, "tareas": filas,
         "resumen": {"tareas_pct": round(100 * pasan / n, 1),
                     "tokens_media": round(tok, 1),
                     "segundos_media": round(seg, 1),
                     "intervenciones": interv}},
        indent=2, ensure_ascii=False), encoding="utf-8")

    # Las cuatro cifras de META.md, juntas, y en el contrato que entiende ciclo.py.
    print("═" * 66)
    print(f"CIFRA tareas_pct {100 * pasan / n:.1f}")
    print(f"CIFRA tokens_media {tok:.1f}")
    print(f"CIFRA segundos_media {seg:.1f}")
    print(f"CIFRA intervenciones {interv}")
    print(f"\n{pasan}/{n} tareas · registro → {reg.relative_to(RAIZ)}")
    return 1 if (a.exigir_todo and pasan < n) else 0


if __name__ == "__main__":
    raise SystemExit(main())
