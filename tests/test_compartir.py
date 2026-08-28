"""Compartir una sesión: un HTML autocontenido, y sobre todo TACHADO.

Compartir es publicar, y una transcripción guarda todo lo que el agente leyó. Si leyó
un `.env` o un `claves.json`, la clave está dentro. Filtrarla pasa justo cuando uno está
contento con el resultado y quiere enseñarlo.

Así que lo que se vigila es, por este orden:

1. que **no se escape ningún secreto conocido** — ocho familias, con el aserto puesto
   sobre el texto final, no sobre el contador;
2. que **se diga cuántos se tacharon**, porque tachar en silencio le oculta a quien
   comparte que su sesión llevaba credenciales;
3. que el fichero **no pida nada a ninguna red** al abrirse;
4. que el HTML no se pueda romper con el contenido de la conversación.
"""
import json
import re
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.compartir import PATRONES, a_html, exportar, tachar

c = Cuenta("compartir")
tmp = Path(tempfile.mkdtemp(prefix="comp-"))

# Los cebos se ARMAN POR PARTES a propósito: escritos enteros, un escáner de secretos
# los toma por credenciales de verdad. Lo comprobó GitHub rechazando el push de esta
# misma prueba por un «Slack API Token». Que un escáner ajeno muerda el anzuelo dice
# que los cebos son buenos; dejarlos literales en el repositorio, que serían un problema.
_R = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SECRETOS = {
    "clave de Anthropic": "sk-" + "ant-" + "api03-" + _R[:34],
    "clave de OpenAI": "sk-" + "proj-" + _R[:30],
    "clave de Google": "AIza" + "Sy" + _R[:34],
    "clave de Google (OAuth)": "AQ" + "." + "Ab8" + _R[:28],
    "token de GitHub": "gh" + "p_" + _R[:36],
    "token de Slack": "xo" + "xb-" + "1234567890-" + _R[:16].lower(),
    "clave de AWS": "AK" + "IA" + _R[:16],   # AKIA + exactamente 16
}

# ── 1. ni uno se escapa ────────────────────────────────────────────────────
for familia, secreto in SECRETOS.items():
    salida, cuenta = tachar(f"esto de aquí {secreto} y sigue el texto")
    c(secreto not in salida, f"NO se escapa: {familia}")
    c("[TACHADO:" in salida, f"y queda marcado dónde estaba: {familia}")

t, _ = tachar("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzzz")
c("eyJhbGciOi" not in t and "Authorization" in t,
  "una cabecera Authorization pierde el token pero conserva el nombre: quien lea el "
  "documento tiene que poder ver QUÉ había ahí")

t, _ = tachar("psql https://usuario:contrasena@base.example/x")
c("contrasena" not in t and "https://" in t,
  "una URL con credenciales pierde la contraseña y conserva el esquema")

t, _ = tachar("-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n"
              "-----END RSA PRIVATE KEY-----")
c("MIIEowIBAAK" not in t, "una clave privada entera desaparece, no solo su cabecera")

# ── 2. se dice cuántos, y de qué ───────────────────────────────────────────
_, cuenta = tachar(" ".join(SECRETOS.values()))
c(sum(cuenta.values()) >= len(SECRETOS),
  f"se cuentan todos los tachados (fueron {sum(cuenta.values())})")
c(len(cuenta) >= 6,
  "y se cuentan POR FAMILIA: saber que había una clave de AWS y otra de GitHub dice "
  "mucho más que saber que había dos secretos")

limpio, cuenta = tachar("aquí no hay nada raro, solo texto")
c(limpio == "aquí no hay nada raro, solo texto" and cuenta == {},
  "un texto sin secretos no se toca: tachar de más llena el documento de agujeros y "
  "acaba en que nadie mira los avisos")

c(not any(n.lower() in ("password", "secret", "token") for n, _ in PATRONES),
  "no hay patrones genéricos por palabra: «password» aparece en cualquier código y "
  "tacharlo sería ruido, no seguridad")

# ── el documento entero ────────────────────────────────────────────────────
sucia = {"inicio": "2026-08-28T10:00:00", "vueltas": 3, "intervenciones": 1,
         "uso": {"tokens_salida": 120, "tokens_entrada": 4000},
         "mensajes": [
             {"rol": "usuario", "contenido": f"usa {SECRETOS['clave de Anthropic']}"},
             {"rol": "herramienta",
              "contenido": "\n".join(SECRETOS.values())},
             {"rol": "asistente", "contenido": "hecho",
              "llamadas": [{"nombre": "bash", "argumentos": {
                  "comando": f"curl -H 'Authorization: Bearer "
                             f"{SECRETOS['token de GitHub']}'"}}]}]}
pagina, cuenta = a_html(sucia, "sesión sucia")
for familia, secreto in SECRETOS.items():
    c(secreto not in pagina, f"tampoco se escapa por el HTML: {familia}")
c("Se tacharon" in pagina and "no puede cazarlo todo" in pagina,
  "el documento avisa EN SU CABECERA de cuántos se tacharon y de que el tachado es de "
  "mejor esfuerzo: quien comparta tiene que mirar")

limpia = {"inicio": "x", "vueltas": 1, "uso": {}, "mensajes":
          [{"rol": "usuario", "contenido": "hola"}]}
p2, _ = a_html(limpia)
c("No se encontró ningún secreto" in p2 and "no</b> es garantía" in p2,
  "y si no había ninguno también se dice, avisando de que eso NO es garantía")

# ── 3. autocontenido ───────────────────────────────────────────────────────
c(not re.search(r'(?:src|href)\s*=|@import|fetch\(|<script', pagina),
  "ni un script, ni un src, ni un href, ni un @import: el fichero no pide nada a "
  "ninguna red al abrirse, que es toda la diferencia con subirlo al servidor de otro")
c("<style>" in pagina, "el estilo va dentro")

# ── 4. el contenido no puede romper el documento ───────────────────────────
malo = {"inicio": "x", "vueltas": 1, "uso": {}, "mensajes": [
    {"rol": "usuario",
     "contenido": "<script>alert(1)</script> y <img src=x onerror=alert(2)>"}]}
p3, _ = a_html(malo)
c("<script>alert" not in p3 and "&lt;script&gt;" in p3,
  "el contenido de la conversación se escapa: un fichero leído con HTML dentro no "
  "puede convertir el documento compartido en algo ejecutable")
c("onerror=alert" not in p3 or "&lt;img" in p3, "ni con atributos de evento")

# ── exportar deja un fichero, y solo eso ───────────────────────────────────
destino, cuenta = exportar(sucia, tmp / "s.html", "sucia")
c(destino.is_file() and destino.read_text(encoding="utf-8").startswith("<!doctype"),
  "exportar deja un HTML en disco")
c(sum(cuenta.values()) > 0, "y devuelve la cuenta de tachados a quien lo llamó")
fuente = (Path(__file__).resolve().parents[1] / "genai" / "compartir.py"
          ).read_text(encoding="utf-8")
c("urllib" not in fuente and "requests" not in fuente,
  "exportar NO sube nada a ninguna parte: publicar es una decisión humana y separada, "
  "y este módulo ni siquiera sabe hablar por red")

raise SystemExit(c.fin())
