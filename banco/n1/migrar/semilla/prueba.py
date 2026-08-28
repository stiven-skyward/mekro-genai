from informe import cabecera, nota

ok = 0
assert cabecera("  ventas  ") == "[VENTAS]"; ok += 1
assert nota("  sin novedades  ") == "[sin novedades]"; ok += 1
assert nota("ya limpio") == "[ya limpio]"; ok += 1
print(f"{ok}/3 asertos ✓")
