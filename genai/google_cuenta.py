"""Entrar con tu cuenta de Google y usar la cuota de tu suscripción, no una clave.

**Qué es esto.** Google AI Pro/Ultra —y también la cuenta gratuita— traen cuota de
*Code Assist*, que es la que usa `gemini-cli`. Entrando con tu cuenta se usa esa cuota
en vez de pagar tokens de la API. La clave de AI Studio sigue funcionando y no se toca:
esto es una alternativa, no un reemplazo.

**Lo que hay que decir y no adornar.** Este es el camino que usan los clientes de
terceros: se presenta con el identificador de cliente de `gemini-cli` y habla con su
mismo endpoint. Esas credenciales **no vienen en este repositorio** —no son nuestras
para redistribuirlas, y GitHub rechazó con razón el primer intento de subirlas—: se
leen de tu gemini-cli, de una variable de entorno o de tu configuración. Funciona, pero
**no es una integración que Google bendiga para terceros**. La suscripción está pensada
para los clientes de Google; la API existe para el uso programático. Puede cortarse sin
aviso. Con una clave de AI Studio no tienes esa incertidumbre, y tiene nivel gratuito.

**Por qué el flujo es de bucle local y no de dispositivo.** El flujo de dispositivo de
Google no admite el ámbito `cloud-platform` que hace falta aquí. Así que se levanta un
servidor en 127.0.0.1, se abre el navegador, y Google devuelve el código ahí. En WSL
funciona porque el navegador de Windows alcanza el localhost de la distribución; si no
llegara, se puede pegar la URL de vuelta a mano, que es la salida que este módulo
ofrece cuando el navegador no puede.

**El `state` no es decorativo.** Sin comprobarlo, cualquier página que tengas abierta
podría mandar a tu servidor local un código suyo y dejarte con la sesión de otro. Se
genera al azar y se verifica.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# ── las credenciales del cliente NO viven en este repositorio ─────────────────
#
# Hacen falta las de una aplicación instalada de Google (las de `gemini-cli`). En una
# aplicación instalada el «secreto» no es confidencial —va dentro del binario y Google
# lo dice así— pero **no son nuestras para redistribuirlas**, y un repositorio público
# que las lleve dentro se convierte en un sitio más donde viven. El escáner de secretos
# de GitHub rechazó el primer intento de subirlas, y tenía razón.
#
# Así que se buscan, por este orden, en sitios que son del USUARIO:
#   1. las variables GENAI_GOOGLE_CLIENTE / GENAI_GOOGLE_SECRETO
#   2. ~/.config/genai/google_cliente.json
#   3. una instalación de gemini-cli en esta máquina
CLIENTE_FICHERO = Path.home() / ".config" / "genai" / "google_cliente.json"


def _pareja_valida(cid: str, sec: str) -> bool:
    """¿Son pareja? Se le pregunta a Google con un código inventado: si el cliente y el
    secreto casan, se queja del CÓDIGO («invalid_grant»); si no, del CLIENTE. No
    autoriza nada ni toca ninguna cuenta."""
    datos = urllib.parse.urlencode({
        "client_id": cid, "client_secret": sec, "code": "no-existe",
        "grant_type": "authorization_code", "redirect_uri": "http://localhost:1"}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://oauth2.googleapis.com/token", datos,
            {"Content-Type": "application/x-www-form-urlencoded"}), timeout=20)
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}").get("error") == "invalid_grant"
        except ValueError:
            return False
    except OSError:
        return False
    return False


def _de_gemini_cli() -> tuple[str, str]:
    """Saca las credenciales de un gemini-cli instalado, si lo hay."""
    import re
    import shutil
    import subprocess
    exe = shutil.which("gemini")
    raices = []
    if exe:
        try:
            real = Path(subprocess.run(["readlink", "-f", exe], capture_output=True,
                                       text=True, timeout=10).stdout.strip() or exe)
            raices.append(real.parent.parent)
        except OSError:
            pass
    raices += [Path.home() / ".npm-global" / "lib" / "node_modules",
               Path("/usr/lib/node_modules"), Path("/usr/local/lib/node_modules")]
    for r in raices:
        for f in list(r.glob("**/@google/gemini-cli*/**/*.js"))[:400]:
            try:
                t = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # gemini-cli lleva DOS client_id y un solo secreto: coger el primero de
            # cada uno los empareja mal y Google responde «client secret is invalid».
            # Se empareja por CERCANÍA en el fichero, que es donde el código los define
            # juntos, y luego se verifica contra Google — que es lo único que lo zanja.
            for m_sec in re.finditer(r"GOCSPX-[A-Za-z0-9_\-]{20,}", t):
                cerca = sorted(
                    re.finditer(r"[0-9]{6,}-[a-z0-9]{10,}\.apps\.googleusercontent\.com", t),
                    key=lambda m: abs(m.start() - m_sec.start()))
                for m_cid in cerca[:3]:
                    if _pareja_valida(m_cid.group(0), m_sec.group(0)):
                        return m_cid.group(0), m_sec.group(0)
    return "", ""


def credenciales() -> tuple[str, str, str]:
    """(cliente, secreto, queja). Sin ellas no hay flujo posible, y se dice cómo."""
    cid = os.environ.get("GENAI_GOOGLE_CLIENTE", "")
    sec = os.environ.get("GENAI_GOOGLE_SECRETO", "")
    if not (cid and sec) and CLIENTE_FICHERO.is_file():
        try:
            d = json.loads(CLIENTE_FICHERO.read_text(encoding="utf-8"))
            cid, sec = d.get("cliente", cid), d.get("secreto", sec)
        except ValueError:
            pass
    if not (cid and sec):
        cid, sec = _de_gemini_cli()
        if cid and sec:
            CLIENTE_FICHERO.parent.mkdir(parents=True, exist_ok=True)
            CLIENTE_FICHERO.write_text(
                json.dumps({"cliente": cid, "secreto": sec,
                            "de": "gemini-cli instalado en esta máquina"}, indent=1),
                encoding="utf-8")
            os.chmod(CLIENTE_FICHERO, 0o600)
    if not (cid and sec):
        return "", "", (
            "faltan las credenciales del cliente de Google, y no vienen en este "
            "repositorio a propósito: son de `gemini-cli`, no nuestras, y publicarlas "
            "aquí las esparciría.\n"
            "  Tres formas de darlas, la primera es la fácil:\n"
            "    1. instala gemini-cli (`npm i -g @google/gemini-cli`) y se leen solas\n"
            "    2. exporta GENAI_GOOGLE_CLIENTE y GENAI_GOOGLE_SECRETO\n"
            f"    3. escríbelas en {CLIENTE_FICHERO}\n"
            "  O usa una clave de AI Studio, que tiene nivel gratuito y no depende de "
            "nada de esto.")
    return cid, sec, ""


AMBITOS = ("https://www.googleapis.com/auth/cloud-platform "
           "https://www.googleapis.com/auth/userinfo.email "
           "https://www.googleapis.com/auth/userinfo.profile")
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
CANJE = "https://oauth2.googleapis.com/token"
ASIST = "https://cloudcode-pa.googleapis.com/v1internal"
FICHERO = Path.home() / ".config" / "genai" / "google.json"


def _post(url: str, datos: dict, cabeceras: dict | None = None, json_cuerpo=None) -> dict:
    if json_cuerpo is not None:
        cuerpo = json.dumps(json_cuerpo).encode()
        cab = {"Content-Type": "application/json", **(cabeceras or {})}
    else:
        cuerpo = urllib.parse.urlencode(datos).encode()
        cab = {"Content-Type": "application/x-www-form-urlencoded", **(cabeceras or {})}
    with urllib.request.urlopen(urllib.request.Request(url, cuerpo, cab),
                                timeout=60) as r:
        return json.loads(r.read())


def _guardar(d: dict) -> None:
    FICHERO.parent.mkdir(parents=True, exist_ok=True)
    FICHERO.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.chmod(FICHERO, 0o600)


def _leer() -> dict:
    try:
        return json.loads(FICHERO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class _Recogida(http.server.BaseHTTPRequestHandler):
    """Recoge el `code` que Google devuelve al navegador."""

    recibido: dict = {}

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Recogida.recibido = {k: v[0] for k, v in q.items()}
        ok = "code" in _Recogida.recibido
        cuerpo = (("<h2>Listo.</h2><p>Ya puedes cerrar esta pestaña y volver a la "
                   "terminal.</p>") if ok else
                  f"<h2>No salió bien.</h2><pre>{q}</pre>").encode()
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


def entrar(imprimir=print, espera: float = 300.0,
           abrir_navegador: bool = True) -> tuple[bool, str]:
    cid, sec, queja = credenciales()
    if queja:
        return False, queja
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Recogida)
    _Recogida.recibido = {}
    redirigir = f"http://localhost:{srv.server_address[1]}"
    estado = secrets.token_urlsafe(24)
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirigir, "response_type": "code",
        "scope": AMBITOS, "state": estado, "access_type": "offline",
        "prompt": "consent"})

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    imprimir("\n  Abre esto en tu navegador y entra con tu cuenta de Google:\n")
    imprimir(f"  {url}\n")
    if abrir_navegador:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — sin navegador, la URL de arriba basta
            pass
    imprimir("  Esperando…  (si el navegador no puede llegar a esta máquina, pega "
             "aquí\n   la URL completa a la que te redirigió y pulsa intro)\n")

    limite = time.time() + espera
    while time.time() < limite and not _Recogida.recibido:
        time.sleep(0.5)
    srv.shutdown()

    r = _Recogida.recibido
    if not r:
        return False, "se agotó el plazo sin autorizar"
    if r.get("error"):
        return False, f"Google devolvió «{r['error']}»"
    # Sin esta comprobación, cualquier página abierta podría mandarle a tu servidor
    # local un código suyo y dejarte con la sesión de otra cuenta.
    if r.get("state") != estado:
        return False, ("el `state` no coincide: la respuesta no venía de la petición "
                       "que se hizo. No se guarda nada.")
    return canjear(r["code"], redirigir)


def canjear(codigo: str, redirigir: str) -> tuple[bool, str]:
    cid, sec, queja = credenciales()
    if queja:
        return False, queja
    try:
        t = _post(CANJE, {"client_id": cid, "client_secret": sec,
                          "code": codigo, "grant_type": "authorization_code",
                          "redirect_uri": redirigir})
    except urllib.error.HTTPError as e:
        d = json.loads(e.read() or b"{}")
        return False, f"Google rechazó el canje: {d.get('error_description', e.reason)}"
    except OSError as e:
        return False, f"no se pudo canjear el código: {e}"
    if not t.get("refresh_token"):
        return False, ("Google no dio `refresh_token`. Suele pasar si ya habías "
                       "autorizado antes; vuelve a intentarlo (se pide `prompt=consent` "
                       "justo para evitarlo).")
    _guardar({"refresco": t["refresh_token"], "acceso": t.get("access_token", ""),
              "caduca": time.time() + int(t.get("expires_in", 3500)),
              "redirigir": redirigir})
    return True, "sesión de Google guardada"


def acceso() -> tuple[str, str]:
    """Token de acceso válido, renovándolo si toca. Devuelve (token, queja)."""
    d = _leer()
    if not d.get("refresco"):
        return "", ("no has entrado con Google. Ejecuta `genai google entrar`.\n"
                    "  (o usa una clave de AI Studio, que tiene nivel gratuito y no "
                    "depende de esto)")
    if d.get("acceso") and d.get("caduca", 0) - 60 > time.time():
        return d["acceso"], ""
    cid, sec, queja = credenciales()
    if queja:
        return "", queja
    try:
        t = _post(CANJE, {"client_id": cid, "client_secret": sec,
                          "refresh_token": d["refresco"], "grant_type": "refresh_token"})
    except urllib.error.HTTPError as e:
        c = json.loads(e.read() or b"{}")
        if c.get("error") == "invalid_grant":
            return "", ("Google invalidó la sesión (contraseña cambiada, permiso "
                        "revocado o mucho tiempo sin usarla). Vuelve a entrar: "
                        "`genai google entrar`")
        return "", f"no se pudo renovar el acceso: {c.get('error_description', e.reason)}"
    except OSError as e:
        return "", f"no se pudo renovar el acceso: {e}"
    d["acceso"] = t.get("access_token", "")
    d["caduca"] = time.time() + int(t.get("expires_in", 3500))
    _guardar(d)
    return d["acceso"], ""


def proyecto() -> tuple[str, str]:
    """El proyecto de Code Assist de tu cuenta, que hace falta para generar."""
    d = _leer()
    if d.get("proyecto"):
        return d["proyecto"], ""
    tok, q = acceso()
    if not tok:
        return "", q
    try:
        r = _post(f"{ASIST}:loadCodeAssist",
                  {}, {"Authorization": f"Bearer {tok}"},
                  json_cuerpo={"metadata": {"pluginType": "GEMINI"}})
    except urllib.error.HTTPError as e:
        return "", (f"Code Assist respondió {e.code}. Lo habitual es que la cuenta no "
                    f"tenga la API activada o que la organización no lo permita.")
    except OSError as e:
        return "", f"no se pudo hablar con Code Assist: {e}"
    pid = r.get("cloudaicompanionProject") or ""
    if not pid:
        nivel = ((r.get("currentTier") or {}).get("id")
                 or (r.get("allowedTiers") or [{}])[0].get("id", "?"))
        return "", (f"Code Assist no devolvió proyecto (nivel «{nivel}»). Suele hacer "
                    f"falta aceptar los términos una vez en gemini-cli o en la consola.")
    d["proyecto"] = pid
    _guardar(d)
    return pid, ""


def estado() -> str:
    d = _leer()
    if not d.get("refresco"):
        return "sin sesión de Google"
    tok, q = acceso()
    if not tok:
        return f"sesión guardada, pero {q}"
    pid, q2 = proyecto()
    if not pid:
        return f"sesión válida, pero {q2}"
    queda = int(d.get("caduca", 0) - time.time())
    return f"listo · proyecto {pid} · acceso válido {max(queda, 0)} s más"


def salir() -> str:
    FICHERO.unlink(missing_ok=True)
    return "sesión de Google borrada"
