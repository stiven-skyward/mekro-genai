"""nucleo/ — el bucle, la sesión y los permisos. Nada de esto sabe qué modelo hay detrás."""
from .bucle import Resultado, turno
from .permisos import Decision, Politica, preguntar_por_consola
from .sesion import Sesion

__all__ = ["turno", "Resultado", "Sesion", "Politica", "Decision", "preguntar_por_consola"]
