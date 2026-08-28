"""Punto de entrada: `python3 -m genai` y el comando instalado `genai` caen aquí.

Hasta 2026-08-28 este fichero llevaba su PROPIA copia del argparse, con `tarea`,
`version` y `malla` — y era la única CLI que `pip install -e .` instalaba de verdad,
porque `pyproject.toml` registra `genai = "genai.__main__:main"`. Mientras tanto,
`genai/cli.py` había crecido con todo lo nuevo (proveedores, cerebros, mcp, google,
copilot, sesiones), pero solo era alcanzable con `python3 -m genai.cli`: invisible para
cualquiera que instalara el paquete y usara el comando `genai` a secas.

Ahora hay una sola CLI, en `genai/cli.py`, con las dos mitades fusionadas. Este fichero
es solo el reexport que hace que las tres formas de invocar el mismo código.
"""
from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
