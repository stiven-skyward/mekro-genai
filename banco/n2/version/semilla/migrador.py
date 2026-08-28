"""Migra fichas v1 → v2 sobre fichas.jsonl, EN EL SITIO.

La v2 lleva `"v": 2`, los puntos en centésimas y el nivel derivado. Migrar es
una operación de mantenimiento: tiene que poder lanzarse las veces que haga
falta sin estropear lo ya migrado."""
import json

RUTA = "fichas.jsonl"


def cargar():
    with open(RUTA, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def guardar(fichas):
    with open(RUTA, "w", encoding="utf-8") as f:
        for ficha in fichas:
            f.write(json.dumps(ficha, ensure_ascii=False) + "\n")


def migrar():
    fichas = []
    for ficha in cargar():
        ficha["v"] = 2
        ficha["nivel"] = ficha["puntos"] // 10
        ficha["puntos"] = ficha["puntos"] * 100      # la v2 cuenta en centésimas
        fichas.append(ficha)
    guardar(fichas)
