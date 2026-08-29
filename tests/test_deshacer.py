"""deshacer.py — el checkpoint por turno, y que `turno()` lo alimente solo.

Lo que un cerebro que no se puede reintentar necesita de esto, verificado en dos
capas: (1) el módulo por sí solo —guardar, listar, restaurar, y el caso especial de
un fichero que no existía—, y (2) que `nucleo.turno()` REALMENTE dispare el guardado
al tocar un fichero, sin que nadie se lo pida explícitamente.
"""
import json
import os
import tempfile
from pathlib import Path

from _util import Cuenta

from genai import deshacer
from genai.cerebro import cargar
from genai.herramientas import estandar
from genai.nucleo import Politica, Sesion, turno

c = Cuenta("deshacer")
tmp = Path(tempfile.mkdtemp(prefix="deshacer-"))
os.environ["MG_DESHACER"] = str(tmp / "d")


def _llamada(nombre, **args):
    return "<tool_call>\n" + json.dumps({"name": nombre, "arguments": args}) + "\n</tool_call>"


# ── el módulo solo: guardar/listar/restaurar ────────────────────────────────
c(deshacer.guardar("sX", "algo", {}) is None,
  "un snapshot vacío no se guarda: nada que deshacer, nada que archivar")

ruta_guardada = deshacer.guardar("sX", "cambié un fichero", {"a.txt": "contenido viejo"})
c(ruta_guardada is not None and ruta_guardada.is_file(), "un snapshot no vacío sí se archiva")

puntos = deshacer.listar("sX")
c(len(puntos) == 1 and puntos[0]["encargo"] == "cambié un fichero",
  "listar() trae el encargo que originó el punto de control")
c(puntos[0]["ficheros"] == ["a.txt"], "y qué ficheros toca, sin el contenido (eso es pesado)")

ok, msg, fallo = deshacer.deshacer_ultimo("sY")
c(not ok and "no hay nada" in msg, "deshacer sobre una sesión sin puntos se rechaza, no revienta")

# ── restaurar de verdad, incluyendo el caso "no existía": se borra, no queda vacío ──
(tmp / "existente.txt").write_text("nuevo", encoding="utf-8")
deshacer.guardar("sZ", "dos ficheros", {
    str(tmp / "existente.txt"): "viejo",
    str(tmp / "nuevo.txt"): None,       # no existía antes de este turno
})
(tmp / "nuevo.txt").write_text("se creó en el turno", encoding="utf-8")

ok, encargo, restaurados = deshacer.deshacer_ultimo("sZ")
c(ok and encargo == "dos ficheros", "deshacer_ultimo() devuelve el encargo que se deshizo")
c(set(restaurados) == {str(tmp / "existente.txt"), str(tmp / "nuevo.txt")},
  "y la lista de rutas tocadas por ese punto de control")
c((tmp / "existente.txt").read_text() == "viejo",
  "el fichero que ya existía vuelve a su contenido de antes")
c(not (tmp / "nuevo.txt").exists(),
  "el fichero que NO existía antes del turno se BORRA, no queda un fichero vacío")
c(deshacer.listar("sZ") == [], "el punto de control se consume: no se reaplica dos veces")

# ── el punto más caro: turno() alimenta esto SOLO, sin que nadie lo pida ────
d2 = tmp / "proyecto"
d2.mkdir()
(d2 / "obj.txt").write_text("original\n", encoding="utf-8")

guion = [
    _llamada("editar", ruta=str(d2 / "obj.txt"),
             cambios=[{"buscar": "original", "poner": "modificado"}]),
    "hecho.",
]
s = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion), id="s-turno")
r = turno(s, estandar(), Politica(modo="todo"), "modifica obj.txt",
         traza_por_pantalla=False)
c(r.motivo == "fin", "el turno de prueba termina normal")
c((d2 / "obj.txt").read_text() == "modificado\n", "y el fichero sí quedó cambiado")

puntos_turno = deshacer.listar("s-turno")
c(len(puntos_turno) == 1, "turno() guardó su propio punto de control sin que nadie "
                         "llamara a deshacer.guardar() a mano")
ok3, _, _ = deshacer.deshacer_ultimo("s-turno")
c(ok3, "y ese punto de control restaura de verdad")
c((d2 / "obj.txt").read_text() == "original\n",
  "obj.txt vuelve a su contenido de antes del turno, vía la ruta real end-to-end")

raise SystemExit(c.fin())
