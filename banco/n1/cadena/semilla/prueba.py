from factura import linea
from tarifas import precio_final

ok = 0
assert precio_final(100, 0.5) == 150.0; ok += 1                       # sin descuento, como siempre
assert precio_final(100, 0.5, descuento=0.5) == 75.0; ok += 1         # el descuento va ANTES del IVA
assert precio_final(80, 0.25, descuento=0.25) == 75.0; ok += 1
assert linea("mesa", 100, 0.5, descuento=0.5) == "mesa: 75.00"; ok += 1
assert linea("silla", 50, 0.5) == "silla: 75.00"; ok += 1
print(f"{ok}/5 asertos ✓")
