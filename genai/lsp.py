"""Cliente LSP: lo que `grep` no puede saber.

**Por qué existe.** `grep pagar` encuentra la palabra; no sabe si son la misma función,
un método homónimo de otra clase o una cadena en un comentario. Para renombrar en veinte
ficheros, encontrar las referencias REALES de un símbolo o ver un error de tipos antes
de ejecutar nada, hace falta alguien que haya parseado el proyecto. Eso es un servidor
de lenguaje, y hablarlos es un protocolo, no una biblioteca: JSON-RPC con cabecera
`Content-Length` sobre stdio. Cabe en este fichero y **no añade dependencias** — el
proyecto tiene una y se queda con una.

`docs/arquitectura.md` cita el uso de LSP de OpenCode como inspiración desde el primer
día; esto es esa deuda.

**Las tres decisiones que lo hacen usable aquí:**

1. **El servidor se reutiliza.** Arrancar uno cuesta segundos y indexar el proyecto más;
   pagarlo en cada llamada haría la herramienta inservible con un cerebro que ya tarda
   530 s por vuelta. Se arranca uno por (proyecto, lenguaje) y vive lo que viva el
   proceso.
2. **Si no hay servidor, se DICE cuál instalar.** Nunca se devuelve «no encontré nada»
   cuando lo cierto es «no hay quien busque»: esa confusión hace que el modelo concluya
   que un símbolo no se usa en ninguna parte.
3. **Solo lectura.** Definición, referencias y diagnósticos. Renombrar en veinte
   ficheros lo hace el agente con `editar`, que pasa por permisos y deja diff. Un
   `workspace/applyEdit` silencioso no.
"""
from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import threading
import time
from pathlib import Path

# Servidores conocidos, por extensión. El primero que esté instalado gana.
SERVIDORES = {
    ".py": [("pylsp", ["pylsp"], "pip install python-lsp-server"),
            ("pyright", ["pyright-langserver", "--stdio"], "npm i -g pyright"),
            ("jedi", ["jedi-language-server"], "pip install jedi-language-server")],
    ".ts": [("typescript", ["typescript-language-server", "--stdio"],
             "npm i -g typescript-language-server typescript")],
    ".js": [("typescript", ["typescript-language-server", "--stdio"],
             "npm i -g typescript-language-server typescript")],
    ".rs": [("rust-analyzer", ["rust-analyzer"], "rustup component add rust-analyzer")],
    ".go": [("gopls", ["gopls"], "go install golang.org/x/tools/gopls@latest")],
    ".c": [("clangd", ["clangd"], "apt install clangd")],
    ".cpp": [("clangd", ["clangd"], "apt install clangd")],
}
SERVIDORES[".tsx"] = SERVIDORES[".ts"]
SERVIDORES[".jsx"] = SERVIDORES[".js"]
SERVIDORES[".h"] = SERVIDORES[".c"]

ESPERA_INICIO = 60.0      # segundos para el arranque + indexado inicial
ESPERA_PETICION = 20.0


class Servidor:
    """Un servidor de lenguaje vivo, hablando JSON-RPC por stdio."""

    def __init__(self, orden: list[str], raiz: Path):
        self.raiz = raiz
        self.proc = subprocess.Popen(
            orden, cwd=str(raiz), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        self._id = 0
        self._lock = threading.Lock()
        self._abiertos: set[str] = set()
        self._pedir("initialize", {
            "processId": os.getpid(),
            "rootUri": raiz.as_uri(),
            "workspaceFolders": [{"uri": raiz.as_uri(), "name": raiz.name}],
            "capabilities": {
                "textDocument": {
                    "definition": {"linkSupport": False},
                    "references": {},
                    "publishDiagnostics": {},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": False},
                },
                "workspace": {"workspaceFolders": True},
            },
        }, espera=ESPERA_INICIO)
        self._avisar("initialized", {})

    # ── el protocolo: cabecera Content-Length + cuerpo JSON ────────────────
    def _enviar(self, msg: dict) -> None:
        cuerpo = json.dumps(msg).encode("utf-8")
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(cuerpo) + cuerpo)
        self.proc.stdin.flush()

    def _esperar(self, hasta: float) -> bool:
        """¿Hay algo que leer antes del plazo?

        Sin esto el plazo es DECORATIVO: `read(1)` sobre una tubería bloquea, así que
        mirar el reloj entre lecturas no sirve de nada y un servidor que se queda mudo
        cuelga al agente para siempre. Costó una prueba colgada descubrirlo, y el
        `faulthandler` señalando esta línea exacta."""
        while True:
            resto = hasta - time.time()
            if resto <= 0 or self.proc.poll() is not None:
                return False
            if select.select([self.proc.stdout], [], [], min(resto, 0.2))[0]:
                return True

    def _leer(self, hasta: float) -> dict | None:
        """Un mensaje. Devuelve None si se agotó el tiempo o el servidor murió."""
        cab, largo = b"", 0
        while not cab.endswith(b"\r\n\r\n"):
            if not self._esperar(hasta):
                return None
            b = self.proc.stdout.read(1)
            if not b:
                return None
            cab += b
        for linea in cab.decode("utf-8", "replace").split("\r\n"):
            if linea.lower().startswith("content-length:"):
                largo = int(linea.split(":", 1)[1])
        datos = b""
        while len(datos) < largo:
            if not self._esperar(hasta):
                return None
            trozo = self.proc.stdout.read(largo - len(datos))
            if not trozo:
                return None
            datos += trozo
        try:
            return json.loads(datos.decode("utf-8", "replace"))
        except ValueError:
            return None

    def _avisar(self, metodo: str, params: dict) -> None:
        self._enviar({"jsonrpc": "2.0", "method": metodo, "params": params})

    def _pedir(self, metodo: str, params: dict, espera: float = ESPERA_PETICION):
        """Petición con respuesta. Se descartan las notificaciones que lleguen en
        medio —diagnósticos, progreso— salvo que sean lo que se está esperando."""
        with self._lock:
            self._id += 1
            ident = self._id
            self._enviar({"jsonrpc": "2.0", "id": ident, "method": metodo,
                          "params": params})
            hasta = time.time() + espera
            while True:
                msg = self._leer(hasta)
                if msg is None:
                    return None
                if msg.get("id") == ident:
                    return msg.get("result")
                if msg.get("method") == "workspace/configuration":
                    # algunos servidores BLOQUEAN hasta que se les contesta
                    self._enviar({"jsonrpc": "2.0", "id": msg["id"], "result": [{}]})

    # ── documentos ─────────────────────────────────────────────────────────
    def abrir(self, f: Path) -> str:
        uri = f.as_uri()
        if uri not in self._abiertos:
            self._avisar("textDocument/didOpen", {"textDocument": {
                "uri": uri, "languageId": f.suffix.lstrip("."), "version": 1,
                "text": f.read_text(encoding="utf-8", errors="replace")}})
            self._abiertos.add(uri)
        return uri

    def diagnosticos(self, f: Path, espera: float = 15.0) -> list[dict]:
        """Los diagnósticos llegan como NOTIFICACIÓN, no como respuesta: hay que
        abrir el fichero y escuchar hasta que el servidor los publique."""
        uri = f.as_uri()
        self._abiertos.discard(uri)
        self.abrir(f)
        hasta = time.time() + espera
        while True:
            msg = self._leer(hasta)
            if msg is None:
                return []
            if (msg.get("method") == "textDocument/publishDiagnostics"
                    and (msg.get("params") or {}).get("uri") == uri):
                return msg["params"].get("diagnostics") or []

    def cerrar(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.proc.kill()


# Un servidor por (raíz, lenguaje). Arrancarlo cuesta segundos e indexar más; con un
# cerebro que tarda 530 s por vuelta, pagarlo en cada llamada lo haría inservible.
_VIVOS: dict[tuple[str, str], Servidor] = {}


def para(f: Path) -> tuple[Servidor | None, str]:
    """Devuelve (servidor, queja). Si no hay ninguno instalado, la queja dice cuál."""
    cands = SERVIDORES.get(f.suffix.lower())
    if not cands:
        return None, (f"no sé qué servidor de lenguaje usar para «{f.suffix}». "
                      f"Conocidos: {', '.join(sorted(SERVIDORES))}.")
    raiz = _raiz(f)
    for nombre, orden, comose in cands:
        if not shutil.which(orden[0]):
            continue
        clave = (str(raiz), nombre)
        vivo = _VIVOS.get(clave)
        if vivo and vivo.proc.poll() is None:
            return vivo, ""
        try:
            s = Servidor(orden, raiz)
        except Exception as e:  # noqa: BLE001
            return None, f"«{nombre}» está instalado pero no arrancó: {e}"
        _VIVOS[clave] = s
        return s, ""
    receta = " · ".join(f"{n}: `{c}`" for n, _, c in cands)
    return None, (f"no hay servidor de lenguaje para {f.suffix} en esta máquina, así "
                  f"que no puedo responder esto de verdad — y decir «no encontré nada» "
                  f"sería mentir. Instala uno: {receta}")


def _raiz(f: Path) -> Path:
    """La raíz del proyecto: donde estén las marcas habituales, o el directorio."""
    marcas = ("pyproject.toml", "setup.py", "setup.cfg", ".git", "package.json",
              "Cargo.toml", "go.mod", "tsconfig.json")
    d = f.resolve().parent
    for cand in [d, *d.parents]:
        if any((cand / m).exists() for m in marcas):
            return cand
    return d


def cerrar_todos() -> None:
    for s in _VIVOS.values():
        s.cerrar()
    _VIVOS.clear()
