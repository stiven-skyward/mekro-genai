from caja import cobrar
from carro import Carro
from cupones import descuento

ok = 0
c = Carro()
c.anadir("pan", 2)
c.anadir("queso")
assert cobrar(c) == "TOTAL: 9.00"; ok += 1           # sin cupón, como siempre

assert descuento("MITAD") == 0.5; ok += 1
assert descuento("DIEZ") == 0.1; ok += 1
try:
    descuento("CHOLLO")
    raise SystemExit("✗ un cupón desconocido debió levantar ValueError")
except ValueError:
    ok += 1

assert cobrar(c, cupon="MITAD") == "TOTAL: 4.50"; ok += 1
assert cobrar(c, cupon="DIEZ") == "TOTAL: 8.10"; ok += 1
assert cobrar(c) == "TOTAL: 9.00"; ok += 1           # cobrar no muta el carro
print(f"{ok}/7 asertos ✓")
