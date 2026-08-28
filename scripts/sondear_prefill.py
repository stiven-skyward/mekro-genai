#!/usr/bin/env python3
"""sondear_prefill.py — la sonda barata de C20: ¿el prefill incremental es INOCUO?

C19 dejó el aviso: un prefijo común mal calculado corrompe el contexto EN SILENCIO y el
modelo sigue respondiendo, solo que peor. Por eso esta sonda va ANTES que el reloj: si la
salida incremental no es bit a bit la misma que la de rehacer el prefill entero a
temperatura 0, el número de la carrera no significa nada.

Qué hace, en tres pasos y unos minutos de CPU:

1. Instancia A: genera sobre unos mensajes cortos (m1). Luego genera sobre m1 + su propia
   respuesta + una observación de herramienta (m2). Esta segunda llamada es la
   incremental: `Llama.generate` reutiliza el prefijo común que ya tiene en la caché KV.
2. Instancia B, recién cargada (la A se libera antes, que la RAM es el muro): genera
   sobre m2 desde cero. Es la referencia sin nada que reutilizar.
3. Compara texto, razonamiento y llamadas. Idénticos o corrupto, no hay término medio.

Contrato de ciclo.py:

    CIFRA identidad 1|0        — la que decide: 0 = contexto corrupto, parar C20
    CIFRA aceleracion <x>      — segundos de B / segundos de A en la llamada incremental

    python3 scripts/sondear_prefill.py
"""
from __future__ import annotations

import gc
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from genai.cerebro.base import Mensaje                 # noqa: E402
from genai.cerebro.local_gguf import CerebroGGUF       # noqa: E402

SISTEMA = """Eres Mekro-Genai, un agente de ingeniería. Trabajas en el directorio actual.
Verifica con `bash` lo que afirmes. Cuando la tarea esté hecha, responde sin llamadas."""

HERRAMIENTAS = [{
    "name": "bash",
    "description": "Ejecuta un comando de shell y devuelve su salida.",
    "parameters": {"type": "object", "properties": {
        "comando": {"type": "string"}}, "required": ["comando"]},
}]


def main() -> int:
    m1 = [
        Mensaje("sistema", SISTEMA),
        Mensaje("usuario", "El fichero suma.py tiene un bug: sumar(2, 3) devuelve -1. "
                           "Míralo con bash y dime qué harías."),
    ]

    print("── instancia A: primera generación (prefill completo, inevitable)")
    a = CerebroGGUF()
    r1 = a.generar(m1, HERRAMIENTAS, max_tokens=96)
    print(f"   {r1.uso.tokens_entrada} tok entrada · {r1.uso.tokens_salida} tok salida · "
          f"{r1.uso.segundos} s · llamadas: {[l.firma() for l in r1.llamadas]}")

    # La transcripción crece SOLO por el final, como en el bucle real del arnés.
    m2 = m1 + [
        Mensaje("asistente", r1.texto, llamadas=r1.llamadas),
        Mensaje("herramienta",
                "$ cat suma.py\ndef sumar(a, b):\n    return a - b\n",
                id_llamada=r1.llamadas[0].id if r1.llamadas else ""),
    ]

    print("── instancia A: segunda generación (prefill INCREMENTAL, lo que se sonda)")
    r2i = a.generar(m2, HERRAMIENTAS, max_tokens=96)
    print(f"   {r2i.uso.tokens_entrada} tok entrada · {r2i.uso.tokens_salida} tok salida · "
          f"{r2i.uso.segundos} s")

    # La RAM es el muro: fuera la A antes de cargar la B.
    del a
    gc.collect()

    print("── instancia B (fresca): misma entrada, prefill entero desde cero")
    b = CerebroGGUF()
    r2f = b.generar(m2, HERRAMIENTAS, max_tokens=96)
    print(f"   {r2f.uso.tokens_entrada} tok entrada · {r2f.uso.tokens_salida} tok salida · "
          f"{r2f.uso.segundos} s")

    identicos = (r2i.texto == r2f.texto
                 and r2i.razonamiento == r2f.razonamiento
                 and [(l.nombre, l.argumentos) for l in r2i.llamadas]
                     == [(l.nombre, l.argumentos) for l in r2f.llamadas])
    if not identicos:
        print("\n✗ LAS SALIDAS DIFIEREN — contexto corrupto, el reloj de C20 no vale")
        print(f"  incremental: {r2i.razonamiento[:200]!r} · {r2i.texto[:200]!r}")
        print(f"  desde cero:  {r2f.razonamiento[:200]!r} · {r2f.texto[:200]!r}")

    acel = r2f.uso.segundos / r2i.uso.segundos if r2i.uso.segundos > 0 else 0.0
    print(f"\nCIFRA identidad {1 if identicos else 0}")
    print(f"CIFRA aceleracion {acel:.2f}")
    return 0 if identicos else 1


if __name__ == "__main__":
    raise SystemExit(main())
