"""genai — el arnés desde la terminal, contra el cerebro local y sin nube.

    genai tarea "arregla el bug de suma.py"     un encargo en el directorio actual
    genai tarea "..." --modo todo               sin preguntar (cuidado)
    genai tarea "..." --cerebro eco              el arnés sin modelo (pruebas)
    genai chat                                   conversación continua (Claude Code/OpenCode)
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
import re
import threading
from pathlib import Path

try:
    import readline  # noqa: F401 — su sola importación activa historial y edición
                     # (flechas, Ctrl-R) en todo `input()` de este proceso, en Linux
                     # y macOS. No existe en el Python de base de Windows, y aquí eso
                     # no importa: el propio README exige WSL para este arnés.
except ImportError:
    pass

from . import tui
from .cerebro import cargar
from .herramientas import estandar
from .memoria import HERRAMIENTAS as HERRAMIENTAS_HOLO
from .nucleo import MODOS, Politica, Sesion, preguntar_por_consola, turno

SISTEMA = """Eres Mekro-Genai, un agente de ingeniería que trabaja en el repositorio {raiz}.

Cada vuelta tuya cuesta segundos de cómputo local. Por eso:
- Antes de leer ficheros, orientate con `foco`, `simbolos` o `grep`.
- Manda todos los cambios de un fichero en UNA llamada a `editar`.
- Verifica con `bash` lo que afirmes. No des por hecho que algo funcionó.
- Cuando la tarea esté hecha y verificada, responde SIN llamar a ninguna herramienta.

Si algo te bloquea, dilo y para. Inventar un resultado cuesta más que no tenerlo."""


_MENCION = re.compile(r"(?<!\S)@(\S+)")
_TOPE_MENCION = 200_000


def _expandir_menciones(texto: str) -> tuple[str, list[str]]:
    """`@ruta/al/fichero` en un encargo mete el contenido directamente en el mensaje
    —una vuelta menos que pedirle al cerebro que llame a `leer`, espere el resultado
    y recién entonces conteste. Con un cerebro que cuesta minutos por vuelta esto no
    es comodidad: es la diferencia entre uno y dos turnos completos de CPU real."""
    adjuntos: list[str] = []
    rutas: list[str] = []

    def _sub(m: re.Match) -> str:
        ruta = Path(m.group(1))
        if not ruta.is_file():
            return m.group(0)
        try:
            contenido = ruta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return m.group(0)
        if len(contenido) > _TOPE_MENCION:
            recortado = len(contenido) - _TOPE_MENCION
            contenido = (contenido[:_TOPE_MENCION] +
                        f"\n\n[… {recortado} caracteres omitidos: demasiado grande "
                        "para adjuntar entero; pide el resto con `leer` acotado …]")
        adjuntos.append(f"--- {ruta} ---\n{contenido}")
        rutas.append(str(ruta))
        return str(ruta)

    resto = _MENCION.sub(_sub, texto)
    if not adjuntos:
        return texto, []
    return resto + "\n\n" + "\n\n".join(adjuntos), rutas


def _elegir_cerebro_guiado() -> str | None:
    """El menú que `/modelo` sin argumento abre: un listado numerado en vez de
    exigir de memoria el nombre exacto («nube:proveedor/modelo»). Por cada
    proveedor BYOK se enseña si YA tiene clave puesta —para que la elección sea
    informada, no una apuesta—, y las dos suscripciones traen su propio estado
    real (`copilot.estado()`/`google_cuenta.estado()`), no un genérico "disponible".
    Devuelve el nombre a pasarle a `cargar()`, o `None` si se cancela."""
    from . import copilot, google_cuenta
    from .cerebro.nube import PROVEEDORES, claves

    cl = claves()
    opciones: dict[str, str] = {}
    filas: list[str] = [tui.negrita("local — sin nube, sin coste, sin clave")]
    filas += tui.tabla([("1", "gguf (por defecto) · Qwen3.8-27B en CPU")])
    opciones["1"] = "gguf"

    filas += ["", tui.negrita("BYOK — tu clave de API, pagas por token")]
    items = []
    n = 2
    for prov in sorted(PROVEEDORES):
        configurado = bool(cl.get(prov, {}).get("clave"))
        marca = tui.exito("configurado") if configurado else tui.atenuado("sin clave")
        items.append((str(n), f"{prov}  ({marca})"))
        opciones[str(n)] = f"nube:{prov}"
        n += 1
    filas += tui.tabla(items)

    def _corto(estado: str, tope: int = 35) -> str:
        # `estado()` puede traer un error de la API entero (Google, con licencia de
        # Code Assist denegada, devuelve el JSON del 403 completo) — bueno para un
        # log, ilegible metido en una fila de menú.
        return estado if len(estado) <= tope else estado[:tope].rstrip() + "…"

    filas += ["", tui.negrita("suscripción — Mekro-Genai usa tu cuenta, no una clave")]
    filas += tui.tabla([
        (str(n), f"copilot (GitHub) · {_corto(copilot.estado())}"),
        (str(n + 1), f"google (Code Assist) · {_corto(google_cuenta.estado())}"),
    ])
    opciones[str(n)], opciones[str(n + 1)] = "nube:copilot", "nube:google"
    n += 2

    filas += ["", tui.negrita("otro")]
    filas += tui.tabla([(str(n), "buscar entre 207 proveedores, o escribir uno a mano")])
    opciones[str(n)] = "_personalizado"
    filas.append("")
    filas.append("0  cancelar")

    print(tui.caja(filas, titulo="elige un cerebro"))
    print(tui.atenuado("  (Cursor/Claude Code/Codex usan tu MCP, no un cerebro de "
                       "/modelo: `genai mcp clientes`)"))
    try:
        eleccion = input(tui.negrita("  → ")).strip()
    except EOFError:
        return None
    if eleccion in ("", "0"):
        return None
    if eleccion not in opciones:
        print(tui.aviso(f"  «{eleccion}» no es ninguna de las opciones de la lista"))
        return None
    nombre = opciones[eleccion]
    if nombre == "_personalizado":
        print(tui.atenuado("  `genai proveedores <texto>` (en otra terminal) busca "
                           "entre los 207; aquí escribe el nombre ya elegido."))
        try:
            nombre = input(tui.negrita(
                "  nombre (ej.: nube:groq/llama-3.3-70b-versatile): ")).strip()
        except EOFError:
            return None
    return nombre or None


def _info_tras_cambio(nombre_pedido: str) -> None:
    """Lo que el usuario pidió explícitamente: no solo cambiar de cerebro, sino
    enseñar qué más hay configurable para el camino elegido — la malla para el
    local, nada de más para BYOK (ya se ve el coste solo, por turno)."""
    if nombre_pedido == "gguf":
        print(tui.atenuado(
            "  local: sin coste, sin red. Modo Mesh disponible si arrancaste con "
            "--malla (`genai malla servir` en otra terminal dona cómputo; "
            "`genai malla cuenta` ve el saldo) — ver docs/malla.md."))


def _con_latido(cerebro: object) -> None:
    """Envuelve `cerebro.generar` para que el hueco de silencio ANTES del primer
    token —cargar el modelo, prefillar el contexto, un `<think>` de varios minutos—
    lleve un latido en pantalla en vez de parecer un proceso colgado. Se envuelve
    aquí, en la CLI, para no meter hilos ni relojes dentro de `bucle.py`: éste sigue
    sin saber nada de latidos, solo llama a `cerebro.generar` como siempre."""
    generar_real = cerebro.generar

    def generar_con_latido(*args, **kw):
        latido = tui.Heartbeat()
        al_token_previo = getattr(cerebro, "al_token", None)
        if al_token_previo:
            primero = threading.Event()

            def _con_parada(trozo, _prev=al_token_previo, _lat=latido, _p=primero):
                if not _p.is_set():
                    _p.set()
                    _lat.parar()
                _prev(trozo)
            cerebro.al_token = _con_parada
        latido.iniciar()
        try:
            return generar_real(*args, **kw)
        finally:
            latido.parar()
            if al_token_previo:
                cerebro.al_token = al_token_previo

    cerebro.generar = generar_con_latido


# ── lo común entre `genai tarea` y `genai chat` ──────────────────────────────
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


def _preparar_sesion(a, titulo: str):
    """Cerebro, registro multi-sesión y candado — lo que `tarea` y `chat` necesitan
    por igual antes de poder correr un `turno()`. Devuelve `None` si algo lo impide
    (el porqué ya se imprimió); si no, `(cerebro, sesion, reg, registro, ultima, _S)`.
    """
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

    # MULTI-SESIÓN: se resuelve el registro ANTES de construir la `Sesion`, para
    # poder atarle el MISMO id. Antes no se hacía así, y `Sesion` generaba su propio
    # UUID al azar: `genai sesiones compartir` y `/transcripcion` buscaban el fichero
    # por el id del registro y el fichero se guardaba con el id de la sesión — dos
    # identidades para la misma cosa que por construcción no coincidían nunca. El
    # candado es de SESIÓN y no de proyecto a propósito: bloquear el proyecto
    # convertiría esto en un turno de espera, que es lo contrario de lo que se busca.
    from . import sesiones as _S
    reg = (next((x for x in _S.listar() if x["id"] == a.sesion), None) if a.sesion
           else (None if a.continuar else _S.crear(titulo[:60])))
    if a.sesion and not reg:
        print(f"no existe la sesión «{a.sesion}». Mira `genai sesiones`.")
        return None

    ultima = Path(".genai") / "ultima.json"
    if a.continuar:
        # M5 brecha 2: la sesión anterior revive tal cual. El primer generar
        # re-prefilla la transcripción UNA vez; después, append-exacto normal.
        if not ultima.exists():
            print(f"no hay sesión que continuar en {ultima}: lanza una tarea primero.")
            return None
        sesion = Sesion.de_dict(json.loads(ultima.read_text(encoding="utf-8")), cerebro)
        print(f"continuando la sesión {sesion.id} ({sesion.vueltas} vueltas previas, "
              f"{len(sesion.mensajes)} mensajes)")
        if reg is None:
            # --continuar sin --sesion no pasaba antes por el registro multi-sesión:
            # se le da una entrada nueva para que el candado y el listado funcionen,
            # aunque su id no coincida con `sesion.id` —son dos mecanismos de resumen
            # distintos (uno por directorio, otro por id explícito) y este caso
            # concreto no se intenta unificar del todo aquí.
            reg = _S.crear(f"(continuada) {sesion.id}"[:60])
    else:
        sesion = Sesion(sistema=SISTEMA.format(raiz=Path.cwd()), cerebro=cerebro,
                        id=reg["id"])

    # streaming (M5.5): a 2,9 tok/s, ver avanzar el texto ES la experiencia. El
    # cerebro entrega deltas decodificables; aquí solo se pintan según llegan.
    if hasattr(cerebro, "al_token") and not a.sin_streaming:
        cerebro.al_token = lambda trozo: print(trozo, end="", flush=True)

    if not a.callado:
        _con_latido(cerebro)

    tomada, queja = _S.tomar(reg["id"])
    if not tomada:
        print(queja)
        return None

    return cerebro, sesion, reg, _registro_para(a), ultima, _S


def _guardar_sesion(sesion: Sesion, ultima: Path) -> None:
    ultima.parent.mkdir(exist_ok=True)
    ultima.write_text(json.dumps(sesion.a_dict(), ensure_ascii=False, indent=1),
                      encoding="utf-8")


def _mostrar_costo(cerebro: object, r) -> None:
    """Solo imprime algo si `cerebro.precio` existe: BYOK con un modelo que el
    catálogo cataloga. Local y suscripción se callan — no tienen coste por token
    que enseñar, y este proyecto no aproxima donde no puede medir."""
    precio = getattr(cerebro, "precio", None)
    if not precio:
        return
    # `ahorro_cache` es una @property en CerebroNube, no un método — sin esto revienta
    # con "'float' object is not callable" en la primera carrera BYOK de verdad.
    ahorro = getattr(cerebro, "ahorro_cache", 0.0)
    linea = tui.linea_costo(r.uso.tokens_entrada, r.uso.tokens_salida, precio, ahorro)
    if linea:
        print(linea)


# ── `genai tarea` ────────────────────────────────────────────────────────────
def cmd_tarea(a) -> int:
    prep = _preparar_sesion(a, a.encargo)
    if prep is None:
        return 2
    cerebro, sesion, reg, registro, ultima, _S = prep
    print(tui.banner("Mekro-Genai", [
        f"cerebro {tui.resalte(cerebro.nombre)} · modo {a.modo}",
        f"topes: {a.vueltas} vueltas · {a.tokens} tokens · {a.segundos} s"]))

    def _correr(encargo: str, modo: str):
        return turno(sesion, registro, Politica(modo=modo), encargo,
                     tope_vueltas=a.vueltas, tope_tokens=a.tokens,
                     tope_segundos=a.segundos, tope_costo=a.tope_costo,
                     preguntar=preguntar_por_consola if modo == "preguntar" else None,
                     traza_por_pantalla=not a.callado)

    encargo, adjuntos = _expandir_menciones(a.encargo)
    for ruta in adjuntos:
        print(tui.atenuado(f"  · @{ruta} adjuntado directo (sin gastar un turno en "
                           "pedir `leer`)"))
    # sesion.uso es ACUMULADO de toda la sesión (importa con --continuar, que puede
    # arrancar con horas ya gastadas): el aviso de «turno largo» tiene que medir
    # SOLO lo que costó ESTA invocación, no arrastrar lo de antes.
    segundos_antes = sesion.uso.segundos

    try:
        r = _correr(encargo, a.modo)
        if a.modo == "plan" and r.motivo == "fin":
            # plan conversacional (M5.5): proponer → aprobar → ejecutar, en la MISMA
            # sesión (el append-exacto hace barata la continuación).
            print(f"\n{tui.markdown_ligero(r.texto)}\n")
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

    _guardar_sesion(sesion, ultima)
    tui.avisar_fin(r.uso.segundos - segundos_antes, r.texto[:120] or f"terminó: {r.motivo}")
    print(f"\n{tui.markdown_ligero(r.texto)}")
    print(tui.resumen_final(r.motivo, r.vueltas, r.uso.tokens_salida,
                            r.uso.tokens_entrada, r.uso.segundos, r.intervenciones))
    _mostrar_costo(sesion.cerebro, r)
    print(tui.atenuado(f"   sesión guardada en {ultima} (retoma con --continuar)"))
    return 0 if r.motivo == "fin" else 1


# ── `genai chat` — la conversación continua que a esto le faltaba ───────────
def cmd_chat(a) -> int:
    """Claude Code y OpenCode se sienten un lugar de trabajo, no un comando que se
    invoca, porque son eso: una conversación que sigue viva mientras la terminal
    sigue abierta. `genai tarea` es un turno por proceso; esto es la misma `Sesion`
    en memoria a lo largo de muchos mensajes, con el contexto append-exacto haciendo
    barato cada uno nuevo — la arquitectura que META.md pide para el cerebro local
    resulta ser también la que hace un REPL barato de sostener."""
    prep = _preparar_sesion(a, "sesión interactiva")
    if prep is None:
        return 2
    cerebro, sesion, reg, registro, ultima, _S = prep
    modo = a.modo

    print(tui.banner("Mekro-Genai · chat", [
        f"cerebro {tui.resalte(cerebro.nombre)} · modo {modo} · sesión {sesion.id}",
        "escribe tu encargo · /ayuda para los comandos",
        "/salir o Ctrl-D para terminar"]))

    try:
        while True:
            try:
                linea = input(tui.negrita("\n› ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not linea:
                continue
            if linea in ("/salir", "/exit", "/quit"):
                break
            if linea == "/ayuda":
                print(tui.caja(tui.tabla([
                    (f"/modo <{'|'.join(MODOS)}>", "cambia la política de permiso"),
                    ("/modelo", "menú guiado para elegir cerebro (local, BYOK, suscripción)"),
                    ("/modelo <nombre>", "cambia directo, sin menú (ej.: nube:gemini)"),
                    ("/nueva", "otra sesión, misma terminal y cerebro"),
                    ("/sesion", "vueltas y tokens gastados hasta ahora"),
                    ("/deshacer", "restaura los ficheros a antes del último mensaje"),
                    ("@ruta/al/fichero", "mételo en el mensaje sin gastar un turno en leerlo"),
                    ("/salir", "termina (o Ctrl-D)"),
                ]), titulo="comandos"))
                continue
            if linea == "/modelo" or linea.startswith("/modelo "):
                partes = linea.split(maxsplit=1)
                if len(partes) == 2:
                    pedido = partes[1].strip()
                else:
                    # sin argumento: el menú guiado, no exigir de memoria
                    # «nube:proveedor/modelo» — lo que pidió el usuario explícitamente.
                    pedido = _elegir_cerebro_guiado()
                    if pedido is None:
                        continue
                try:
                    nuevo = cargar(pedido)
                except SystemExit as e:
                    # el propio SystemExit de cargar()/CerebroNube ya dice qué hacer
                    # («Ejecuta `genai copilot entrar`», «pon tu clave en ...») — no
                    # hace falta un mensaje aparte de ayuda, solo enseñarlo bien.
                    print(tui.fallo(f"  no se pudo cargar «{pedido}»: {e}"))
                    continue
                if hasattr(sesion.cerebro, "cerrar"):
                    sesion.cerebro.cerrar()
                if hasattr(nuevo, "al_token") and not a.sin_streaming:
                    nuevo.al_token = lambda trozo: print(trozo, end="", flush=True)
                _con_latido(nuevo)
                sesion.cerebro = nuevo
                # el HISTORIAL sigue intacto: solo cambia quién genera la próxima
                # respuesta. Cambiar de local a BYOK a media conversación —o volver—
                # sin perder los mensajes de antes es justo lo que unifica los tres
                # caminos de docs/nube.md en una sola sesión.
                print(tui.exito(f"  cerebro → {nuevo.nombre} (el historial sigue igual)"))
                _info_tras_cambio(pedido)
                continue
            if linea == "/deshacer":
                from . import deshacer
                ok, mensaje, restaurados = deshacer.deshacer_ultimo(sesion.id)
                if not ok:
                    print(tui.aviso(f"  {mensaje}"))
                else:
                    print(tui.exito(f"  deshecho: {mensaje[:60]!r}" if mensaje else "  deshecho"))
                    for r in restaurados:
                        print(f"    ↺ {r}")
                continue
            if linea.startswith("/modo"):
                partes = linea.split(maxsplit=1)
                if len(partes) == 2 and partes[1] in MODOS:
                    modo = partes[1]
                    print(tui.atenuado(f"  modo → {modo}"))
                else:
                    print(tui.aviso(f"  modos válidos: {', '.join(MODOS)}"))
                continue
            if linea == "/sesion":
                print(tui.atenuado(
                    f"  {sesion.id} · {sesion.vueltas} vueltas · "
                    f"{sesion.uso.tokens_salida} tok salida / "
                    f"{sesion.uso.tokens_entrada} entrada"))
                continue
            if linea == "/nueva":
                _S.soltar(reg["id"])
                reg = _S.crear("sesión interactiva")
                sesion = Sesion(sistema=SISTEMA.format(raiz=Path.cwd()), cerebro=cerebro,
                                id=reg["id"])
                tomada, queja = _S.tomar(reg["id"])
                if not tomada:
                    print(tui.fallo(f"  {queja}"))
                    return 2
                print(tui.atenuado(f"  nueva sesión {sesion.id}"))
                continue

            encargo, adjuntos = _expandir_menciones(linea)
            for ruta in adjuntos:
                print(tui.atenuado(f"  · @{ruta} adjuntado directo (sin gastar un "
                                   "turno en pedir `leer`)"))
            segundos_antes = sesion.uso.segundos   # delta de ESTE mensaje, no del chat entero
            r = turno(sesion, registro, Politica(modo=modo), encargo,
                     tope_vueltas=a.vueltas, tope_tokens=a.tokens,
                     tope_segundos=a.segundos, tope_costo=a.tope_costo,
                     preguntar=preguntar_por_consola if modo == "preguntar" else None,
                     traza_por_pantalla=not a.callado)
            tui.avisar_fin(r.uso.segundos - segundos_antes, r.texto[:120] or "listo")
            print(f"\n{tui.markdown_ligero(r.texto)}")
            print(tui.resumen_final(r.motivo, r.vueltas, r.uso.tokens_salida,
                                    r.uso.tokens_entrada, r.uso.segundos, r.intervenciones))
            _mostrar_costo(sesion.cerebro, r)
            _guardar_sesion(sesion, ultima)
    finally:
        _S.latir(reg["id"], vueltas=sesion.vueltas)
        _S.soltar(reg["id"])
        if hasattr(sesion.cerebro, "cerrar"):
            sesion.cerebro.cerrar()

    print(tui.atenuado(f"sesión guardada en {ultima} (retoma con `genai tarea --continuar`)"))
    return 0


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
    # Bare `genai mcp` (sin argumentos): comportamiento EXACTO de siempre — es lo que
    # Claude Code, Codex y Cursor ya tienen registrado. `--trazar` es opt-in y solo
    # existe para quien arranca el servidor a mano en una terminal para depurar: la
    # traza va a stderr, nunca a stdout (el canal JSON-RPC), así que no puede
    # interferir con ningún cliente real que sí pase por aquí.
    from .mcp import servir
    servir(trazar="--trazar" in args)
    return 0


# ── `genai deshacer` ─────────────────────────────────────────────────────────
def cmd_deshacer(args: list[str]) -> int:
    """Restaura los ficheros al estado de ANTES del último turno de una sesión —el
    checkpoint que `bucle.py` guarda solo, sin que nadie lo pida (ver deshacer.py).
    Sin argumentos usa la sesión de `.genai/ultima.json` de este directorio."""
    from . import deshacer

    sesion_id = args[0] if args else ""
    if not sesion_id:
        ultima = Path(".genai") / "ultima.json"
        if not ultima.exists():
            print("no hay ninguna sesión reciente en este directorio; da el id a "
                  "mano: `genai deshacer <id>` (`genai sesiones` para verlos).")
            return 2
        sesion_id = json.loads(ultima.read_text(encoding="utf-8"))["id"]

    ok, mensaje, restaurados = deshacer.deshacer_ultimo(sesion_id)
    if not ok:
        print(tui.aviso(mensaje))
        return 1
    print(tui.exito(f"deshecho: {mensaje[:80]!r}" if mensaje else "deshecho"))
    for r in restaurados:
        print(f"  ↺ {r}")
    return 0


def cmd_ui(puerto: int, abrir_navegador: bool) -> int:
    """`genai ui` — la interfaz gráfica: una página servida por `genai/servidor.py`
    (`genai sesiones servir` es el mismo servidor; esto solo añade abrir el
    navegador). Sin instalar nada ni añadir un ecosistema de JavaScript: funciona en
    Linux, macOS y WSL exactamente igual, porque es un navegador hablando HTTP con
    localhost — no hay ninguna pieza nativa por sistema operativo que mantener."""
    import webbrowser

    from .servidor import servir

    def _abrir(url: str) -> None:
        if abrir_navegador:
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001 — sin navegador, la URL ya se imprimió
                pass

    # `puerto` tal cual, SIN «or 7654»: 0 es el defecto documentado («uno libre
    # cualquiera») y en Python `0 or 7654` da 7654 siempre — ese `or` volvía inalcanzable
    # el propio comportamiento por defecto que el --help promete.
    servir(puerto, al_arrancar=_abrir)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="genai", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden")

    def _flags_encargo(sp) -> None:
        """Comunes a `tarea` (un turno por proceso) y `chat` (muchos, en el
        mismo): qué cerebro, qué política de permiso, qué topes."""
        sp.add_argument("--cerebro", default="gguf",
                        help="gguf (local, defecto) · eco (pruebas) · "
                             "nube:PROVEEDOR[/MODELO] con TU clave (docs/nube.md)")
        sp.add_argument("--modo", default="preguntar", choices=MODOS)
        sp.add_argument("--vueltas", type=int, default=16)
        sp.add_argument("--tokens", type=int, default=4000)
        sp.add_argument("--segundos", type=int, default=3600)
        sp.add_argument("--tope-costo", type=float, default=None,
                        help="para BYOK: para el turno si el gasto estimado (USD, "
                             "según precio del catálogo) llega a esto; sin efecto en "
                             "local o suscripción, que no tienen coste por token")
        sp.add_argument("--continuar", action="store_true",
                        help="retomar la última sesión de este directorio "
                             "(.genai/ultima.json)")
        sp.add_argument("--cerebro-subagente", default="",
                        help="modo híbrido: cerebro para los subagentes de exploración")
        sp.add_argument("--cerebro-resumidor", default="",
                        help="modo híbrido: cerebro para el resumen del renacimiento")
        sp.add_argument("--hibrido", default="",
                        help="atajo: PROVEEDOR de nube para TODOS los roles auxiliares, "
                             "conservando el cerebro principal local "
                             "(ej.: --hibrido nube:gemini)")
        sp.add_argument("--malla", action="store_true",
                        help="modo Mesh: permite delegar tareas a pares (docs/malla.md)")
        sp.add_argument("--sin-streaming", action="store_true",
                        help="no pintar el texto según se genera")
        sp.add_argument("--sin-web", action="store_true",
                        help="quitar el acceso a la web (viene encendido; nunca alcanza "
                             "esta máquina ni esta red)")
        sp.add_argument("--sesion", default="",
                        help="id de una sesión existente (`genai sesiones`); si no se "
                             "da, se abre una nueva. Varios agentes pueden trabajar a "
                             "la vez en el mismo proyecto, cada uno con la suya")
        sp.add_argument("--guion", default="",
                        help="JSON con el guion, solo para --cerebro eco")
        sp.add_argument("--callado", action="store_true", help="sin traza por pantalla")

    t = sub.add_parser("tarea", help="un encargo agéntico en el directorio actual")
    t.add_argument("encargo")
    _flags_encargo(t)

    ch = sub.add_parser("chat", help="conversación continua (estilo Claude Code/OpenCode)")
    _flags_encargo(ch)

    sub.add_parser("version", help="qué hay instalado y qué cerebro ve")

    de = sub.add_parser("deshacer",
                        help="restaura los ficheros al estado de antes del último turno")
    de.add_argument("sesion", nargs="?", default="",
                    help="id de sesión (por defecto, la última usada en este directorio)")

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

    ui = sub.add_parser("ui", help="interfaz gráfica ligera (navegador, sin instalar nada)")
    ui.add_argument("--puerto", type=int, default=0, help="0 = uno libre cualquiera")
    ui.add_argument("--sin-navegador", action="store_true",
                    help="no abrir el navegador solo; imprime la URL igualmente")

    a = ap.parse_args(argv)
    if a.orden == "tarea":
        return cmd_tarea(a)
    if a.orden == "chat":
        return cmd_chat(a)
    if a.orden == "deshacer":
        return cmd_deshacer([a.sesion] if a.sesion else [])
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
    if a.orden == "ui":
        return cmd_ui(a.puerto, not a.sin_navegador)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
