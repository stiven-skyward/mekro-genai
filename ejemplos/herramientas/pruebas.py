"""Plugin de ejemplo, y el único que se envía: `pruebas` (M7.3).

Copia este fichero a `.genai/herramientas/` de tu proyecto (o a
`~/.config/genai/herramientas/` para todos) y el agente lo tendrá en la vuelta
siguiente. No hay registro que editar ni nada que reiniciar: el contrato entero es
«un `.py` que define `HERRAMIENTAS`». Ver docs/plugins.md.

**Por qué ESTA herramienta y no una de juguete.** Un plugin de ejemplo que sume dos
números demuestra que el mecanismo carga, y nada más. Este hace algo que el agente
necesita de verdad y que `bash` hace mal: correr la suite del proyecto y devolver **lo
que falló**, no las cuatrocientas líneas verdes. Es la brecha 6 y docs/ahorro.md en una
pieza — una salida que se reenvía en cada vuelta restante debe traer el veredicto y los
fallos, no el ruido.

Y es el ejemplo honesto de cómo se escribe un plugin: declara `ejecuta_shell=True`
porque corre un comando, y así `permisos.py` puede vigilarlo. Un plugin que corre shell
sin declararlo se salta el único guardia que hay.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from genai.herramientas.base import Herramienta, Resultado

# Se prueba en este orden y gana el primero que exista en el proyecto.
CORREDORES = [
    ("pytest", ["pytest", "-q", "--no-header"], ("pytest.ini", "pyproject.toml",
                                                 "setup.cfg", "tests", "test")),
    ("npm", ["npm", "test", "--silent"], ("package.json",)),
    ("cargo", ["cargo", "test", "-q"], ("Cargo.toml",)),
    ("go", ["go", "test", "./..."], ("go.mod",)),
    ("make", ["make", "test"], ("Makefile",)),
]


def _elegir(raiz: Path) -> tuple[str, list[str]] | None:
    for nombre, cmd, pistas in CORREDORES:
        if not any((raiz / p).exists() for p in pistas):
            continue
        if shutil.which(cmd[0]):
            return nombre, cmd
    return None


def pruebas(patron: str = "", ruta: str = ".") -> Resultado:
    raiz = Path(ruta).resolve()
    if not raiz.is_dir():
        return Resultado(False, f"no es un directorio: {ruta}")
    elegido = _elegir(raiz)
    if not elegido:
        return Resultado(False, "no encuentro cómo probar este proyecto (busco pytest, "
                                "npm, cargo, go o make). Si tiene otro corredor, lánzalo "
                                "con `bash`.")
    nombre, cmd = elegido
    if patron:
        cmd = cmd + (["-k", patron] if nombre == "pytest" else [patron])
    try:
        p = subprocess.run(cmd, cwd=raiz, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return Resultado(False, f"«{' '.join(cmd)}» pasó de 15 minutos y se cortó")
    except OSError as e:
        return Resultado(False, f"no se pudo lanzar {cmd[0]}: {e}")

    salida = (p.stdout + p.stderr).strip()
    lineas = salida.splitlines()
    # Lo que vuelve al contexto: el veredicto y los fallos con su contexto. El verde
    # de en medio dice lo mismo que la última línea y cuesta cien veces más.
    marcas = re.compile(r"\b(FAIL|FAILED|ERROR|Traceback|assert|panicked|✗|not ok)\b")
    interesa: set[int] = set()
    for i, l in enumerate(lineas):
        if marcas.search(l):
            interesa.update(range(max(0, i - 2), min(len(lineas), i + 15)))
    interesa.update(range(max(0, len(lineas) - 6), len(lineas)))

    fuera, ultimo = [], -2
    for i in sorted(interesa):
        if i > ultimo + 1:
            fuera.append("    […]")
        fuera.append(lineas[i])
        ultimo = i
    cuerpo = "\n".join(fuera)[:20_000]
    veredicto = "✓ la suite pasa" if p.returncode == 0 else "✗ la suite FALLA"
    return Resultado(
        p.returncode == 0,
        f"{veredicto}  ({nombre}, {len(lineas)} líneas de salida, "
        f"se muestran los fallos y el resumen)\n{cuerpo}",
        datos={"corredor": nombre, "codigo": p.returncode})


HERRAMIENTAS = [
    Herramienta(
        nombre="pruebas",
        descripcion=("Corre la suite del proyecto y devuelve QUÉ FALLÓ, no las líneas "
                     "verdes. Detecta pytest, npm, cargo, go o make. `patron` acota a "
                     "las pruebas cuyo nombre lo contenga. Úsala en vez de `bash` para "
                     "probar: trae el veredicto sin el ruido."),
        parametros={
            "type": "object",
            "properties": {
                "patron": {"type": "string",
                           "description": "acota a las pruebas que lo contengan"},
                "ruta": {"type": "string", "description": "raíz del proyecto (por "
                                                          "defecto, el directorio actual)"},
            },
        },
        funcion=pruebas,
        peligrosa=True,
        ejecuta_shell=True,   # corre un comando: permisos.py tiene que poder vigilarlo
    ),
]
