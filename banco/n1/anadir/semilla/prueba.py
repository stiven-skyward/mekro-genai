from inventario import Inventario

inv = Inventario()
inv.entra("tuerca", 10)
ok = 0

inv.sale("tuerca", 4)
assert inv.hay("tuerca") == 6; ok += 1

try:
    inv.sale("tuerca", 7)            # no hay 7: ni descuenta ni lo deja pasar
    raise SystemExit("✗ sacar más de lo que hay debió levantar ValueError")
except ValueError:
    ok += 1
assert inv.hay("tuerca") == 6; ok += 1

try:
    inv.sale("tornillo", 1)          # lo que no existe no puede salir
    raise SystemExit("✗ sacar de una pieza inexistente debió levantar ValueError")
except ValueError:
    ok += 1

try:
    inv.sale("tuerca", 0)
    raise SystemExit("✗ una salida no positiva debió levantar ValueError")
except ValueError:
    ok += 1

print(f"{ok}/5 asertos ✓")
