"""base.py — qué es una herramienta y por qué son de grano grueso.

LA REGLA DE DISEÑO (META.md §puerta 3)
--------------------------------------
Cada vuelta del bucle cuesta el prefill del contexto entero más la generación. Con un
cerebro a 1-3 tokens/s, **una vuelta cuesta segundos o minutos**. En Claude Code una
herramienta fina (leer una línea, aplicar un cambio) es gratis; aquí no lo es.

De ahí la regla: **una herramienta hace el trabajo entero de un paso**. `editar` acepta
una lista de cambios y los aplica todos o ninguno; `buscar` devuelve símbolos con su
contexto, no números de línea que obliguen a una segunda llamada. Diez llamadas finas
que un modelo grande haría en tres segundos aquí son diez minutos.

DOS INVARIANTES QUE NO SE NEGOCIAN
----------------------------------
1. **La salida cabe.** Toda herramienta trunca a `MAX_SALIDA` caracteres y dice que
   truncó. Una salida de 200 KB no «llena el contexto»: lo destruye, y encima el modelo
   ni se entera de que le falta la mitad.
2. **El error es información, no una excepción.** Una herramienta que falla devuelve un
   `Resultado(ok=False)` con el motivo en un lenguaje que el modelo pueda accionar. Que
   el arnés reviente por un fichero inexistente convierte un tropiezo en una carrera
   perdida.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

MAX_SALIDA = 12_000        # caracteres, ~3 K tokens: el 10 % de un contexto de 32 K


@dataclass
class Resultado:
    ok: bool
    salida: str
    # Datos para el arnés (no para el modelo): rutas tocadas, códigos, cifras.
    datos: dict = field(default_factory=dict)

    def recortado(self, tope: int = MAX_SALIDA) -> str:
        if len(self.salida) <= tope:
            return self.salida
        mitad = tope // 2
        omitido = len(self.salida) - tope
        return (self.salida[:mitad] +
                f"\n\n[… {omitido} caracteres omitidos: la salida no cabía. "
                "Acota la petición (una ruta, un patrón más estrecho, menos líneas) "
                "en vez de repetir esta llamada …]\n\n" +
                self.salida[-mitad:])


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict                       # JSON Schema, tal cual va al modelo
    funcion: Callable[..., Resultado]
    # Escribe en disco, corre procesos o toca la red → pasa por permisos.py
    peligrosa: bool = False
    # Ejecuta un comando de shell que viene en los argumentos → pasa por el veto duro
    # y la lista blanca IGUAL que bash. Un plugin (M5.4) que corra shell y no lo
    # declare es un agujero: por eso permisos.py también mira este campo, no solo el
    # nombre de las herramientas de fábrica.
    ejecuta_shell: bool = False

    def firma(self) -> dict:
        """La definición que ve el modelo, en formato Hermes/OpenAI."""
        return {"type": "function",
                "function": {"name": self.nombre,
                             "description": self.descripcion,
                             "parameters": self.parametros}}


class Registro:
    """El conjunto de herramientas de una sesión.

    Es un objeto y no un diccionario global a propósito: dos sesiones pueden tener
    permisos distintos, y una herramienta prestada de una sesión a otra sería un agujero.
    """

    def __init__(self, herramientas: list[Herramienta] | None = None):
        self._por_nombre: dict[str, Herramienta] = {}
        for h in herramientas or []:
            self.registrar(h)

    def registrar(self, h: Herramienta) -> None:
        if h.nombre in self._por_nombre:
            raise ValueError(f"herramienta duplicada: {h.nombre}")
        self._por_nombre[h.nombre] = h

    def __contains__(self, nombre: str) -> bool:
        return nombre in self._por_nombre

    def __getitem__(self, nombre: str) -> Herramienta:
        return self._por_nombre[nombre]

    def __len__(self) -> int:
        return len(self._por_nombre)

    def firmas(self) -> list[dict]:
        return [h.firma() for h in self._por_nombre.values()]

    def invocar(self, nombre: str, argumentos: dict) -> Resultado:
        if nombre not in self._por_nombre:
            disponibles = ", ".join(sorted(self._por_nombre))
            return Resultado(False, f"no existe la herramienta «{nombre}». "
                                    f"Las que hay: {disponibles}")
        h = self._por_nombre[nombre]
        try:
            return h.funcion(**argumentos)
        except TypeError as e:
            # Argumentos que no casan con la firma: es el fallo más común de un modelo
            # pequeño, y se le devuelve tal cual para que corrija en la vuelta siguiente.
            return Resultado(False, f"argumentos inválidos para «{nombre}»: {e}. "
                                    f"Espera: {list(h.parametros.get('properties', {}))}")
        except Exception as e:                                # noqa: BLE001
            return Resultado(False, f"«{nombre}» falló: {type(e).__name__}: {e}")
