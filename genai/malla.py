"""malla.py — el modo Mesh (M6): tareas enteras entre pares de confianza.

El grano es la TAREA, no el token: repartir la inferencia por capas está descartado
con medición (C20: caché recurrente sin operaciones parciales; latencia WAN por token).
Un par ejecuta la tarea completa con SU cerebro y el verificador LOCAL del delegante
decide si el resultado vale. Diseño completo: docs/malla.md.

Tres papeles en un módulo, sin dependencias fuera de la stdlib:

    python3 -m genai.malla servir --hilos 4 --cerebro gguf     # donar cómputo
    python3 -m genai.malla esperar <par> <id> <nombre>         # (interno) el poller
    malla_delegar — la herramienta del agente (ver HERRAMIENTAS)

La espera se integra con el fondo (M5.3): delegar deja un poller desasido que escribe
`.genai/fondo/<nombre>.rc` al terminar, y el AVISO llega por el bucle como cualquier
otro fondo. El resultado queda en CUARENTENA (`.genai/malla/<nombre>/`), nunca sobre
el árbol de trabajo.
"""
from __future__ import annotations

import base64
import io
import json
import os
import secrets
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .herramientas.base import Herramienta, Resultado

CONFIG = Path(os.environ.get("MG_MALLA_CONFIG",
                             Path.home() / ".config" / "genai" / "malla.json"))
CUENTA = CONFIG.with_name("malla-cuenta.json")
TOPE_SOBRE = 10 * 2**20          # 10 MB de semilla: una tarea, no un repositorio
TOPES_SERVIDOR = {"tope_vueltas": 16, "tope_tokens": 4000, "tope_segundos": 3600}


def _config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    return {}


def _anotar_cuenta(clave: str, segundos: float) -> None:
    CUENTA.parent.mkdir(parents=True, exist_ok=True)
    c = json.loads(CUENTA.read_text(encoding="utf-8")) if CUENTA.exists() else {}
    c[clave] = round(c.get(clave, 0.0) + segundos, 1)
    CUENTA.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def _tar_b64(directorio: Path) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for f in sorted(directorio.rglob("*")):
            rel = f.relative_to(directorio)
            if any(p.startswith((".genai", ".git", "__pycache__")) for p in rel.parts):
                continue
            t.add(f, arcname=str(rel), recursive=False)
    datos = buf.getvalue()
    if len(datos) > TOPE_SOBRE:
        raise ValueError(f"el directorio pesa {len(datos)} B empaquetado y el tope "
                         f"del sobre es {TOPE_SOBRE}: una tarea, no un repositorio")
    return base64.b64encode(datos).decode()


def _desempaquetar(b64: str, destino: Path) -> None:
    datos = base64.b64decode(b64)
    with tarfile.open(fileobj=io.BytesIO(datos), mode="r:gz") as t:
        for m in t.getmembers():
            ruta = (destino / m.name).resolve()
            if not str(ruta).startswith(str(destino.resolve())):
                raise ValueError(f"ruta hostil en el sobre: {m.name}")
        t.extractall(destino)


def _pedir(par: str, camino: str, cuerpo: dict | None, clave: str) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(
        f"http://{par}{camino}", data=datos, method="POST" if datos else "GET",
        headers={"Content-Type": "application/json", "X-Malla-Clave": clave})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ── el servidor: donar cómputo ──────────────────────────────────────────────


class _Manejador(BaseHTTPRequestHandler):
    """UNA tarea a la vez: el computo donado es una fraccion, no la maquina entera,
    y un servidor simple se audita entero de una lectura."""

    directorio: Path = None
    clave: str = ""
    hilos: int = 4
    cerebro: str = "gguf"
    estado: dict = {"corriendo": None}

    def _json(self, codigo, cuerpo):
        datos = json.dumps(cuerpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, *a):
        pass

    def _autorizado(self) -> bool:
        # comparacion en tiempo constante: la clave es lo unico que separa a un par
        # de confianza de cualquiera que alcance el puerto
        return secrets.compare_digest(
            self.headers.get("X-Malla-Clave", ""), self.clave)

    def do_POST(self):
        if not self._autorizado():
            return self._json(403, {"error": "clave incorrecta"})
        if self.path != "/tarea":
            return self._json(404, {"error": "camino desconocido"})
        if self.estado["corriendo"]:
            return self._json(503, {"error": "ocupado: una tarea a la vez"})
        largo = int(self.headers.get("Content-Length", 0))
        if largo > TOPE_SOBRE * 2:
            return self._json(413, {"error": "sobre demasiado grande"})
        sobre = json.loads(self.rfile.read(largo).decode())
        ident = secrets.token_hex(8)
        caja = self.directorio / ident
        caja.mkdir(parents=True)
        try:
            _desempaquetar(sobre["semilla"], caja / "trabajo")
        except Exception as e:
            return self._json(400, {"error": f"sobre invalido: {e}"})
        (caja / "encargo.json").write_text(
            json.dumps({"encargo": sobre["encargo"],
                        "topes": {**TOPES_SERVIDOR,
                                  **{k: v for k, v in (sobre.get("topes") or {}).items()
                                     if k in TOPES_SERVIDOR
                                     and isinstance(v, int)
                                     and 0 < v <= TOPES_SERVIDOR[k]}}},
                       ensure_ascii=False), encoding="utf-8")
        hilo = threading.Thread(target=self._ejecutar, args=(caja,), daemon=True)
        self.estado["corriendo"] = ident
        hilo.start()
        return self._json(202, {"id": ident})

    def do_GET(self):
        if not self._autorizado():
            return self._json(403, {"error": "clave incorrecta"})
        if not self.path.startswith("/resultado/"):
            return self._json(404, {"error": "camino desconocido"})
        caja = self.directorio / self.path.split("/")[-1]
        listo = caja / "listo.json"
        if not caja.is_dir():
            return self._json(404, {"error": "no existe esa tarea"})
        if not listo.exists():
            return self._json(200, {"estado": "corriendo"})
        return self._json(200, json.loads(listo.read_text(encoding="utf-8")))

    def _ejecutar(self, caja: Path):
        """La tarea ajena corre con la MISMA politica que una carrera del banco:
        modo lista, veto duro y rutas vedadas. Es el guardarrail que este proyecto
        lleva 80 ciclos usando (docs/malla.md, regla 2)."""
        from .cerebro import cargar
        from .herramientas import estandar
        from .nucleo import Politica, Sesion, turno

        enc = json.loads((caja / "encargo.json").read_text(encoding="utf-8"))
        t0 = time.time()
        salida = {"ok": False, "motivo": "", "texto": "", "resultado": ""}
        antes = os.getcwd()
        try:
            cerebro = cargar(self.cerebro)
            if hasattr(cerebro, "hilos"):
                cerebro.hilos = self.hilos      # solo la fraccion donada
            sesion = Sesion(sistema=SISTEMA_SERVIDOR, cerebro=cerebro)
            os.chdir(caja / "trabajo")
            r = turno(sesion, estandar(plugins=False),
                      Politica(modo="lista", vedadas=["..", "/etc", "/home"]),
                      enc["encargo"], traza_por_pantalla=False, **enc["topes"])
            salida.update(ok=r.motivo == "fin", motivo=r.motivo, texto=r.texto,
                          vueltas=r.vueltas, tokens=r.uso.tokens_salida)
        except Exception as e:
            salida.update(motivo="error", texto=f"{type(e).__name__}: {e}")
        finally:
            os.chdir(antes)
            try:
                salida["resultado"] = _tar_b64(caja / "trabajo")
            except Exception as e:
                salida["motivo"], salida["ok"] = f"resultado impaquetable: {e}", False
            salida["segundos"] = round(time.time() - t0, 1)
            (caja / "listo.json").write_text(
                json.dumps(salida, ensure_ascii=False), encoding="utf-8")
            _anotar_cuenta("donados", salida["segundos"])
            self.estado["corriendo"] = None
            print(f"  tarea {caja.name}: {salida['motivo']} "
                  f"({salida['segundos']} s donados)", flush=True)


SISTEMA_SERVIDOR = """Eres Mekro-Genai ejecutando una tarea delegada por un par de la
malla. Trabajas en el directorio actual, que es una copia aislada: haz el encargo y
verifica lo que afirmes con `bash`. Cuando este hecho, responde SIN llamar a ninguna
herramienta. El intérprete es `python3`; nada de `cd`."""


def servir(puerto: int, clave: str, hilos: int, cerebro: str) -> None:
    directorio = Path(tempfile.mkdtemp(prefix="malla-servidor-"))
    _Manejador.directorio, _Manejador.clave = directorio, clave
    _Manejador.hilos, _Manejador.cerebro = hilos, cerebro
    srv = ThreadingHTTPServer(("0.0.0.0", puerto), _Manejador)
    print(f"malla: sirviendo en :{puerto} con {hilos} hilos y cerebro {cerebro}\n"
          f"  cajas en {directorio}\n"
          f"  UNA tarea a la vez, modo lista + veto + vedadas. Ctrl-C para parar.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nmalla: servidor abajo (lo donado queda anotado en la cuenta)")


# ── el cliente: delegar y esperar ───────────────────────────────────────────

def delegar(encargo: str, nombre: str, directorio: str = ".") -> Resultado:
    """Envia el directorio de trabajo y el encargo al primer par disponible y deja
    un poller desasido: el AVISO de terminacion llega por el fondo (M5.3), y el
    resultado a CUARENTENA en .genai/malla/<nombre>/ — nunca sobre tu arbol."""
    cfg = _config()
    pares, clave = cfg.get("pares") or [], cfg.get("clave", "")
    if not pares or not clave:
        return Resultado(False, f"la malla no esta configurada: crea {CONFIG} con "
                                '{"clave": "...", "pares": ["host:7337"]}. '
                                "Modo local intacto (docs/malla.md).")
    if not str(nombre).isidentifier():
        return Resultado(False, "el nombre debe ser un identificador simple")
    try:
        semilla = _tar_b64(Path(directorio))
    except ValueError as e:
        return Resultado(False, str(e))

    for par in pares:
        try:
            r = _pedir(par, "/tarea", {"encargo": encargo, "semilla": semilla}, clave)
        except Exception as e:
            continue
        if not r.get("id"):
            continue
        # el poller vive fuera de este proceso: escribe el .rc del fondo al terminar
        fondo = Path(".genai") / "fondo"
        fondo.mkdir(parents=True, exist_ok=True)
        log = fondo / f"{nombre}.log"
        for viejo in (fondo / f"{nombre}.rc", fondo / f"{nombre}.avisado"):
            viejo.unlink(missing_ok=True)
        # el hijo hereda la ruta del paquete explicitamente: asi funciona tanto
        # instalado (pip install -e .) como corriendo desde el repositorio
        entorno = dict(os.environ)
        raiz = str(Path(__file__).resolve().parents[1])
        entorno["PYTHONPATH"] = (raiz + os.pathsep + entorno["PYTHONPATH"]
                                 if entorno.get("PYTHONPATH") else raiz)
        with open(log, "w", encoding="utf-8") as f:
            p = subprocess.Popen(
                [sys.executable, "-m", "genai.malla", "esperar", par, r["id"], nombre],
                stdout=f, stderr=subprocess.STDOUT, start_new_session=True, env=entorno)
        (fondo / f"{nombre}.pid").write_text(str(p.pid), encoding="utf-8")
        return Resultado(True, f"delegado a {par} como «{nombre}» (id {r['id'][:8]}). "
                               "Sigue con otra cosa: el bucle avisara al terminar. El "
                               f"resultado llegara EN CUARENTENA a .genai/malla/{nombre}/ "
                               "y no se aplica hasta que tu verificador local lo apruebe.",
                         {"par": par, "id": r["id"]})
    return Resultado(False, f"ningun par respondio ({', '.join(pares)}). "
                            "Sigue en local: la malla es opcional.")


def esperar(par: str, ident: str, nombre: str, intervalo: int = 5) -> int:
    """Sondea al par hasta que la tarea acabe y deja el resultado en cuarentena.

    Escribe el `.rc` del fondo al terminar: es la señal que el bucle mira al empezar
    la vuelta siguiente para entregar el AVISO (M5.3). Sin esto, delegar sería un
    grito al vacío."""
    clave = _config().get("clave", "")
    destino = Path(".genai") / "malla" / nombre
    rc = Path(".genai") / "fondo" / f"{nombre}.rc"

    def _cerrar(codigo: int) -> int:
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(str(codigo), encoding="utf-8")
        return codigo
    while True:
        try:
            r = _pedir(par, f"/resultado/{ident}", None, clave)
        except Exception as e:
            print(f"par ilocalizable: {e}")
            return _cerrar(1)
        if r.get("estado") == "corriendo":
            time.sleep(intervalo)
            continue
        destino.mkdir(parents=True, exist_ok=True)
        if r.get("resultado"):
            _desempaquetar(r["resultado"], destino)
        (destino / "informe.json").write_text(
            json.dumps({k: v for k, v in r.items() if k != "resultado"},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        _anotar_cuenta("consumidos", r.get("segundos", 0))
        print(f"tarea de la malla «{nombre}»: {r.get('motivo')} en "
              f"{r.get('segundos')} s. Resultado EN CUARENTENA en {destino} — "
              "revisalo y pasa TU verificador antes de aplicar nada.")
        return _cerrar(0 if r.get("ok") else 1)


def cuenta() -> dict:
    return json.loads(CUENTA.read_text(encoding="utf-8")) if CUENTA.exists() else {}


HERRAMIENTAS = [
    Herramienta(
        nombre="malla_delegar",
        descripcion=("Envia una tarea ENTERA a un par de la malla para que la ejecute "
                     "con su propio cerebro mientras tu sigues. El resultado llega en "
                     "cuarentena y NO se aplica sin pasar el verificador local. Usalo "
                     "para trabajo paralelizable e independiente, no para partir una "
                     "tarea que necesita tu contexto."),
        parametros={"type": "object", "properties": {
            "encargo": {"type": "string", "description": "la tarea, autocontenida"},
            "nombre": {"type": "string", "description": "identificador para seguirla"},
            "directorio": {"type": "string",
                           "description": "que enviar (por defecto, el actual)"}},
            "required": ["encargo", "nombre"]},
        peligrosa=True,
        funcion=delegar),
]


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="genai.malla", description=__doc__)
    sub = ap.add_subparsers(dest="orden")
    s = sub.add_parser("servir", help="donar computo a la malla")
    s.add_argument("--puerto", type=int, default=7337)
    s.add_argument("--hilos", type=int, default=4)
    s.add_argument("--cerebro", default="gguf")
    e = sub.add_parser("esperar", help="(interno) sondear una tarea delegada")
    e.add_argument("par")
    e.add_argument("ident")
    e.add_argument("nombre")
    sub.add_parser("cuenta", help="segundos donados y consumidos")
    a = ap.parse_args(argv)

    if a.orden == "servir":
        clave = _config().get("clave", "")
        if not clave:
            print(f"falta la clave compartida: crea {CONFIG} con "
                  '{"clave": "...", "pares": []}')
            return 2
        servir(a.puerto, clave, a.hilos, a.cerebro)
        return 0
    if a.orden == "esperar":
        return esperar(a.par, a.ident, a.nombre)
    if a.orden == "cuenta":
        c = cuenta()
        print(f"donados: {c.get('donados', 0)} s · consumidos: "
              f"{c.get('consumidos', 0)} s")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
