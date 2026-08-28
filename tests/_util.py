"""_util.py — asertos que se CUENTAN. Un test que solo devuelve 0 no dice cuánto probó.

La convención del ecosistema Mekro: la prueba imprime «N/N asertos» y falla ruidosamente
en el primero que se cae, con el porqué. Un `pytest -q` verde de un fichero vacío también
es verde.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Cuenta:
    def __init__(self, titulo: str):
        self.titulo = titulo
        self.n = 0
        self.fallos: list[str] = []

    def __call__(self, condicion, que: str) -> None:
        self.n += 1
        if not condicion:
            self.fallos.append(f"  ✗ {que}")

    def igual(self, obtenido, esperado, que: str) -> None:
        self.__call__(obtenido == esperado, f"{que} · obtenido {obtenido!r}, "
                                            f"esperado {esperado!r}")

    def fin(self) -> int:
        if self.fallos:
            print(f"{self.titulo}: {self.n - len(self.fallos)}/{self.n} asertos")
            print("\n".join(self.fallos))
            return 1
        print(f"{self.titulo}: {self.n}/{self.n} asertos ✓")
        return 0
