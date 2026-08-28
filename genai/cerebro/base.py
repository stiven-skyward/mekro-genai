"""base.py — qué es un cerebro para este arnés, y qué se le exige.

El arnés NO se acopla a un modelo: se acopla a este protocolo. No es por elegancia ni
para poder escaparse a la nube cuando el local falle (META.md lo prohíbe explícitamente):
es porque **sin una referencia contra la que medir, «el cerebro local es peor» no es una
afirmación con cifra**. El backend `eco` permite medir el arnés sin modelo; el backend
local mide el modelo; la diferencia entre ambos es lo que se le puede achacar al cerebro.

La contabilidad de tokens y de segundos NO es opcional: META.md exige las cuatro cifras
en toda carrera, y tres de las cuatro nacen aquí.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable

ROLES = ("sistema", "usuario", "asistente", "herramienta")


@dataclass
class Mensaje:
    rol: str
    contenido: str
    # Solo en rol «asistente»: lo que el modelo pidió ejecutar.
    llamadas: list["Llamada"] = field(default_factory=list)
    # Solo en rol «herramienta»: a qué llamada responde.
    id_llamada: str = ""
    # El razonamiento NO vuelve al contexto en el turno siguiente (ver plantilla.py):
    # se guarda para la transcripción y para depurar, no para gastarlo otra vez.
    razonamiento: str = ""

    def __post_init__(self) -> None:
        if self.rol not in ROLES:
            raise ValueError(f"rol desconocido: {self.rol!r} (roles: {ROLES})")


@dataclass
class Llamada:
    nombre: str
    argumentos: dict
    id: str = ""

    def firma(self) -> str:
        """Cómo se enseña en pantalla y en los registros. Corta a propósito."""
        args = json.dumps(self.argumentos, ensure_ascii=False)
        return f"{self.nombre}({args[:120]}{'…' if len(args) > 120 else ''})"


@dataclass
class Uso:
    """Las tres cifras que META.md exige de toda generación."""
    tokens_entrada: int = 0
    tokens_salida: int = 0
    segundos: float = 0.0

    @property
    def tokens_por_segundo(self) -> float:
        return self.tokens_salida / self.segundos if self.segundos > 0 else 0.0

    def __add__(self, otro: "Uso") -> "Uso":
        return Uso(self.tokens_entrada + otro.tokens_entrada,
                   self.tokens_salida + otro.tokens_salida,
                   round(self.segundos + otro.segundos, 3))


@dataclass
class Respuesta:
    texto: str
    llamadas: list[Llamada]
    uso: Uso
    razonamiento: str = ""
    # Por qué paró: «fin», «tope_tokens», «herramienta». Cuando sea «tope_tokens» hay
    # que sospechar de todo lo demás: una llamada truncada parece válida y no lo es.
    motivo_parada: str = "fin"


@runtime_checkable
class Cerebro(Protocol):
    """Lo único que el núcleo sabe del modelo."""

    nombre: str
    contexto_max: int

    def generar(self, mensajes: Sequence[Mensaje], herramientas: Sequence[dict],
                max_tokens: int = 512) -> Respuesta:
        ...

    def contar_tokens(self, texto: str) -> int:
        """Necesario para la contabilidad de contexto ANTES de generar. Si el backend
        no sabe contar, que estime — pero que no mienta con un 0."""
        ...
