"""git como herramienta (M7.5), en un repositorio de juguete.

Lo que se vigila aquí no es que git funcione —funciona— sino los dos límites que hacen
que darle git a un agente no sea un accidente esperando:

1. que lo que **reescribe historia o publica** esté vetado y lo diga con claridad;
2. que la salida entre **podada**, porque un diff que se paga en cada vuelta restante
   debe traer lo que cambió y no el fichero entero (docs/ahorro.md).
"""
import os
import subprocess
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.herramientas import estandar
from genai.herramientas.git import PERMITIDOS, VETADOS, git

c = Cuenta("git")

# ── el veto, antes que nada ─────────────────────────────────────────────────
for prohibida in ("push", "reset", "rebase", "clean", "checkout"):
    r = git(prohibida)
    c(not r.ok and "no está permitida" in r.salida,
      f"«{prohibida}» está vetada: un agente que puede borrar trabajo ajeno no es "
      f"una herramienta")
c(not (set(PERMITIDOS) & set(VETADOS)),
  "ninguna acción está a la vez permitida y vetada: la lista no se contradice")
c(git("push").salida.count("persona") == 1,
  "y el rechazo dice de quién es la decisión, en vez de solo negarse")

# ── fuera de un repositorio, lo dice en vez de reventar ──────────────────────
antes = os.getcwd()
vacio = Path(tempfile.mkdtemp(prefix="git-sin-repo-"))
os.chdir(vacio)
r = git("estado")
os.chdir(antes)
c(not r.ok and "no hay repositorio" in r.salida,
  "sin repositorio, un motivo accionable y no una traza")

# ── un repositorio de juguete ───────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="git-prueba-"))
os.chdir(tmp)
for cmd in (["init", "-q"], ["config", "user.email", "p@p"], ["config", "user.name", "p"]):
    subprocess.run(["git", *cmd], capture_output=True)

(tmp / "a.py").write_text("uno = 1\n" * 300, encoding="utf-8")
r = git("estado")
c(r.ok and "a.py" in r.salida, "el estado ve el fichero nuevo")
c(len(r.salida) < 300,
  "y cabe en unas líneas: git para humanos imprime consejos que aquí se pagarían "
  "en cada vuelta")

r = git("commit", mensaje="primer commit de juguete")
c(r.ok, f"el commit se hace (dijo: {r.salida!r})")
c(not git("commit", mensaje="  ").ok,
  "un commit sin mensaje se rechaza: no sirve a quien lo lea mañana")
c(not git("commit", mensaje="nada que ver").ok,
  "y con el árbol limpio también, en vez de crear un commit vacío")

r = git("log", n=5)
c(r.ok and "primer commit" in r.salida, "el log muestra lo registrado")

# ── el diff entra podado: lo que cambió, no el fichero ──────────────────────
texto = (tmp / "a.py").read_text(encoding="utf-8").replace("uno = 1\n", "uno = 2\n", 1)
(tmp / "a.py").write_text(texto, encoding="utf-8")
r = git("diff")
os.chdir(antes)
c(r.ok and "uno = 2" in r.salida, "el diff trae la línea que cambió")
c(len(r.salida) < 600,
  "una línea cambiada de un fichero de 300 no cuesta 300 líneas: el diff ES poda "
  "en el origen, no una comodidad de presentación")

# ── el registro y los permisos ──────────────────────────────────────────────
reg = estandar()
c("git" in reg, "git está en el juego estándar")
c(reg["git"].peligrosa,
  "y es peligrosa: commit escribe, así que pasa por permisos.py como todo lo demás")
c(not getattr(reg["git"], "ejecuta_shell", False),
  "pero NO ejecuta shell: los argumentos van a subprocess como lista, nunca a un "
  "intérprete que pudiera expandirlos")

raise SystemExit(c.fin())
