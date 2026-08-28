"""memoria/ — el contexto que se reconstruye.

El sistema vive en la raíz del repositorio (`holograma.py`, `ciclo.py`) porque es
también la herramienta de trabajo del humano y de la sesión de Claude Code que ayuda a
construir esto. Aquí se envuelve para que el ARNÉS pueda usarlo como herramienta: la
misma reconstrucción de contexto, a través del registro de herramientas.
"""
from .holos import HERRAMIENTAS

__all__ = ["HERRAMIENTAS"]
