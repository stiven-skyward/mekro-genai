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
    registro = estandar(incluir_peligrosas=args.modo != "plan",
                        web=not args.sin_web)
    for h in HERRAMIENTAS_HOLO:
        if not (h.peligrosa and args.modo == "plan"):
            registro.registrar(h)
    guion = json.loads(Path(args.guion).read_text(encoding="utf-8")) if args.guion else []
    cerebro = cargar(args.cerebro, guion=guion) if args.cerebro == "eco" else cargar(args.cerebro)
    sesion = Sesion(sistema=SISTEMA.format(raiz=Path.cwd()), cerebro=cerebro)
    return sesion, registro, Politica(modo=args.modo)


def cmd_proveedores(patron: str = "") -> int:
    """`genai proveedores [texto]` — qué se puede enchufar.

    Los de fábrica son los ocho que tienen medición detrás; el resto sale del catálogo
    de models.dev, cacheado en disco para que esto funcione sin red."""
    from .catalogo import buscar, descargar
    from .cerebro.nube import PROVEEDORES
    cat, queja = descargar()
    if queja:
        print(f"⚠ {queja}")
    print(f"De fábrica ({len(PROVEEDORES)}, medidos): {', '.join(sorted(PROVEEDORES))}")
    if not cat:
        return 1
    filas = buscar(patron, tope=40)
    total = sum(len(v.get("models") or {}) for v in cat.values())
    if not filas:
        print(f"nada casa con «{patron}» entre {len(cat)} proveedores y {total} modelos")
        return 1
    print(f"\nDel catálogo ({len(cat)} proveedores, {total} modelos)"
          + (f" · «{patron}»" if patron else ", primeros 40") + ":")
    for pid, mid, _ in filas:
        print(f"  --cerebro nube:{pid}/{mid}")
    print("\nLa clave va en ~/.config/genai/claves.json, con el nombre del proveedor.")
    return 0


def cmd_sesiones(args: list[str]) -> int:
    """`genai sesiones [nueva|limpiar|servir] …` — varios agentes en un proyecto."""
    from . import sesiones as S
    sub = args[0] if args else "listar"
    if sub == "nueva":
        s = S.crear(" ".join(args[1:]))
        print(f"{s['id']}  {s['titulo']}")
        return 0
    if sub == "limpiar":
        print(f"{S.limpiar()} sesión(es) rancia(s) recogida(s)")
        return 0
    if sub == "compartir":
        if len(args) < 2:
            print("uso: genai sesiones compartir <id> [fichero.html]")
            return 2
        from .compartir import exportar
        from .servidor import _transcripcion
        ident = args[1]
        tr = _transcripcion(ident)
        if not tr.get("mensajes"):
            print(f"la sesión «{ident}» no tiene transcripción guardada todavía")
            return 1
        s = next((x for x in S.listar() if x["id"] == ident), {})
        destino = args[2] if len(args) > 2 else f"sesion-{ident}.html"
        p, cuenta = exportar(tr, destino, s.get("titulo", ""))
        print(f"→ {p}")
        total = sum(cuenta.values())
        if total:
            print(f"⚠ tachados {total} posibles secretos: "
                  + ", ".join(f"{n} ×{v}" for n, v in sorted(cuenta.items())))
        print("  El tachado va por patrones conocidos y NO puede cazarlo todo. "
              "Léelo antes de mandarlo.")
        return 0
    if sub == "servir":
        from .servidor import PUERTO, servir
        servir(int(args[1]) if len(args) > 1 else PUERTO)
        return 0
    todas = S.listar()
    if not todas:
        print("no hay sesiones. `genai sesiones nueva \"lo que vas a hacer\"`")
        return 0
    print(f"{'id':14}{'estado':10}{'vueltas':>8}  título")
    for s in todas:
        est = "activa" if s["viva"] else ("rancia" if s["rancia"] else "libre")
        print(f"{s['id']:14}{est:10}{s.get('vueltas', 0):8}  {s['titulo']}")
    ch = S.conflictos()
    if ch:
        # El candado es de sesión, no de ficheros. Callarse esto sería prometer un
        # aislamiento que no existe.
        print("\n⚠ mismo fichero tocado por varias sesiones vivas:")
        for f, ids in ch:
            print(f"    {f}  ←  {', '.join(ids)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("mekro-genai", description=__doc__)
    p.add_argument("peticion", nargs="*", help="el encargo, en lenguaje natural")
    p.add_argument("--cerebro", default="eco", help="eco | local_stream | local_packed")
    p.add_argument("--modo", default="preguntar", help="plan | preguntar | lista | todo")
    p.add_argument("--guion", help="JSON con el guion, solo para --cerebro eco")
    p.add_argument("--tope-vueltas", type=int, default=24)
    p.add_argument("--tope-tokens", type=int, default=6000)
    p.add_argument("--tope-segundos", type=int, default=1800)
    p.add_argument("--sin-web", action="store_true",
                   help="quitar el acceso a la web (viene encendido; nunca alcanza "
                        "esta máquina ni esta red)")
    p.add_argument("--sesion", default="",
                   help="id de una sesión existente (`genai sesiones`); si no se da, "
                        "se abre una nueva. Varios agentes pueden trabajar a la vez en "
                        "el mismo proyecto, cada uno con la suya")
    p.add_argument("--callado", action="store_true", help="sin traza por pantalla")
    a = p.parse_args(argv)

    if not a.peticion:
        p.print_help()
        return 0

    # `genai proveedores [texto]` — qué se puede enchufar, del catálogo.
    if a.peticion[0] == "proveedores":
        return cmd_proveedores(" ".join(a.peticion[1:]))
    if a.peticion[0] == "google":
        from . import google_cuenta as G
        sub = a.peticion[1] if len(a.peticion) > 1 else "estado"
        if sub == "entrar":
            ok, msg = G.entrar()
            print(("✓ " if ok else "✗ ") + msg)
            if ok:
                print("  Ya puedes: genai tarea \"...\" --cerebro nube:google")
                print("  Usa la cuota de tu cuenta, no una clave de API.")
            return 0 if ok else 1
        if sub == "salir":
            print(G.salir())
            return 0
        print(G.estado())
        return 0
    if a.peticion[0] == "copilot":
        from . import copilot as C
        sub = a.peticion[1] if len(a.peticion) > 1 else "estado"
        if sub == "entrar":
            ok, msg = C.entrar()
            print(("✓ " if ok else "✗ ") + msg)
            if ok:
                print("  Ya puedes: genai tarea \"...\" --cerebro nube:copilot")
            return 0 if ok else 1
        if sub == "salir":
            print(C.salir())
            return 0
        print(C.estado())
        return 0
    if a.peticion[0] == "sesiones":
        return cmd_sesiones(a.peticion[1:])

    # MULTI-SESIÓN: se coge una sesión en exclusiva antes de tocar nada. El candado es
    # de sesión y no de proyecto a propósito — bloquear el proyecto convertiría esto en
    # un turno de espera, que es lo contrario de lo que se busca.
    from . import sesiones as _S
    reg = (next((x for x in _S.listar() if x["id"] == a.sesion), None) if a.sesion
           else _S.crear(" ".join(a.peticion)[:60]))
    if a.sesion and not reg:
        print(f"no existe la sesión «{a.sesion}». Mira `genai sesiones`.")
        return 2
    tomada, queja = _S.tomar(reg["id"])
    if not tomada:
        print(queja)
        return 2

    sesion, registro, politica = construir(a)
    try:
        r = turno(sesion, registro, politica, " ".join(a.peticion),
                  tope_vueltas=a.tope_vueltas, tope_tokens=a.tope_tokens,
                  tope_segundos=a.tope_segundos,
                  preguntar=preguntar_por_consola if a.modo == "preguntar" else None,
                  traza_por_pantalla=not a.callado)
    finally:
        # Los ficheros tocados se anotan aunque la carrera muera: sirven para avisar
        # de que dos sesiones vivas están editando lo mismo.
        _S.latir(reg["id"], vueltas=sesion.vueltas,
                 tocados=sorted({d for m in sesion.mensajes
                                 for ll in m.llamadas
                                 for d in [ll.argumentos.get("ruta")] if d}))
        _S.soltar(reg["id"])

    # Una caché explícita de nube que sobrevive al turno se sigue cobrando por horas.
    if hasattr(sesion.cerebro, "cerrar"):
        sesion.cerebro.cerrar()

    ruta = sesion.guardar()
    # Las cuatro cifras de META.md, siempre juntas y siempre al final.
    print(f"\n── {r.motivo} · {r.vueltas} vueltas · "
          f"{r.uso.tokens_salida} tok salida / {r.uso.tokens_entrada} entrada · "
          f"{r.uso.segundos:.1f} s · {r.intervenciones} intervenciones")
    print(f"   transcripción: {ruta}")
    return 0 if r.terminado_bien else 1


if __name__ == "__main__":
    sys.exit(main())
