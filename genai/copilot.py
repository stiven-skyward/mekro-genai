"""GitHub Copilot: entrar con tu cuenta en vez de con una clave de API.

**Cómo funciona, en dos pasos.** El *device flow* de GitHub está documentado y es el
mismo que usa cualquier herramienta sin navegador: se pide un código, tú lo tecleas en
`github.com/login/device`, y se sondea hasta que autorizas. Con el token de GitHub se
pide después un token de Copilot, que es el que vale para la API y **caduca en
minutos**, así que se renueva solo.

**Lo que hay que decir y no adornar.** Este es el camino que usan los clientes de
Copilot que no son de GitHub: se presenta con el identificador de cliente del editor.
Funciona, y es lo que hace OpenCode, pero *no* es una integración que GitHub bendiga
para terceros. Necesitas una suscripción activa de Copilot, la usas bajo sus términos, y
si GitHub cierra esta puerta dejará de funcionar sin previo aviso. Con una clave de API
de cualquier otro proveedor no tienes esa incertidumbre.

**El token no se guarda con el resto de claves.** Va a su propio fichero con permisos
600, porque no es una clave que tú escribiste sino una credencial de sesión que este
programa obtuvo en tu nombre: mezclarlas haría que borrar una borrase la otra.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# El identificador público del cliente de Copilot para editores. No es un secreto —va
# en el binario de cualquier editor— pero sí es la parte que hace esto no-oficial.
CLIENTE = "Iv1.b507a08c87ecfe98"
DEVICE = "https://github.com/login/device/code"
TOKEN = "https://github.com/login/oauth/access_token"
CANJE = "https://api.github.com/copilot_internal/v2/token"
API = "https://api.githubcopilot.com"
FICHERO = Path(os.environ.get("MG_COPILOT",
                              Path.home() / ".config" / "genai" / "copilot.json"))
AGENTE = "GitHubCopilotChat/0.26.7"


def _post(url: str, datos: dict, cabeceras: dict | None = None) -> dict:
    cuerpo = urllib.parse.urlencode(datos).encode()
    cab = {"Accept": "application/json", "User-Agent": AGENTE,
           "Content-Type": "application/x-www-form-urlencoded", **(cabeceras or {})}
    with urllib.request.urlopen(urllib.request.Request(url, cuerpo, cab),
                                timeout=30) as r:
        return json.loads(r.read())


def _get(url: str, cabeceras: dict) -> dict:
    cab = {"Accept": "application/json", "User-Agent": AGENTE, **cabeceras}
    with urllib.request.urlopen(urllib.request.Request(url, headers=cab),
                                timeout=30) as r:
        return json.loads(r.read())


def _guardar(d: dict) -> None:
    import os
    FICHERO.parent.mkdir(parents=True, exist_ok=True)
    FICHERO.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.chmod(FICHERO, 0o600)


def _leer() -> dict:
    try:
        return json.loads(FICHERO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def entrar(imprimir=print) -> tuple[bool, str]:
    """Device flow completo. Bloquea hasta que autorizas o se agota el plazo."""
    try:
        d = _post(DEVICE, {"client_id": CLIENTE, "scope": "read:user"})
    except urllib.error.HTTPError as e:
        return False, f"GitHub rechazó la petición inicial: {e.code} {e.reason}"
    except OSError as e:
        return False, f"no se pudo hablar con GitHub: {e}"
    if "device_code" not in d:
        return False, f"respuesta inesperada de GitHub: {str(d)[:200]}"

    imprimir(f"\n  1. Abre  {d.get('verification_uri', 'https://github.com/login/device')}")
    imprimir(f"  2. Teclea el código:  {d['user_code']}")
    imprimir("  3. Esperando a que autorices…\n")

    espera = max(int(d.get("interval", 5)), 1)
    limite = time.time() + int(d.get("expires_in", 900))
    while time.time() < limite:
        time.sleep(espera)
        try:
            r = _post(TOKEN, {"client_id": CLIENTE, "device_code": d["device_code"],
                              "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        except OSError:
            continue                       # un tropiezo de red no cancela la espera
        if r.get("access_token"):
            _guardar({"github": r["access_token"]})
            return True, "sesión de GitHub guardada"
        err = r.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            espera += int(r.get("interval", 5))
            continue
        if err == "expired_token":
            return False, "el código caducó; vuelve a intentarlo"
        if err == "access_denied":
            return False, "cancelaste la autorización"
        return False, f"GitHub devolvió «{err}»: {r.get('error_description', '')}"
    return False, "se agotó el plazo sin autorizar"


def token() -> tuple[str, str]:
    """Token de Copilot válido, renovándolo si toca. Devuelve (token, queja)."""
    d = _leer()
    if not d.get("github"):
        return "", ("no has entrado en GitHub. Ejecuta `genai copilot entrar` "
                    "(hace falta una suscripción activa de Copilot).")
    # El token de Copilot caduca en minutos; se renueva con 60 s de margen para que no
    # caduque a mitad de una petición larga.
    if d.get("copilot") and d.get("caduca", 0) - 60 > time.time():
        return d["copilot"], ""
    try:
        r = _get(CANJE, {"Authorization": f"token {d['github']}"})
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "", ("GitHub aceptó tu cuenta pero no da token de Copilot "
                        f"({e.code}). Lo habitual es no tener suscripción activa, o "
                        f"que la organización no lo permita para herramientas de "
                        f"terceros.")
        return "", f"GitHub respondió {e.code} {e.reason} al pedir el token de Copilot"
    except OSError as e:
        return "", f"no se pudo pedir el token de Copilot: {e}"
    if not r.get("token"):
        return "", f"respuesta sin token: {str(r)[:200]}"
    d["copilot"], d["caduca"] = r["token"], r.get("expires_at", time.time() + 1500)
    _guardar(d)
    return d["copilot"], ""


def estado() -> str:
    d = _leer()
    if not d.get("github"):
        return "sin sesión de GitHub"
    t, q = token()
    if not t:
        return f"sesión de GitHub guardada, pero {q}"
    queda = int(d.get("caduca", 0) - time.time())
    return f"listo · token de Copilot válido {max(queda, 0)} s más"


def salir() -> str:
    FICHERO.unlink(missing_ok=True)
    return "sesión de Copilot borrada"


def config() -> dict:
    """Config para `CerebroNube`, con el token ya renovado."""
    t, q = token()
    if not t:
        raise SystemExit(q)
    return {"dialecto": "openai", "url": API, "clave": t,
            "modelo": "gpt-4.1", "cabeceras": {
                "Editor-Version": "vscode/1.99.0",
                "Copilot-Integration-Id": "vscode-chat",
                "User-Agent": AGENTE}}
