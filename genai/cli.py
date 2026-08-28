"""genai — el arnés desde la terminal, contra el cerebro local y sin nube.

    genai tarea "arregla el bug de suma.py"     un encargo en el directorio actual
    genai tarea "..." --modo todo               sin preguntar (cuidado)
    genai tarea "..." --cerebro eco              el arnés sin modelo (pruebas)
    genai version                                qué hay instalado y qué cerebro ve
    genai cerebros                               tres caminos para traer un cerebro de nube
    genai proveedores [texto]                    207 proveedores BYOK + los 8 de fábrica
    genai mcp clientes                           Mekro-Genai como servidor MCP
    genai sesiones                               varios agentes en el mismo proyecto

El modo por defecto es «preguntar»: lo peligroso (escribir, borrar, ejecutar) se
consulta por consola antes de hacerse. Los topes existen porque cada vuelta cuesta
segundos de CPU de verdad: se enseñan al arrancar y se respetan.

**Nota de mantenimiento**: hasta 2026-08-28 esto y `genai/__main__.py` eran DOS CLIs que
habían divergido — `__main__.py` era la única que `pip install -e .` instalaba de
verdad como el comando `genai`, y todo lo de esta sesión (proveedores, cerebros, mcp,
google, copilot, sesiones) solo era alcanzable con `python3 -m genai.cli`, invisible
para cualquiera que instalara el paquete y usara `genai` a secas. Ahora `__main__.py`
es un reexport de este módulo: hay una sola CLI, y `python3 -m genai.cli mcp` se
conserva byte a byte porque Claude Code, Codex y Cursor ya lo tienen registrado como
comando de servidor MCP — cambiarlo rompería esas tres integraciones probadas con
cuenta real.
"""
from __future__ import annotations

import argparse
import json
import os
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


# ── `genai tarea` ────────────────────────────────────────────────────────────
def _registro_para(a) -> object:
    registro = estandar(incluir_peligrosas=a.modo != "plan",
                        web=not a.sin_web, malla=a.malla)
    # Herramientas de holograma (foco, holos, anotar): fuera en modo plan si son
    # peligrosas, igual que cualquier otra — un plan no debería poder anotar ni tocar
    # nada.
    for h in HERRAMIENTAS_HOLO:
        if not (h.peligrosa and a.modo == "plan"):
            registro.registrar(h)
    return registro


def cmd_tarea(a) -> int:
    os.environ["MG_CEREBRO"] = a.cerebro        # lo heredan los roles auxiliares
    # modo híbrido: el principal sigue siendo el de --cerebro; los auxiliares, otro.
    for rol, valor in (("subagente", a.cerebro_subagente or a.hibrido),
                       ("resumidor", a.cerebro_resumidor or a.hibrido)):
        if valor:
            os.environ[f"MG_CEREBRO_{rol.upper()}"] = valor
    if a.hibrido or a.cerebro_subagente or a.cerebro_resumidor:
        from .cerebro import para_rol
        print("modo híbrido · principal: " + a.cerebro + " · "
              + " · ".join(f"{r}: {para_rol(r, a.cerebro)}"
                           for r in ("subagente", "resumidor")))

    guion = json.loads(Path(a.guion).read_text(encoding="utf-8")) if a.guion else []
    cerebro = cargar(a.cerebro, guion=guion) if a.cerebro == "eco" else cargar(a.cerebro)

    ultima = Path(".genai") / "ultima.json"
    if a.continuar:
        # M5 brecha 2: la sesión anterior revive tal cual. El primer generar
        # re-prefilla la transcripción UNA vez; después, append-exacto normal.
        if not ultima.exists():
            print(f"no hay sesión que continuar en {ultima}: lanza una tarea primero.")
            return 2
        sesion = Sesion.de_dict(json.loads(ultima.read_text(encoding="utf-8")), cerebro)
        print(f"continuando la sesión {sesion.id} ({sesion.vueltas} vueltas previas, "
              f"{len(sesion.mensajes)} mensajes)")
    else:
        sesion = Sesion(sistema=SISTEMA.format(raiz=Path.cwd()), cerebro=cerebro)
    politica = Politica(modo=a.modo)
    print(f"cerebro {cerebro.nombre} · modo {a.modo} · topes: {a.vueltas} vueltas, "
          f"{a.tokens} tokens, {a.segundos} s")
    # streaming (M5.5): a 2,9 tok/s, ver avanzar el texto ES la experiencia. El
    # cerebro entrega deltas decodificables; aquí solo se pintan según llegan.
    if hasattr(cerebro, "al_token") and not a.sin_streaming:
        cerebro.al_token = lambda trozo: print(trozo, end="", flush=True)

    # MULTI-SESIÓN: se coge una sesión en exclusiva antes de tocar nada. El candado es
    # de sesión y no de proyecto a propósito — bloquear el proyecto convertiría esto en
    # un turno de espera, que es lo contrario de lo que se busca. Es un mecanismo
    # DISTINTO de --continuar: uno registra "cuál de varias sesiones está viva y quién
    # la tiene", el otro es "retoma lo último que hice aquí". Pueden usarse juntos o
    # por separado.
    from . import sesiones as _S
    reg = (next((x for x in _S.listar() if x["id"] == a.sesion), None) if a.sesion
           else _S.crear(a.encargo[:60]))
    if a.sesion and not reg:
        print(f"no existe la sesión «{a.sesion}». Mira `genai sesiones`.")
        return 2
    tomada, queja = _S.tomar(reg["id"])
    if not tomada:
        print(queja)
        return 2

    registro = _registro_para(a)

    def _correr(encargo: str, modo: str):
        return turno(sesion, registro, Politica(modo=modo), encargo,
                     tope_vueltas=a.vueltas, tope_tokens=a.tokens,
                     tope_segundos=a.segundos,
                     preguntar=preguntar_por_consola if modo == "preguntar" else None,
                     traza_por_pantalla=not a.callado)

    try:
        r = _correr(a.encargo, a.modo)
        if a.modo == "plan" and r.motivo == "fin":
            # plan conversacional (M5.5): proponer → aprobar → ejecutar, en la MISMA
            # sesión (el append-exacto hace barata la continuación).
            print(f"\n{r.texto}\n")
            try:
                resp = input("¿ejecutar el plan? [s/N] ").strip().lower()
            except EOFError:
                resp = ""
            if resp in ("s", "si", "sí", "y"):
                r = _correr("Adelante: ejecuta el plan que propusiste, paso a paso.",
                            "preguntar")
            else:
                print("plan no ejecutado; la sesión queda guardada por si cambias "
                      "de idea.")
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

    ultima.parent.mkdir(exist_ok=True)
    ultima.write_text(json.dumps(sesion.a_dict(), ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\n{r.texto}\n── {r.motivo} · {r.vueltas} vueltas · "
          f"{r.uso.tokens_salida} tok salida / {r.uso.tokens_entrada} entrada · "
          f"{r.uso.segundos:.1f} s · {r.intervenciones} intervenciones")
    print(f"   sesión guardada en {ultima} (retoma con --continuar)")
    return 0 if r.motivo == "fin" else 1


def cmd_version(_a) -> int:
    from .cerebro.local_gguf import GGUF
    print("Mekro-Genai — arnés agéntico para cerebros locales en CPU")
    ruta = Path(GGUF)
    if ruta.exists():
        print(f"cerebro: {ruta} ({ruta.stat().st_size / 2**30:.1f} GB)")
    else:
        print(f"cerebro: NO ENCONTRADO en {ruta}. Descarga el GGUF y ponlo ahí, o "
              "usa --cerebro eco para probar el arnés sin modelo.")
    return 0


# ── `genai proveedores` / `genai cerebros` ──────────────────────────────────
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
    print("\nEsto es BYOK (pagas por token). Para suscripción o MCP: `genai cerebros`.")
    return 0


def cmd_cerebros() -> int:
    """`genai cerebros` — el menú: tres caminos para traer un cerebro, decide tú cuál.

    Existe porque no son intercambiables ni igual de disponibles para todo proveedor:
    BYOK cubre cualquiera con clave; suscripción directa solo donde el proveedor
    sanciona de verdad usarla desde un tercero; MCP es al revés —tu cliente de
    suscripción usa las herramientas de Mekro-Genai, no un cerebro nuevo."""
    from .cerebro.nube import PROVEEDORES
    print("Tres caminos para traer un cerebro de nube. Ninguno es «el bueno»: decide "
          "según lo que ya tengas.\n")
    print("1. BYOK — clave de API, pagas por token")
    print(f"   {len(PROVEEDORES)} de fábrica (medidos) + 207 del catálogo de "
          f"models.dev, sin código nuevo.")
    print("   `genai proveedores [texto]` · --cerebro nube:<proveedor>/<modelo>\n")
    print("2. Suscripción directa — Mekro-Genai actúa como tu cerebro, con tu cuenta")
    print("   Solo donde el proveedor sanciona de verdad usarlo desde un tercero:")
    print("     genai copilot entrar   — GitHub Copilot (device flow de editor, "
          "documentado)")
    print("     genai google entrar    — Google (Code Assist exige licencia aparte "
          "de AI Pro/Ultra; medido, ver docs/nube.md)")
    print("   NO existe para OpenAI ni Anthropic: ChatGPT y Claude Pro/Max están "
          "ligados a su propio cliente oficial, no a extraerlos para otro programa.\n")
    print("3. MCP — tu cliente de suscripción usa las HERRAMIENTAS de Mekro-Genai")
    print("   El camino correcto para Claude Code, Codex, Cursor, y cualquier cliente "
          "MCP: el cerebro sigue siendo el suyo, se presta la caja de herramientas.")
    print("   `genai mcp clientes` · `genai mcp instalar <cliente>`")
    return 0


# ── `genai mcp` ──────────────────────────────────────────────────────────────
def cmd_mcp_clientes() -> int:
    """`genai mcp clientes` — qué se ha probado de verdad y qué no."""
    from .mcp_clientes import CLIENTES, detectado
    for clave, c in CLIENTES.items():
        marca = ("✓ instalado" if detectado(clave)
                 else ("no detectado" if c.get("binario") else "sin binario propio"))
        if c.get("verificado"):
            print(f"[{clave}] {c['nombre']}  ({marca})")
            print(f"    verificado: {c['verificado']}")
            print(f"    genai mcp instalar {clave}")
        else:
            print(f"[{clave}] {c['nombre']}  (SIN VERIFICAR desde aquí)")
            print(f"    {c['instrucciones']}")
        print()
    print("Cualquier otro cliente MCP: usa el fragmento JSON genérico —")
    print("`python3 -c \"from genai.mcp_clientes import json_generico as j; "
          "import json; print(json.dumps(j(), indent=2))\"`")
    return 0


def cmd_mcp_instalar(clave: str) -> int:
    if not clave:
        print("uso: genai mcp instalar <cliente>   (`genai mcp clientes` para ver "
              "cuáles)")
        return 2
    from .mcp_clientes import instalar
    ok, msg = instalar(clave)
    print(("✓ " if ok else "") + msg)
    if ok:
        print(f"\nQuitar con: genai mcp quitar {clave}")
    return 0 if ok else 1


def cmd_mcp_quitar(clave: str) -> int:
    if not clave:
        print("uso: genai mcp quitar <cliente>")
        return 2
    from .mcp_clientes import quitar
    ok, msg = quitar(clave)
    print(("✓ " if ok else "✗ ") + (msg or ("hecho" if ok else "falló")))
    return 0 if ok else 1


# ── `genai sesiones` ─────────────────────────────────────────────────────────
def cmd_sesiones(args: list[str]) -> int:
    """`genai sesiones [nueva|limpiar|compartir|servir] …` — varios agentes en un
    proyecto. Es el registro multi-sesión (`.genai/sesiones/`); no sustituye a
    `--continuar`, que retoma el último encargo de este directorio."""
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


# ── `genai google` / `genai copilot` ─────────────────────────────────────────
def cmd_google(args: list[str]) -> int:
    from . import google_cuenta as G
    sub = args[0] if args else "estado"
    if sub == "url":
        u, q = G.url_de_entrada()
        if q:
            print(q)
            return 1
        print("\n  1. Abre esto y entra con tu cuenta de Google:\n")
        print(f"  {u}\n")
        print("  2. Al aceptar, el navegador irá a localhost:8765 y dirá que NO")
        print("     PUEDE CONECTAR. Es lo esperado: no hay nada escuchando ahí.")
        print("     Copia la URL entera de la barra de direcciones.\n")
        print("  3. Y pégala aquí:")
        print("     genai google pegar \"http://localhost:8765/?code=...\"\n")
        return 0
    if sub == "pegar":
        ok, msg = G.completar(" ".join(args[1:]))
        print(("✓ " if ok else "✗ ") + msg)
        if ok:
            print("  Comprueba con: genai google")
        return 0 if ok else 1
    if sub == "entrar":
        ok, msg = G.entrar()
        print(("✓ " if ok else "✗ ") + msg)
        if ok:
            print("  Ya puedes: genai tarea \"...\" --cerebro nube:google")
            print("  Usa la cuota de tu cuenta, no una clave de API.")
        return 0 if ok else 1
    if sub == "proyecto":
        if len(args) < 2:
            print("uso: genai google proyecto <id-de-tu-proyecto-gcp>")
            return 2
        d = G._leer()
        d["proyecto_dado"] = args[1]
        d.pop("proyecto", None)
        G._guardar(d)
        print(f"proyecto fijado: {args[1]}")
        print(G.estado())
        return 0
    if sub == "salir":
        print(G.salir())
        return 0
    print(G.estado())
    return 0


def cmd_copilot(args: list[str]) -> int:
    from . import copilot as C
    sub = args[0] if args else "estado"
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


def cmd_mcp(args: list[str]) -> int:
    sub = args[0] if args else ""
    if sub == "clientes":
        return cmd_mcp_clientes()
    if sub == "instalar":
        return cmd_mcp_instalar(args[1] if len(args) > 1 else "")
    if sub == "quitar":
        return cmd_mcp_quitar(args[1] if len(args) > 1 else "")
    # Bare `genai mcp`: SERVIR, sin traza por stdio. Es lo que Claude Code, Codex y
    # Cursor ya tienen registrado (`python3 -m genai.cli mcp`, sin más argumentos) —
    # cambiar este defecto rompería las tres integraciones probadas con cuenta real.
    from .mcp import servir
    servir()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="genai", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden")

    t = sub.add_parser("tarea", help="un encargo agéntico en el directorio actual")
    t.add_argument("encargo")
    t.add_argument("--cerebro", default="gguf",
                   help="gguf (local, defecto) · eco (pruebas) · "
                        "nube:PROVEEDOR[/MODELO] con TU clave (docs/nube.md)")
    t.add_argument("--modo", default="preguntar",
                   choices=("plan", "preguntar", "lista", "todo"))
    t.add_argument("--vueltas", type=int, default=16)
    t.add_argument("--tokens", type=int, default=4000)
    t.add_argument("--segundos", type=int, default=3600)
    t.add_argument("--continuar", action="store_true",
                   help="retomar la última sesión de este directorio (.genai/ultima.json)")
    t.add_argument("--cerebro-subagente", default="",
                   help="modo híbrido: cerebro para los subagentes de exploración")
    t.add_argument("--cerebro-resumidor", default="",
                   help="modo híbrido: cerebro para el resumen del renacimiento")
    t.add_argument("--hibrido", default="",
                   help="atajo: PROVEEDOR de nube para TODOS los roles auxiliares, "
                        "conservando el cerebro principal local (ej.: --hibrido nube:gemini)")
    t.add_argument("--malla", action="store_true",
                   help="modo Mesh: permite delegar tareas a pares (docs/malla.md)")
    t.add_argument("--sin-streaming", action="store_true",
                   help="no pintar el texto según se genera")
    t.add_argument("--sin-web", action="store_true",
                   help="quitar el acceso a la web (viene encendido; nunca alcanza "
                        "esta máquina ni esta red)")
    t.add_argument("--sesion", default="",
                   help="id de una sesión existente (`genai sesiones`); si no se da, "
                        "se abre una nueva. Varios agentes pueden trabajar a la vez en "
                        "el mismo proyecto, cada uno con la suya")
    t.add_argument("--guion", default="",
                   help="JSON con el guion, solo para --cerebro eco")
    t.add_argument("--callado", action="store_true", help="sin traza por pantalla")

    sub.add_parser("version", help="qué hay instalado y qué cerebro ve")

    m = sub.add_parser("malla", help="modo Mesh: donar cómputo o ver la cuenta")
    m.add_argument("resto", nargs=argparse.REMAINDER,
                   help="servir [--puerto N --hilos N] | cuenta")

    pr = sub.add_parser("proveedores", help="207 proveedores BYOK + los 8 de fábrica")
    pr.add_argument("patron", nargs="*", default=[])

    sub.add_parser("cerebros", help="tres caminos para traer un cerebro de nube")

    mc = sub.add_parser("mcp", help="Mekro-Genai como servidor MCP (o gestionar clientes)")
    mc.add_argument("resto", nargs=argparse.REMAINDER)

    se = sub.add_parser("sesiones", help="varios agentes en el mismo proyecto")
    se.add_argument("resto", nargs=argparse.REMAINDER)

    go = sub.add_parser("google", help="suscripción directa de Google (Code Assist)")
    go.add_argument("resto", nargs=argparse.REMAINDER)

    co = sub.add_parser("copilot", help="suscripción directa de GitHub Copilot")
    co.add_argument("resto", nargs=argparse.REMAINDER)

    a = ap.parse_args(argv)
    if a.orden == "tarea":
        return cmd_tarea(a)
    if a.orden == "version":
        return cmd_version(a)
    if a.orden == "malla":
        from .malla import main as malla_main
        return malla_main(a.resto)
    if a.orden == "proveedores":
        return cmd_proveedores(" ".join(a.patron))
    if a.orden == "cerebros":
        return cmd_cerebros()
    if a.orden == "mcp":
        return cmd_mcp(a.resto)
    if a.orden == "sesiones":
        return cmd_sesiones(a.resto)
    if a.orden == "google":
        return cmd_google(a.resto)
    if a.orden == "copilot":
        return cmd_copilot(a.resto)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
