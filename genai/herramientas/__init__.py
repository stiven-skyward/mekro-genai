"""herramientas/ — lo que el cerebro puede hacer. Ver base.py para la regla del grano.

`estandar()` es el juego completo. Una sesión puede recortarlo: menos herramientas es
menos prompt de sistema en CADA vuelta, y con un cerebro caro eso se nota. Las firmas
de las once herramientas de Claude Code costarían aquí ~1.500 tokens por vuelta.
"""
from __future__ import annotations

from .base import Herramienta, Registro, Resultado

__all__ = ["Herramienta", "Registro", "Resultado", "estandar"]


def cargar_plugins() -> tuple[list[Herramienta], list[str]]:
    """El contrato de plugin (M5.4): un fichero .py en `.genai/herramientas/` del
    proyecto o en `~/.config/genai/herramientas/` que defina `HERRAMIENTAS = [...]`
    con el MISMO dataclass que los módulos de fábrica. Si corre shell, declara
    `ejecuta_shell=True` o permisos.py no podrá vigilarlo. Un plugin roto se salta y
    se DICE (segunda lista): tragárselo en silencio sería mentir sobre qué
    herramientas tiene el agente. Contrato completo: docs/plugins.md"""
    import importlib.util
    from pathlib import Path

    extras: list[Herramienta] = []
    quejas: list[str] = []
    directorios = [Path(".genai") / "herramientas",
                   Path.home() / ".config" / "genai" / "herramientas"]
    for d in directorios:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            try:
                espec = importlib.util.spec_from_file_location(f"plugin_{f.stem}", f)
                mod = importlib.util.module_from_spec(espec)
                espec.loader.exec_module(mod)
                nuevas = list(getattr(mod, "HERRAMIENTAS"))
                for h in nuevas:
                    if not isinstance(h, Herramienta):
                        raise TypeError(f"{h!r} no es una Herramienta")
                extras.extend(nuevas)
            except Exception as e:  # noqa: BLE001 — el plugin es código ajeno
                quejas.append(f"plugin {f} saltado: {type(e).__name__}: {e}")
    return extras, quejas


def estandar(incluir_peligrosas: bool = True, plugins: bool = True,
             malla: bool = False) -> Registro:
    from . import bash, buscar, ficheros, fondo
    todas: list[Herramienta] = []
    for modulo in (ficheros, buscar, bash, fondo):
        todas.extend(modulo.HERRAMIENTAS)
    if malla:
        # M6: delegar solo existe si el usuario encendió el modo malla. En local, el
        # agente ni sabe que la malla es una posibilidad — el defecto no cambia.
        from ..malla import HERRAMIENTAS as MALLA
        todas.extend(MALLA)
    if plugins:
        extras, quejas = cargar_plugins()
        nombres = {h.nombre for h in todas}
        for h in extras:
            if h.nombre in nombres:
                quejas.append(f"plugin «{h.nombre}» ignorado: pisa una herramienta "
                              "de fábrica")
                continue
            todas.append(h)
        for q in quejas:
            print(f"⚠ {q}")
    if not incluir_peligrosas:
        todas = [h for h in todas if not h.peligrosa]
    return Registro(todas)
