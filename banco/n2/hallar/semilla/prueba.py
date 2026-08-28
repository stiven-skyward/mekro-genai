import importlib

ok = 0
for i in range(8):
    m = importlib.import_module(f'app.mod{i}')
    assert m.LIMITE == 100, f'mod{i} tiene el límite mal puesto'
    ok += 1
print(f'{ok}/8 asertos ✓')
