"""Servidor de sesiones: la separación cliente/servidor que arquitectura.md debía.

`docs/arquitectura.md` cita «la separación servidor/cliente de OpenCode» como
inspiración desde el primer día, igual que citaba el LSP. Esta es la otra deuda.

**Por qué importa más de lo que parece.** No es una API por tenerla: es lo que convierte
tres brechas en una. Con un servidor, *multi-sesión* es listar y adjuntarse, *compartir*
es exportar lo que el servidor ya sabe, y *cualquier editor* es un cliente más — una
extensión de VS Code no necesita reimplementar el arnés, solo hablar HTTP. Y ahora
también es la base de la **interfaz gráfica** (`genai ui`, `genai/ui.html`): la página
es solo un cliente más de esta misma API, no un programa aparte.

**Escucha en 127.0.0.1 y punto.** Lo contrario sería abrir un agente con permiso de
escritura a la red local. La malla (`malla.py`) sí sale fuera, pero eso es opt-in
declarado y con clave compartida; esto es infraestructura de escritorio y se queda en
casa. Para llegar desde otra máquina está SSH, que ya sabe hacer esto bien.

**Y aun así pide clave.** En una máquina compartida, «solo local» no es «solo tuyo»:
cualquier proceso del equipo puede hablar con 127.0.0.1. La clave se genera sola y se
guarda con permisos 600. La única excepción es `/` y `/salud`: quien ya puede alcanzar
este puerto en esta máquina ya tiene el mismo nivel de acceso que ver la página, así que
pedir clave ahí no protegería nada — y es lo que permite que el navegador cargue la UI
sin tener que leer un fichero del disco primero (algo que JS de una página no puede
hacer). La clave se sirve embebida en el HTML, no antes de eso.

**Ejecutar una tarea en vivo reutiliza `turno()` tal cual**, en un hilo de fondo por
sesión, y NO inventa un protocolo de streaming nuevo: el cliente sondea
`/sesiones/<id>` (¿va por la vuelta N? ¿hay un permiso pendiente?) y
`/sesiones/<id>/transcripcion` (la conversación tal como va, en memoria mientras corre)
cada uno o dos segundos. Con un cerebro que tarda segundos o minutos por vuelta, sondear
cada 1-2 s es indistinguible de un streaming de verdad, y evita mantener abierto un
canal de eventos para un fallo más que depurar.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import sesiones
from .nucleo.permisos import Decision

PUERTO = 7654
FICHERO_CLAVE = Path.home() / ".config" / "genai" / "servidor.clave"
TOPE_CUERPO = 2 * 1024 * 1024


def clave(crear: bool = True) -> str:
    if FICHERO_CLAVE.is_file():
        return FICHERO_CLAVE.read_text(encoding="utf-8").strip()
    if not crear:
        return ""
    k = secrets.token_hex(16)
    FICHERO_CLAVE.parent.mkdir(parents=True, exist_ok=True)
    FICHERO_CLAVE.write_text(k, encoding="utf-8")
    os.chmod(FICHERO_CLAVE, 0o600)
    return k


# ── ejecutar tareas en vivo ──────────────────────────────────────────────────
# Una sesión en curso vive aquí, en memoria del proceso del servidor — no en disco —
# mientras corre. `_transcripcion()` la mira primero; cuando termina, `cmd_tarea`-style
# la guarda en logs/sesiones/ como cualquier otra y desaparece de aquí.
_EN_VIVO: dict[str, object] = {}
_ESPERANDO: dict[str, tuple[threading.Event, dict]] = {}


def _preguntar_por_servidor(ident: str):
    """El `preguntar` de una tarea lanzada desde la UI: en vez de bloquear en
    `input()` —no hay consola—, publica la pregunta en el estado de la sesión y
    bloquea el HILO DE FONDO hasta que `/sesiones/<id>/responder` la conteste. La
    tarea de verdad se detiene a esperar un humano, igual que en modo `preguntar`
    por consola; aquí el «terminal» es la página."""
    def _preguntar(herramienta, argumentos) -> Decision:
        evento = threading.Event()
        caja: dict = {}
        _ESPERANDO[ident] = (evento, caja)
        sesiones.latir(ident, pregunta_pendiente={
            "herramienta": herramienta.nombre, "argumentos": argumentos})
        evento.wait()          # sin plazo: igual que un `input()` sin nadie delante
        sesiones.latir(ident, pregunta_pendiente=None)
        _ESPERANDO.pop(ident, None)
        return Decision(bool(caja.get("permitido")), "decidido desde la interfaz")
    return _preguntar


def _lanzar(ident: str, params: dict) -> tuple[bool, str]:
    from .cerebro import cargar
    from .herramientas import estandar
    from .memoria import HERRAMIENTAS as HERRAMIENTAS_HOLO
    from .nucleo import Politica, Sesion, turno

    if ident in _EN_VIVO:
        return False, "esta sesión ya tiene una tarea en curso"
    tomada, queja = sesiones.tomar(ident)
    if not tomada:
        return False, queja

    encargo = (params.get("encargo") or "").strip()
    if not encargo:
        sesiones.soltar(ident)
        return False, "el encargo está vacío"
    cerebro_nombre = params.get("cerebro") or "gguf"
    modo = params.get("modo") or "preguntar"
    try:
        cerebro = cargar(cerebro_nombre)
    except SystemExit as e:
        sesiones.soltar(ident)
        return False, str(e)

    # El id de la Sesión se ATA al de la entrada del registro (`ident`): sin esto,
    # `Sesion` generaría su propio UUID al azar y `/transcripcion` —que busca el
    # fichero guardado por `ident`— nunca lo encontraría. Es el mismo fallo que tenía
    # `cli.py` antes de repararlo hoy: dos identidades para la misma sesión.
    sesion = Sesion(sistema=f"Eres Mekro-Genai, un agente de ingeniería que trabaja "
                            f"en el repositorio {Path.cwd()}.", cerebro=cerebro,
                    id=ident)
    registro = estandar(incluir_peligrosas=modo != "plan", web=True)
    for h in HERRAMIENTAS_HOLO:
        if not (h.peligrosa and modo == "plan"):
            registro.registrar(h)

    _EN_VIVO[ident] = sesion
    sesiones.latir(ident, en_curso=True, motivo="")

    def _correr():
        try:
            r = turno(sesion, registro, Politica(modo=modo), encargo,
                     tope_vueltas=int(params.get("vueltas", 16)),
                     tope_tokens=int(params.get("tokens", 4000)),
                     tope_segundos=int(params.get("segundos", 3600)),
                     preguntar=(_preguntar_por_servidor(ident)
                               if modo == "preguntar" else None),
                     traza_por_pantalla=False)
            sesiones.latir(ident, en_curso=False, motivo=r.motivo,
                          vueltas=sesion.vueltas)
        except Exception as e:  # noqa: BLE001 — un fallo aquí no puede tumbar el
            sesiones.latir(ident, en_curso=False, motivo=f"error: {e}")  # servidor
        finally:
            if hasattr(sesion.cerebro, "cerrar"):
                sesion.cerebro.cerrar()
            d = Path("logs") / "sesiones"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{time.strftime('%Y-%m-%d')}_{sesion.id}.json").write_text(
                json.dumps(sesion.a_dict(), ensure_ascii=False, indent=1),
                encoding="utf-8")
            _EN_VIVO.pop(ident, None)
            sesiones.soltar(ident)

    threading.Thread(target=_correr, daemon=True).start()
    return True, "lanzada"


class _Manejador(BaseHTTPRequestHandler):
    clave = ""
    proyecto = Path(".")

    # ── plomería ───────────────────────────────────────────────────────────
    def _responder(self, codigo: int, cuerpo: dict | list) -> None:
        b = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _html(self, texto: str) -> None:
        b = texto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _autorizado(self) -> bool:
        dado = (self.headers.get("X-Genai-Clave") or "").strip()
        # comparación en tiempo constante: comparar claves con == filtra información
        # por el tiempo de respuesta, y aquí no cuesta nada hacerlo bien
        return bool(dado) and secrets.compare_digest(dado, self.clave)

    def _cuerpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > TOPE_CUERPO:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8", "replace"))
        except ValueError:
            return {}

    def log_message(self, *a):
        pass                      # el servidor no ensucia la terminal del agente

    # ── rutas ──────────────────────────────────────────────────────────────
    def do_GET(self):
        r = urlparse(self.path)
        if r.path == "/salud":                 # sin clave: es para saber si está vivo
            return self._responder(200, {"ok": True, "proyecto": str(self.proyecto),
                                         "version": 1})
        if r.path in ("/", "/ui"):
            # Sin clave A PROPÓSITO: quien ya alcanza este puerto en esta máquina
            # tiene el mismo acceso que ver la página, y una página no puede leer
            # ~/.config/genai/servidor.clave del disco por su cuenta. La clave se
            # sirve embebida AQUÍ, no antes.
            return self._html(_pagina(self.clave))
        if not self._autorizado():
            return self._responder(401, {"error": "clave incorrecta o ausente "
                                                  "(cabecera X-Genai-Clave)"})
        if r.path == "/sesiones":
            return self._responder(200, {"sesiones": sesiones.listar()})
        if r.path == "/conflictos":
            return self._responder(200, {"conflictos": [
                {"fichero": f, "sesiones": ids} for f, ids in sesiones.conflictos()]})
        if r.path == "/cerebros":
            return self._responder(200, _cerebros_disponibles())
        if r.path == "/claves":
            return self._responder(200, _claves_enmascaradas())
        if r.path.startswith("/sesiones/"):
            ident = r.path.split("/")[2]
            s = next((x for x in sesiones.listar() if x["id"] == ident), None)
            if not s:
                return self._responder(404, {"error": f"no existe «{ident}»"})
            if r.path.endswith("/transcripcion"):
                return self._responder(200, _transcripcion(ident))
            return self._responder(200, s)
        return self._responder(404, {"error": f"no hay ruta {r.path}"})

    def do_POST(self):
        if not self._autorizado():
            return self._responder(401, {"error": "clave incorrecta o ausente"})
        r = urlparse(self.path)
        cuerpo = self._cuerpo()
        if r.path == "/sesiones":
            s = sesiones.crear(cuerpo.get("titulo", ""), meta=cuerpo.get("meta") or {})
            return self._responder(201, s)
        if r.path == "/claves":
            return self._guardar_clave(cuerpo)
        partes = r.path.strip("/").split("/")
        if len(partes) == 3 and partes[0] == "sesiones":
            ident, accion = partes[1], partes[2]
            if accion == "tomar":
                s, queja = sesiones.tomar(ident)
                return self._responder(200 if s else 409, s or {"error": queja})
            if accion == "soltar":
                sesiones.soltar(ident)
                return self._responder(200, {"ok": True})
            if accion == "latido":
                sesiones.latir(ident, **{k: v for k, v in cuerpo.items()
                                         if k in ("vueltas", "tocados", "estado")})
                return self._responder(200, {"ok": True})
            if accion == "lanzar":
                ok, msg = _lanzar(ident, cuerpo)
                return self._responder(200 if ok else 409, {"ok": ok, "mensaje": msg})
            if accion == "responder":
                if ident not in _ESPERANDO:
                    return self._responder(409, {"error": "esta sesión no tiene "
                                                          "ningún permiso pendiente"})
                evento, caja = _ESPERANDO[ident]
                caja["permitido"] = bool(cuerpo.get("permitido"))
                evento.set()
                return self._responder(200, {"ok": True})
        return self._responder(404, {"error": f"no hay ruta {r.path}"})

    def _guardar_clave(self, cuerpo: dict):
        from .cerebro.nube import CLAVES

        proveedor = (cuerpo.get("proveedor") or "").strip()
        valor = (cuerpo.get("clave") or "").strip()
        if not proveedor or not valor:
            return self._responder(400, {"error": "faltan «proveedor» o «clave»"})
        # MISMA ruta que lee `claves()` (respeta MG_CLAVES) — antes esto escribía
        # siempre en ~/.config/genai/claves.json a pelo, sin importar la variable de
        # entorno que GET /claves ya honraba: una prueba que quisiera aislarse no
        # podía, y acababa tocando el fichero REAL de secretos del usuario. Eso
        # además corrió carrera de verdad con `scripts/guardian.py` (que ejecuta la
        # misma suite cada 15 min) la primera vez que se probó en frío.
        f = CLAVES
        f.parent.mkdir(parents=True, exist_ok=True)
        try:
            datos = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
        except ValueError:
            return self._responder(500, {"error": f"{f} existe pero no es JSON "
                                                  f"válido; arréglalo a mano"})
        # se COMPLETA la entrada del proveedor, no se pisa entera: puede tener
        # `modelo`, `cabeceras` u otras claves puestas a mano
        datos.setdefault(proveedor, {})
        if isinstance(datos[proveedor], dict):
            datos[proveedor]["clave"] = valor
        else:
            datos[proveedor] = {"clave": valor}
        f.write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
        os.chmod(f, 0o600)
        return self._responder(200, {"ok": True})


def _transcripcion(ident: str) -> dict:
    """La conversación tal como va. Si la sesión está corriendo AHORA, se lee de
    memoria —es más reciente que cualquier fichero—; si no, del disco, como siempre."""
    if ident in _EN_VIVO:
        return _EN_VIVO[ident].a_dict()
    for d in (Path("logs") / "sesiones", Path(".genai") / "transcripciones"):
        for f in sorted(d.glob(f"*{ident}*.json")) if d.is_dir() else []:
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return {"mensajes": [], "aviso": "esta sesión aún no ha guardado transcripción"}


def _cerebros_disponibles() -> dict:
    """Qué se le puede ofrecer al selector de la interfaz: lo de fábrica, lo que ya
    tiene clave guardada, el local si el GGUF está, y las suscripciones directas."""
    from .cerebro.local_gguf import GGUF
    from .cerebro.nube import PROVEEDORES, claves
    from . import copilot, google_cuenta
    cl = claves()
    return {
        "local": {"disponible": Path(GGUF).is_file(), "ruta": str(GGUF)},
        "fabrica": sorted(PROVEEDORES),
        "configurados": sorted(p for p in cl if isinstance(cl.get(p), dict)
                               and cl[p].get("clave")),
        "suscripciones": {"copilot": copilot.estado(), "google": google_cuenta.estado()},
    }


def _claves_enmascaradas() -> dict:
    """Qué proveedores tienen clave guardada, SIN devolver el secreto — ni truncado:
    para una interfaz de ajustes basta saber que existe y desde cuándo, no verla."""
    from .cerebro.nube import claves
    cl = claves()
    return {p: {"configurada": bool(v.get("clave"))} for p, v in cl.items()
            if isinstance(v, dict)}


def _pagina(clave_actual: str) -> str:
    # Las llamadas fetch() de la página son relativas: el navegador ya las manda al
    # mismo origen (host y puerto) desde el que cargó la página, así que el puerto
    # no hace falta embeberlo.
    from .ui import PAGINA
    return PAGINA.replace("__CLAVE__", clave_actual)


def servir(puerto: int = PUERTO, bloquear: bool = True,
          al_arrancar=None) -> ThreadingHTTPServer:
    """`al_arrancar(url)`, si se da, se llama justo tras reservar el puerto y antes de
    bloquear — el único enganche que `genai ui` necesita para abrir el navegador con
    la URL real (puede haber cambiado si el puerto por defecto ya estaba ocupado)."""
    _Manejador.clave = clave()
    _Manejador.proyecto = Path.cwd()
    # 127.0.0.1 y no 0.0.0.0: lo contrario abre un agente con permiso de escritura a
    # la red local. Para llegar desde fuera está SSH, que ya sabe hacer esto bien.
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _Manejador)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    if al_arrancar:
        al_arrancar(url)
    if not bloquear:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    # flush=True: sin él, estos prints se quedan en el búfer cuando la salida no va
    # a una terminal (redirigida, en segundo plano) y serve_forever() bloquea antes de
    # vaciarlo — el usuario ve un proceso «colgado» que en realidad ya está sirviendo.
    # Costó exactamente esto mismo con genai/google_cuenta.py; se aprende una vez.
    print(f"interfaz y servidor de sesiones en {url}", flush=True)
    print(f"  proyecto: {Path.cwd()}", flush=True)
    print(f"  clave:    {FICHERO_CLAVE}  (cabecera X-Genai-Clave; la UI la trae sola)",
          flush=True)
    print("  rutas:    GET / (interfaz) · /salud /sesiones /sesiones/<id>/"
          "{transcripcion,lanzar} /cerebros /claves", flush=True)
    print("            POST /sesiones · /sesiones/<id>/{tomar,soltar,latido,lanzar,"
          "responder} · /claves", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nservidor parado", flush=True)
    return srv
