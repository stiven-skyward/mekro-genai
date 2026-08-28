"""bash.py — la herramienta que hace todo lo que no tiene herramienta propia.

Y por eso mismo es la peligrosa: `bash` es la superficie por la que un agente borra un
directorio. El control NO vive aquí sino en `nucleo/permisos.py`, que decide antes de
llamar. Aquí solo hay tres cosas que deben ser ciertas pase lo que pase:

1. **Tope de tiempo siempre.** Un comando sin `timeout` cuelga la sesión para siempre y
   —peor— cuelga una carrera nocturna que nadie mira hasta la mañana.
2. **La salida se recorta y se dice.** Un `find /` sin filtro no puede tumbar el contexto.
3. **Se devuelve el código de salida.** Un modelo pequeño se cree que algo funcionó si
   la salida está vacía; el código de salida es el dato que lo desmiente.
"""
from __future__ import annotations

import os
import subprocess

from .base import Herramienta, Resultado

TOPE_SEGUNDOS = 120


def correr(comando: str, cwd: str = ".", segundos: int = TOPE_SEGUNDOS) -> Resultado:
    segundos = min(int(segundos or TOPE_SEGUNDOS), 600)
    try:
        r = subprocess.run(comando, shell=True, cwd=cwd, capture_output=True,
                           text=True, timeout=segundos)
    except subprocess.TimeoutExpired:
        return Resultado(False, f"el comando pasó de {segundos} s y se cortó. "
                                "Si es un proceso largo, láncalo desasido con nohup y su "
                                ".pid en logs/, y consúltalo después.",
                         {"timeout": True})
    salida = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    salida = salida.strip() or "(sin salida)"
    # La ruta absoluta del directorio de trabajo cambia por carrera (es un temporal) y
    # C31 midió que ese ruido basta para divergir un guion a temperatura 0. En la
    # observación siempre es «.», que es como el agente lo conoce.
    salida = salida.replace(os.path.realpath(cwd), ".").replace(os.path.abspath(cwd), ".")
    return Resultado(r.returncode == 0,
                     f"$ {comando}\n[código {r.returncode}]\n{salida}",
                     {"codigo": r.returncode})


HERRAMIENTAS = [
    Herramienta(
        nombre="bash",
        descripcion=("Ejecuta un comando de shell y devuelve su salida y su código. "
                     f"Se corta a los {TOPE_SEGUNDOS} s. Encadena con && lo que sea un "
                     "solo paso: cada llamada cuesta una vuelta entera del bucle."),
        parametros={"type": "object", "properties": {
            "comando": {"type": "string"},
            "cwd": {"type": "string", "description": "directorio de trabajo"},
            "segundos": {"type": "integer", "description": f"tope, máximo 600 (por defecto {TOPE_SEGUNDOS})"}},
            "required": ["comando"]},
        funcion=correr, peligrosa=True,
        ejecuta_shell=True),
]
