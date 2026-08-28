import json

from migrador import RUTA, migrar

V1 = [{"nombre": "ana", "puntos": 37}, {"nombre": "bo", "puntos": 8}]
with open(RUTA, "w", encoding="utf-8") as f:
    for ficha in V1:
        f.write(json.dumps(ficha, ensure_ascii=False) + "\n")

ok = 0
migrar()
fichas = [json.loads(l) for l in open(RUTA, encoding="utf-8")]
assert fichas[0] == {"nombre": "ana", "puntos": 3700, "v": 2, "nivel": 3}; ok += 1
assert fichas[1] == {"nombre": "bo", "puntos": 800, "v": 2, "nivel": 0}; ok += 1

migrar()                     # mantenimiento: relanzar NO puede volver a migrar
fichas_bis = [json.loads(l) for l in open(RUTA, encoding="utf-8")]
assert fichas_bis == fichas; ok += 1
print(f"{ok}/3 asertos ✓")
