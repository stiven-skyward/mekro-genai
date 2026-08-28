"""E/S cruda de la bitácora: una línea JSON por entrada."""
import json


def cargar(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def anotar(ruta, entrada):
    with open(ruta, "a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
