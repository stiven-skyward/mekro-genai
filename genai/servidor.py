"""Servidor de sesiones: la separación cliente/servidor que arquitectura.md debía.

`docs/arquitectura.md` cita «la separación servidor/cliente de OpenCode» como
inspiración desde el primer día, igual que citaba el LSP. Esta es la otra deuda.

**Por qué importa más de lo que parece.** No es una API por tenerla: es lo que convierte
tres brechas en una. Con un servidor, *multi-sesión* es listar y adjuntarse, *compartir*
es exportar lo que el servidor ya sabe, y *cualquier editor* es un cliente más — una
extensión de VS Code no necesita reimplementar el arnés, solo hablar HTTP.

**Escucha en 127.0.0.1 y punto.** Lo contrario sería abrir un agente con permiso de
escritura a la red local. La malla (`malla.py`) sí sale fuera, pero eso es opt-in
declarado y con clave compartida; esto es infraestructura de escritorio y se queda en
casa. Para llegar desde otra máquina está SSH, que ya sabe hacer esto bien.

**Y aun así pide clave.** En una máquina compartida, «solo local» no es «solo tuyo»:
cualquier proceso del equipo puede hablar con 127.0.0.1. La clave se genera sola y se
guarda con permisos 600.
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
        if not self._autorizado():
            return self._responder(401, {"error": "clave incorrecta o ausente "
                                                  "(cabecera X-Genai-Clave)"})
        if r.path == "/sesiones":
            return self._responder(200, {"sesiones": sesiones.listar()})
        if r.path == "/conflictos":
            return self._responder(200, {"conflictos": [
                {"fichero": f, "sesiones": ids} for f, ids in sesiones.conflictos()]})
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
        return self._responder(404, {"error": f"no hay ruta {r.path}"})


def _transcripcion(ident: str) -> dict:
    """La conversación guardada, si la hay. El servidor no la reconstruye: la lee."""
    for d in (Path("logs") / "sesiones", Path(".genai") / "transcripciones"):
        for f in sorted(d.glob(f"*{ident}*.json")) if d.is_dir() else []:
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return {"mensajes": [], "aviso": "esta sesión aún no ha guardado transcripción"}


def servir(puerto: int = PUERTO, bloquear: bool = True) -> ThreadingHTTPServer:
    _Manejador.clave = clave()
    _Manejador.proyecto = Path.cwd()
    # 127.0.0.1 y no 0.0.0.0: lo contrario abre un agente con permiso de escritura a
    # la red local. Para llegar desde fuera está SSH, que ya sabe hacer esto bien.
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _Manejador)
    if not bloquear:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    print(f"servidor de sesiones en http://127.0.0.1:{srv.server_address[1]}")
    print(f"  proyecto: {Path.cwd()}")
    print(f"  clave:    {FICHERO_CLAVE}  (cabecera X-Genai-Clave)")
    print("  rutas:    GET /salud /sesiones /sesiones/<id> /sesiones/<id>/transcripcion")
    print("            GET /conflictos · POST /sesiones · POST /sesiones/<id>/"
          "{tomar,soltar,latido}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nservidor parado")
    return srv
