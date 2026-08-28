import os

from bitacora import eventos, registrar

RUTA = "eventos.jsonl"
if os.path.exists(RUTA):
    os.remove(RUTA)

ok = 0
assert eventos(RUTA) == []; ok += 1                  # primer arranque: bitácora vacía
registrar(RUTA, "arranque")
registrar(RUTA, "año nuevo")
assert eventos(RUTA) == [{"que": "arranque"}, {"que": "año nuevo"}]; ok += 1
registrar(RUTA, "parada")
assert [e["que"] for e in eventos(RUTA)][-1] == "parada"; ok += 1
print(f"{ok}/3 asertos ✓")
