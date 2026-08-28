"""local_stream.py — el campeón v13 leído capa a capa desde disco. Correcto y lentísimo.

QUÉ ES ESTO Y POR QUÉ EXISTE
----------------------------
`E:\\QuantModels\\modelos\\qwen38-h13b` son **51 GB de safetensors en bf16**: el
checkpoint está «deshecho» (fake-quant), es decir, cuantizado a 1,9995 bits y vuelto a
expandir a bf16 para poder medir su perplejidad. No hay códigos ni libros guardados en
disco; solo la receta, en `HERMETIC2.json`.

Consecuencia medida en esta máquina (2026-08-22): `/mnt/e` lee a **192 MB/s**, luego un
pase completo por los 51 GB cuesta **~4,4 minutos**. Generar un token exige un pase
completo. Es decir: **~4,4 min/token**. Una respuesta de 500 tokens serían 36 horas.

Por eso este backend NO es el cerebro del arnés. Es un instrumento de referencia:
sirve para responder «¿qué habría contestado el campeón?» en una tarea suelta y para
comparar contra `local_packed` cuando exista, comprobando que el empaquetado no cambió
la salida. Usarlo para trabajar es un error de categoría, y el propio módulo lo dice al
arrancar en vez de dejar que alguien lo descubra a las cuatro horas.

El cerebro de verdad es `local_packed` (~8 GB en RAM), y es el hito M1: holos/H1.md.

DEUDA TÉCNICA RECONOCIDA
------------------------
`quant/perplejidad.py` de QuantModels evalúa por capas en modo *teacher forcing*: mete
todas las ventanas de golpe por cada capa. Generar es lo contrario —un token depende del
anterior— y además necesita **caché KV**, que aquel arnés no tiene porque no le hacía
falta. Qwen3.8 ayuda: solo 16 de sus 64 capas son de atención (las demás son GatedDeltaNet,
recurrentes y de estado O(1)), así que la caché es cuatro veces más barata de lo normal.
Escribir ese bucle de generación es trabajo de este repositorio, no de QuantModels: H2.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Sequence

from .base import Mensaje, Respuesta, Uso

CAMPEON = Path(os.environ.get("MG_CAMPEON", "/mnt/e/QuantModels/modelos/qwen38-h13b"))
QUANTMODELS = Path(os.environ.get("MG_QUANTMODELS", "/mnt/e/QuantModels"))

# Medido con `dd` sobre capa-00.safetensors el 2026-08-22. Si alguien mueve el
# checkpoint a un SSD interno esto cambia, y hay que volver a medirlo, no suponerlo.
MB_POR_SEGUNDO = 192
GB_CHECKPOINT = 51


class CerebroStream:
    """Lee el checkpoint capa a capa. Un token cuesta un pase completo por el disco."""

    def __init__(self, ruta: Path | str = CAMPEON, contexto_max: int = 32768,
                 hilos: int = 0, permitir_lento: bool = False):
        self.nombre = "local_stream"
        self.ruta = Path(ruta)
        self.contexto_max = contexto_max
        self.hilos = hilos or os.cpu_count() or 8
        self.permitir_lento = permitir_lento
        self._tokenizador = None
        self._deposito = None

    # ── el aviso que ahorra cuatro horas ────────────────────────────────────
    def segundos_por_token(self) -> float:
        return GB_CHECKPOINT * 1024 / MB_POR_SEGUNDO

    def _comprobar(self) -> None:
        if not self.ruta.exists():
            raise SystemExit(f"no existe el checkpoint {self.ruta}. "
                             "¿Está montada E:? ¿Lo movió alguien?")
        if not self.permitir_lento:
            raise SystemExit(
                f"local_stream cuesta ~{self.segundos_por_token() / 60:.1f} min POR TOKEN "
                f"({GB_CHECKPOINT} GB a {MB_POR_SEGUNDO} MB/s en esta máquina).\n"
                "  No es el cerebro del arnés: es un instrumento de referencia.\n"
                "  Si de verdad quieres una carrera de horas, pásale permitir_lento=True\n"
                "  y lánzala desasida con su .pid en logs/. El cerebro de trabajo es\n"
                "  local_packed y es el hito M1: python3 holograma.py foco H1")

    def _cargar(self):
        """Reutiliza el lector de QuantModels en vez de reescribirlo: `DepositoPesos`
        ya sabe abrir estos safetensors en modo perezoso y encontrar el prefijo de las
        capas sin suponerlo."""
        if self._deposito is not None:
            return
        import sys
        if str(QUANTMODELS) not in sys.path:
            sys.path.insert(0, str(QUANTMODELS))
        try:
            from quant.carga import DepositoPesos          # type: ignore
        except ImportError as e:
            raise SystemExit(f"no se pudo importar quant.carga desde {QUANTMODELS}: {e}")
        from transformers import AutoTokenizer
        self._deposito = DepositoPesos(self.ruta)
        self._tokenizador = AutoTokenizer.from_pretrained(str(self.ruta))

    def generar(self, mensajes: Sequence[Mensaje], herramientas: Sequence[dict] = (),
                max_tokens: int = 512) -> Respuesta:
        self._comprobar()
        self._cargar()
        t0 = time.time()
        # El bucle autoregresivo con caché KV sobre pesos en streaming es H2. Aquí NO
        # se devuelve una respuesta falsa ni un texto de relleno: se falla ruidosamente.
        # Un cerebro que finge responder envenena cualquier medición que lo use.
        raise NotImplementedError(
            "el bucle de generación con caché KV está por escribir (holos/H2.md). "
            f"Prefill preparado en {time.time() - t0:.1f} s; falta el decode.")

    def contar_tokens(self, texto: str) -> int:
        self._cargar()
        return len(self._tokenizador(texto)["input_ids"])
