"""cli.py — la puerta de entrada. `python3 -m genai.cli --ayuda`

El prompt de sistema es corto A PROPÓSITO. Se paga entero en CADA vuelta del bucle: a
1-3 tokens/s, mil tokens de instrucciones son entre seis minutos y media hora regalados
por tarea. Las instrucciones largas de otros arneses presuponen un prefill barato que
aquí no existe. Lo que no quepa en el sistema va donde el modelo pueda ir a buscarlo
cuando lo necesite: CLAUDE.md, los hologramas, `foco`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cerebro import cargar
from .herramientas import estandar
from .memoria import HERRAMIENTAS as HERRAMIENTAS_HOLO
from .nucleo import Politica, Sesion, preguntar_por_consola, turno

SISTEMA = """Eres Mekro-Genai, un agente de ingeniería que trabaja en el repositorio {raiz}.

Cada vuelta tuya cuesta segundos de cómputo local. Por eso:
- Antes de leer ficheros, orientate con `foco`, `simbolos` o `grep`.
- Manda todos los cambios de un fichero en UNA llamada a `editar`.
- Verifica con `bash` lo que afirmes. No des por hecho que algo funcionó.
- Cuando la tarea esté hecha y verificada, responde SIN llamar a ninguna herramienta.

Si algo te bloquea, dilo y para. Inventar un resultado cuesta más que no tenerlo."""


def construir(args) -> tuple[Sesion, object, Politica]:
    registro = estandar(incluir_peligrosas=args.modo != "plan")
    for h in HERRAMIENTAS_HOLO:
        if not (h.peligrosa and args.modo == "plan"):
            registro.registrar(h)
    guion = json.loads(Path(args.guion).read_text(encoding="utf-8")) if args.guion else []
    cerebro = cargar(args.cerebro, guion=guion) if args.cerebro == "eco" else cargar(args.cerebro)
    sesion = Sesion(sistema=SISTEMA.format(raiz=Path.cwd()), cerebro=cerebro)
    return sesion, registro, Politica(modo=args.modo)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("mekro-genai", description=__doc__)
    p.add_argument("peticion", nargs="*", help="el encargo, en lenguaje natural")
    p.add_argument("--cerebro", default="eco", help="eco | local_stream | local_packed")
    p.add_argument("--modo", default="preguntar", help="plan | preguntar | lista | todo")
    p.add_argument("--guion", help="JSON con el guion, solo para --cerebro eco")
    p.add_argument("--tope-vueltas", type=int, default=24)
    p.add_argument("--tope-tokens", type=int, default=6000)
    p.add_argument("--tope-segundos", type=int, default=1800)
    p.add_argument("--callado", action="store_true", help="sin traza por pantalla")
    a = p.parse_args(argv)

    if not a.peticion:
        p.print_help()
        return 0

    sesion, registro, politica = construir(a)
    r = turno(sesion, registro, politica, " ".join(a.peticion),
              tope_vueltas=a.tope_vueltas, tope_tokens=a.tope_tokens,
              tope_segundos=a.tope_segundos,
              preguntar=preguntar_por_consola if a.modo == "preguntar" else None,
              traza_por_pantalla=not a.callado)

    ruta = sesion.guardar()
    # Las cuatro cifras de META.md, siempre juntas y siempre al final.
    print(f"\n── {r.motivo} · {r.vueltas} vueltas · "
          f"{r.uso.tokens_salida} tok salida / {r.uso.tokens_entrada} entrada · "
          f"{r.uso.segundos:.1f} s · {r.intervenciones} intervenciones")
    print(f"   transcripción: {ruta}")
    return 0 if r.terminado_bien else 1


if __name__ == "__main__":
    sys.exit(main())
