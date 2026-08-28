import importlib

ok = 0
for i in range(10):
    m = importlib.import_module(f'app.m{i}')
    assert m.calcula(5) == 5 + i, f'm{i} sigue con el signo cambiado'
    ok += 1
print(f'{ok}/10 asertos ✓')
