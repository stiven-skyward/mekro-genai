"""Verificador. Comprueba el arreglo Y dónde se hizo."""
import sys

fallos = []


def comprueba(que, cond):
    print(("✓ " if cond else "✗ ") + que)
    if not cond:
        fallos.append(que)


sys.path.insert(0, ".")
from entrada import leer          # noqa: E402
from filtro import positivos      # noqa: E402
from tuberia import correr        # noqa: E402

LINEAS = ["tornillo, 3", "tuerca,10", "", "arandela, 0", "clavo,7"]

# ── el sintoma, arreglado ──────────────────────────────────────────────────
comprueba("la tubería ya no revienta y suma bien", correr(LINEAS) == 20)

# ── pero el arreglo tiene que estar en la CAUSA ────────────────────────────
# `leer` promete devolver la cantidad como número. Si el parche se puso en `salida`
# o en `filtro`, la tubería sumaría pero el contrato de `leer` seguiría roto, y el
# siguiente que lo use se lleva el mismo susto.
crudo = leer(["tornillo, 3"])
comprueba("leer devuelve la cantidad como NÚMERO, que es lo que promete su docstring",
          isinstance(crudo[0]["cantidad"], (int, float)))
comprueba("y no pierde el nombre por el camino", crudo[0]["nombre"] == "tornillo")

# ── el filtro sigue filtrando: 0 no pasa ───────────────────────────────────
comprueba("filtro.positivos descarta las cantidades a cero",
          len(positivos(leer(LINEAS))) == 3)

if fallos:
    raise SystemExit(f"FALLAN {len(fallos)} de 4")
print("4/4 asertos ✓")
