"""eco.py — un cerebro sin modelo, para medir el ARNÉS aislado.

No es un juguete ni un «mock» de pruebas unitarias: es un instrumento de medida. M0
(META.md) se declara con este cerebro precisamente porque **separa las dos fuentes de
fallo**. Si el banco falla con `eco`, el fallo está en el bucle, en las herramientas o
en los permisos; si pasa con `eco` y falla con el local, el fallo es del modelo y se
mide como tal. Sin esta separación, «el agente no resolvió la tarea» no dice nada.

Actúa según un **guion**: una lista de respuestas literales que emite en orden. Escribir
el guion de una tarea es escribir la traza ideal de esa tarea, y eso tiene un efecto
lateral que vale la pena: obliga a decidir cuál ES la traza ideal antes de exigírsela a
un modelo de 2 bits.
"""
from __future__ import annotations

import time
from typing import Sequence

from .base import Mensaje, Respuesta, Uso
from .plantilla import analizar_llamadas, montar, separar_razonamiento


class CerebroEco:
    """Emite el guion, en orden. Al agotarse, cierra el turno educadamente."""

    def __init__(self, guion: Sequence[str] = (), contexto_max: int = 32768,
                 nombre: str = "eco", latencia: float = 0.0):
        self.nombre = nombre
        self.contexto_max = contexto_max
        self.guion = list(guion)
        self.paso = 0
        # Latencia fingida: sirve para que las pruebas del bucle vean tiempos como los
        # del cerebro real (segundos por vuelta) sin cargar 8 GB de pesos.
        self.latencia = latencia

    def generar(self, mensajes: Sequence[Mensaje], herramientas: Sequence[dict] = (),
                max_tokens: int = 512) -> Respuesta:
        t0 = time.time()
        entrada = montar(mensajes, herramientas)
        if self.latencia:
            time.sleep(self.latencia)
        if self.paso < len(self.guion):
            crudo = self.guion[self.paso]
            self.paso += 1
        else:
            crudo = "Guion agotado: no queda nada que hacer."
        razon, visible = separar_razonamiento(crudo)
        prosa, llamadas, quejas = analizar_llamadas(visible)
        if quejas:
            # En `eco` una queja es un fallo del guion, no del modelo. Que se note.
            raise ValueError(f"guion mal escrito en el paso {self.paso}: {quejas}")
        uso = Uso(tokens_entrada=self.contar_tokens(entrada),
                  tokens_salida=self.contar_tokens(crudo),
                  segundos=round(time.time() - t0, 3))
        return Respuesta(texto=prosa, llamadas=llamadas, uso=uso, razonamiento=razon,
                         motivo_parada="herramienta" if llamadas else "fin")

    def contar_tokens(self, texto: str) -> int:
        """Aproximación honesta y declarada: ~4 caracteres por token. No pretende ser
        el tokenizador de Qwen; pretende no mentir con un 0."""
        return max(1, len(texto) // 4)
