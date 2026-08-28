"""local_gguf.py — el cerebro de trabajo: un GGUF cuantizado corriendo en CPU.

QUÉ ES Y QUÉ NO ES
------------------
Es el **cerebro de trabajo** que META.md autoriza (§cerebro de trabajo, 2026-08-23): una
cuantización cualquiera del mismo Qwen3.8-27B que arranca hoy en CPU y RAM y permite
avanzar el arnés y el banco mientras H1 no exista. **NO es M1**, que sigue exigiendo el
campeón `qwen38-h13b` empaquetado con PPL ≤ +1 %.

Medido el 2026-08-23 sobre el corpus congelado `c6c95a4d`, ventanas de 512 y tokenización
verificada idéntica a la de `transformers` (512/512 tokens):

    Qwen3.8-27B-UD-Q2_K_XL.gguf · 9,15 GB · 2,83 bits
    PPL  4,7124 (código) · 10,5831 (español)      [BF16: 4,3781 y 9,5267]
    2,876 tok/s con 8 hilos · carga en 3-6 s por mmap

Para comparar: el campeón v13 da 9,8536 y 27,1130 sobre el mismo corpus, y hoy no se
puede ejecutar. Ver `holos/H1.md`.

LA CPU ES POR CONSTRUCCIÓN, NO POR OMISIÓN
-------------------------------------------
`n_gpu_layers=0` va fijado aquí y el motor se compiló con `GGML_CUDA=OFF`. La GPU está
vetada en este proyecto por decisión del autor: que un descuido la use sería un fallo
silencioso, así que se comprueba y se falla ruidosamente.

TRES TRAMPAS MEDIDAS, PARA QUE NADIE LAS REPITA
-----------------------------------------------
0. **`tokenize(special=False)` es el defecto de llama-cpp-python y desmonta la
   plantilla.** Con él, `<|im_start|>` entra como texto literal (17 tokens donde van 7
   en un turno mínimo, medido 2026-08-24) y el modelo nunca ve los tokens especiales con
   los que se entrenó. Aquí se tokeniza SIEMPRE con special=True (`_tokenizar`).
1. **`logits_all=True` cuesta un factor 26.** Existe para calcular perplejidad y obliga a
   producir los 248.320 logits en CADA posición: con él la generación cae de 2,876 a
   0,110 tok/s. Aquí va apagado.
2. **8 hilos, no 16.** La máquina tiene 16 hilos lógicos sobre 8 núcleos físicos, y
   pasarse los estorba.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Sequence

import json

from .base import Mensaje, Respuesta, Uso
from .plantilla import (INICIO, analizar_llamadas, montar, montar_uno,
                        separar_razonamiento)

GGUF = Path(os.environ.get(
    "MG_GGUF", "/home/forge/modelos/gguf/Qwen3.8-27B-UD-Q2_K_XL.gguf"))
FIN = "<|im_end|>"


class CerebroGGUF:
    """Un GGUF servido por llama.cpp, en CPU y RAM."""

    # 16.384 y no 8.192: C26 midió que doblar la ventana cuesta 0,5 GB (512 MiB de KV
    # por cada 8k más 149,6 MiB fijos de estado recurrente) y el modelo se entrenó a
    # 262.144. El límite práctico ya no es la RAM: es el reloj del prefill en frío.
    def __init__(self, ruta: Path | str = GGUF, contexto_max: int = 16384,
                 hilos: int = 0, temperatura: float = 0.0, semilla: int = 0,
                 cache_gb: float = 3.0):
        self.nombre = "gguf"
        self.ruta = Path(ruta)
        self.contexto_max = contexto_max
        # 8 hilos, no 16: los lógicos por encima de los físicos se estorban (medido)
        self.hilos = hilos or max(1, (os.cpu_count() or 8) // 2)
        self.temperatura = temperatura
        self.semilla = semilla
        # Caché de prefijo. Medido en la primera carrera del banco con cerebro real:
        # el 94,1 % del reloj era prefill REHECHO —10.526 tokens de entrada frente a 471
        # de salida—, y el prefill cuesta 0,247 s por token, casi lo mismo que generar.
        # Ninguno de los dos se puede acelerar en esta máquina: generar está limitado por
        # la memoria y el prefill por el cómputo. La única palanca es no rehacerlo, y se
        # puede porque entre dos vueltas el contexto sólo crece por el final.
        # `cache_gb` queda por compatibilidad, pero NO se usa: LlamaRAMCache guarda y
        # restaura el estado completo en cada llamada y eso cuesta cientos de MB por
        # vuelta. Medido en C19: devolvía 324 s de los 1.605 que prometía la aritmética.
        # Lo que sí funciona es no reiniciar el contexto (C20).
        self.cache_gb = cache_gb
        self._llm = None
        # CONTEXTO APPEND-EXACTO (C22). C20 midió que la caché de este GGUF no admite
        # borrado parcial (`kv_cache_seq_rm` → false): cualquier divergencia entre lo
        # cacheado y lo que se remonta fuerza re-evaluar el prompt ENTERO (3.359,5 s la
        # carrera de humo). La única reutilización posible es que la secuencia nueva
        # EXTIENDA exactamente la cacheada: aquí se guardan los tokens que la caché
        # contiene —razonamiento crudo incluido— y la huella de los mensajes que
        # representan, para montar solo el sufijo en la vuelta siguiente.
        self._ids_contexto: list[int] = []
        self._huellas: list[tuple | None] = []  # None = nuestro turno crudo de asistente
        # Streaming (M5.5): si alguien pone aquí un callable(str), recibe cada trozo
        # decodificable según se genera. Atributo y no parámetro: el protocolo Cerebro
        # no cambia y los demás cerebros ni se enteran.
        self.al_token = None
        # --sin-pensar (M3/C79): apagar el think en TODAS las vueltas del bucle. Es el
        # único mando que actúa en cada carrera por construcción, no según el camino.
        self.pensar = True

    # ── carga perezosa: `cargar("gguf")` no debe costar 9 GB ────────────────
    def _cargar(self):
        if self._llm is not None:
            return self._llm
        if not self.ruta.exists():
            raise SystemExit(
                f"no existe el GGUF {self.ruta}.\n"
                "  Descárgalo con el token de ~/.config/quantmodels/hf_tokens.env o\n"
                "  apunta MG_GGUF a otro fichero .gguf del mismo modelo.")
        try:
            from llama_cpp import Llama
        except ImportError:
            raise SystemExit(
                "falta el motor: pip install llama-cpp-python\n"
                "  OBLIGATORIO compilarlo sin CUDA en este proyecto:\n"
                '  CMAKE_ARGS="-DGGML_CUDA=OFF -DGGML_NATIVE=ON" pip install llama-cpp-python')
        self._llm = Llama(
            model_path=str(self.ruta), n_ctx=self.contexto_max, n_threads=self.hilos,
            n_gpu_layers=0,          # la GPU está vetada: cero, y no negociable
            logits_all=False,        # con él la generación cae ×26 (medido)
            seed=self.semilla, verbose=False)
        return self._llm

    @staticmethod
    def _huella(m: Mensaje) -> tuple:
        """Con qué se decide que un mensaje viejo NO cambió. Si compactar() u otra mano
        reescribe por el medio, la huella difiere y se vuelve al arranque en frío: más
        lento, nunca incorrecto."""
        return (m.rol, m.contenido, m.id_llamada,
                tuple((ll.nombre, json.dumps(ll.argumentos, sort_keys=True,
                                             ensure_ascii=False))
                      for ll in m.llamadas))

    def _tokenizar(self, texto: str) -> list[int]:
        # special=True SIEMPRE: los marcadores <|im_start|>/<|im_end|> deben entrar como
        # UN token especial cada uno —el formato con el que Qwen se entrenó— y no como
        # texto literal (medido 2026-08-24: 17 tokens frente a 7 en un turno mínimo).
        # Además el camino incremental cierra nuestro turno con el <|im_end|> real, el
        # mismo token que el modelo emite como EOS: con special=False jamás casarían.
        return self._cargar().tokenize(texto.encode("utf-8"), add_bos=False, special=True)

    def _sufijo_incremental(self, mensajes: Sequence[Mensaje]) -> str | None:
        """El trozo de plantilla que EXTIENDE el contexto cacheado, o None si toca
        arrancar en frío. Exige que los mensajes viejos estén intactos y que lo añadido
        venga DESPUÉS de nuestro último turno de asistente (que ya vive en la caché con
        sus tokens crudos, razonamiento incluido: re-plantillarlo divergiría)."""
        n = len(self._huellas)
        if not self._ids_contexto or n == 0 or len(mensajes) <= n:
            return None
        for m, h in zip(mensajes[:n - 1], self._huellas[:n - 1]):
            if self._huella(m) != h:
                return None
        if mensajes[n - 1].rol != "asistente":   # el hueco de nuestro turno crudo
            return None
        partes = [FIN + "\n"]                     # cerrar nuestro turno en la caché
        partes += [montar_uno(m) for m in mensajes[n:]]
        partes.append(f"{INICIO}assistant\n")
        return "".join(partes)

    def generar(self, mensajes: Sequence[Mensaje], herramientas: Sequence[dict] = (),
                max_tokens: int = 512, pensar: bool | None = None) -> Respuesta:
        llm = self._cargar()
        if pensar is None:
            pensar = self.pensar
        # PREFILL INCREMENTAL APPEND-EXACTO (C20 → C22). La caché de este GGUF no admite
        # borrado parcial, así que solo hay dos caminos honestos: (a) la secuencia nueva
        # extiende EXACTAMENTE la cacheada y se evalúa solo el sufijo, o (b) arranque en
        # frío re-evaluando todo. Nada de podas: divergió → frío.
        # `pensar=False` solo existe en el camino frío: el incremental es el del bucle
        # agéntico, donde el think crudo es parte de la caché y se queda.
        sufijo = self._sufijo_incremental(mensajes) if pensar else None
        if sufijo is not None:
            entrada_ids = self._ids_contexto + self._tokenizar(sufijo)
        else:
            entrada_ids = self._tokenizar(montar(mensajes, herramientas, pensar=pensar))
        n_entrada = len(entrada_ids)
        if n_entrada + max_tokens > self.contexto_max:
            raise SystemExit(
                f"el contexto son {n_entrada} tokens y el tope es {self.contexto_max}: "
                "no se trunca en silencio, porque un contexto recortado por el principio "
                "borra el prompt del sistema y el modelo deja de saber qué herramientas "
                "tiene. Sube contexto_max o recorta la transcripción antes.")
        t0 = time.time()
        piezas, n_salida, parada = [], 0, "fin"
        # OJO con `reset`: NO significa «no reinicies». El cotejo de prefijo vive DENTRO
        # de `if reset and self.n_tokens > 0:` y pone reset=False él mismo; pasar
        # reset=False lo SALTA (medido: ×1,0). Con el sufijo append-exacto de arriba el
        # cotejo casa la caché entera y evalúa solo lo nuevo; si divergió, re-evalúa
        # todo él solo —más lento, nunca corrupto (identidad verificada en C20)—.
        visto = ""   # lo ya entregado al oyente de streaming (M5.5)
        try:
            for tk in llm.generate(entrada_ids, temp=self.temperatura, reset=True):
                if tk == llm.token_eos():
                    break
                piezas.append(tk)
                n_salida += 1
                # streaming (M5.5): el oyente es un atributo, no un parámetro — así el
                # protocolo Cerebro no cambia y eco sigue intacto. Se entrega el DELTA
                # decodificable (detokenizar pieza a pieza rompería el UTF-8 multibyte).
                if self.al_token is not None:
                    texto_hasta = llm.detokenize(piezas).decode("utf-8", "ignore")
                    if len(texto_hasta) > len(visto):
                        self.al_token(texto_hasta[len(visto):])
                        visto = texto_hasta
                if n_salida >= max_tokens:
                    parada = "tope_tokens"
                    break
                # el fin de turno de Hermes puede no ser el EOS del modelo
                if len(piezas) % 8 == 0 and FIN in llm.detokenize(piezas).decode("utf-8", "ignore"):
                    break
        except KeyboardInterrupt:
            # Ctrl-C limpio (M5.5): lo generado hasta aquí se conserva, el motivo se
            # dice, y la sesión guardada permite retomar con --continuar. Morir con
            # traceback a mitad de generación era perder el trabajo del turno.
            parada = "interrumpido"
        crudo = llm.detokenize(piezas).decode("utf-8", "ignore").split(FIN)[0]
        segundos = time.time() - t0
        # La caché queda con lo pedido más lo generado, razonamiento crudo incluido: ese
        # es el alquiler que paga C22 a cambio de no re-evaluar nada. El hueco de nuestro
        # turno se marca con None; la sesión lo cubrirá con su asistente re-plantillado,
        # que a propósito NO se coteja por contenido (diverge del crudo y no importa).
        self._ids_contexto = entrada_ids + piezas
        self._huellas = [self._huella(m) for m in mensajes] + [None]
        razon, visible = separar_razonamiento(crudo)
        prosa, llamadas, quejas = analizar_llamadas(visible)
        if quejas:
            prosa = (prosa + "\n" + "\n".join(quejas)).strip()
        return Respuesta(texto=prosa, llamadas=llamadas, razonamiento=razon,
                         motivo_parada=parada,
                         uso=Uso(tokens_entrada=n_entrada, tokens_salida=n_salida,
                                 segundos=round(segundos, 3)))

    def contar_tokens(self, texto: str) -> int:
        return len(self._tokenizar(texto))

    def tokens_en_contexto(self) -> int:
        """Los tokens REALES que la caché arrastra — think crudo incluido. C72 murió
        dos veces porque todo conteo desde la transcripción montada EXCLUYE ese think
        (montar no lo remonta a propósito), y el desbordamiento ocurre contra este
        número, no contra aquel."""
        return len(self._ids_contexto)

    def olvidar(self) -> None:
        """Tras un renacimiento: la transcripción nueva no casa con la caché de todos
        modos (huellas), y dejar el contexto viejo apuntado haría que el conteo vivo
        siguiera enorme y disparara renaceres en cadena."""
        self._ids_contexto = []
        self._huellas = []
