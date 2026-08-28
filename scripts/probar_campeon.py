#!/usr/bin/env python3
"""probar_campeon.py — hacerle una pregunta al modelo, en CPU, capa a capa desde disco.

    python3 scripts/probar_campeon.py --modelo /home/forge/modelos/qwen38-h13b \
        --prompt "..." --tokens 40

Imprime cada token en cuanto sale (a este ritmo, ver la respuesta aparecer es la única
forma de saber que la cosa va bien sin esperar al final) y cierra con las cifras.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai.cerebro.motor import MotorDenso      # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--modelo", default="/home/forge/modelos/qwen38-h13b")
    p.add_argument("--prompt", default="¿Qué es la cuantización de modelos de lenguaje?")
    p.add_argument("--sistema", default="")
    p.add_argument("--tokens", type=int, default=40)
    p.add_argument("--temperatura", type=float, default=0.0)
    p.add_argument("--crudo", action="store_true", help="sin plantilla de chat")
    p.add_argument("--hilos", type=int, default=0)
    a = p.parse_args()

    t0 = time.time()
    motor = MotorDenso(a.modelo, hilos=a.hilos)

    if a.crudo:
        prompt = a.prompt
    else:
        msgs = ([{"role": "system", "content": a.sistema}] if a.sistema else []) + \
               [{"role": "user", "content": a.prompt}]
        prompt = motor.tok.apply_chat_template(msgs, tokenize=False,
                                               add_generation_prompt=True)

    print(f"\n── modelo: {a.modelo}")
    print(f"── prompt: {a.prompt!r}\n")
    print("respuesta: ", end="", flush=True)

    def al_token(txt, paso, traza):
        print(txt, end="", flush=True)

    texto, traza = motor.generar(prompt, max_tokens=a.tokens,
                                 temperatura=a.temperatura, al_token=al_token)
    print("\n")
    seg = traza.seg_por_token
    print(f"CIFRA seg_por_token {seg:.3f}")
    print(f"CIFRA tokens_por_segundo {1 / seg if seg else 0:.4f}")
    print(f"CIFRA seg_prefill {traza.prefill_seg:.3f}")
    print(f"\n── {len(traza.segundos)} tokens · {seg:.1f} s/token "
          f"({1 / seg if seg else 0:.3f} tok/s) · prefill {traza.tokens_prompt} tokens en "
          f"{traza.prefill_seg:.1f} s · total {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
