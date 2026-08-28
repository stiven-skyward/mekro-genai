#!/usr/bin/env python3
"""sondear_append.py — la sonda barata de C22: ¿extiende de verdad el append-exacto?

C20 dejó dos ramas medidas en el `generate` del motor: con divergencia, «partial kv
removal not supported, re-evaluating full prompt»; con extensión exacta, «prefix-match
hit». Esta sonda hace hablar al motor (`verbose`) mientras el camino incremental de
`CerebroGGUF` genera la segunda vuelta de un bucle de juguete, y NO se fía del reloj
solo: exige ver el hit escrito.

Ojo: aquí no se exige identidad de salida con la instancia fresca, y no por descuido.
El contexto append-exacto es DELIBERADAMENTE otro prompt —conserva el razonamiento crudo
y los tokens especiales—, así que comparar salidas compara manzanas con peras. La
corrección la vigila el verificador del banco en la medición (tareas_pct 100).

Contrato de ciclo.py:

    CIFRA reutilizo 1|0       — la que decide: el motor imprimió «prefix-match hit»
    CIFRA aceleracion <x>     — segundos de la instancia fresca / segundos incremental

    python3 scripts/sondear_append.py
"""
from __future__ import annotations

import contextlib
import gc
import io
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

    print("── instancia A: primera generación (frío, inevitable)")
    a = CerebroGGUF()
    r1 = a.generar(m1, HERRAMIENTAS, max_tokens=96)
    print(f"   {r1.uso.tokens_entrada} tok entrada · {r1.uso.tokens_salida} tok salida · "
          f"{r1.uso.segundos} s · llamadas: {[l.firma() for l in r1.llamadas]}")

    m2 = m1 + [
        Mensaje("asistente", r1.texto, llamadas=r1.llamadas,
                razonamiento=r1.razonamiento),
        Mensaje("herramienta",
                "$ cat suma.py\ndef sumar(a, b):\n    return a - b\n",
                id_llamada=r1.llamadas[0].id if r1.llamadas else ""),
    ]

    print("── instancia A: segunda generación (append-exacto, lo que se sonda)")
    a._llm.verbose = True                      # que el motor diga qué rama toma
    parlanchin = io.StringIO()
    with contextlib.redirect_stderr(parlanchin):
        r2i = a.generar(m2, HERRAMIENTAS, max_tokens=96)
    a._llm.verbose = False
    dicho = parlanchin.getvalue()
    reutilizo = "prefix-match hit" in dicho
    print(f"   {r2i.uso.tokens_entrada} tok entrada · {r2i.uso.tokens_salida} tok salida"
          f" · {r2i.uso.segundos} s")
    print(f"   el motor dijo: {[l for l in dicho.splitlines() if 'Llama.generate' in l]}")

    del a
    gc.collect()

    print("── instancia B (fresca): mismo estado de bucle, prefill entero")
    b = CerebroGGUF()
    r2f = b.generar(m2, HERRAMIENTAS, max_tokens=96)
    print(f"   {r2f.uso.tokens_entrada} tok entrada · {r2f.uso.tokens_salida} tok salida"
          f" · {r2f.uso.segundos} s")

    acel = r2f.uso.segundos / r2i.uso.segundos if r2i.uso.segundos > 0 else 0.0
    print(f"\nCIFRA reutilizo {1 if reutilizo else 0}")
    print(f"CIFRA aceleracion {acel:.2f}")
    return 0 if reutilizo else 1


if __name__ == "__main__":
    raise SystemExit(main())
