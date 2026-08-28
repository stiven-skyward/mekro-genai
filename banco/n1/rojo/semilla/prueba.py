from turnos import huecos, solapan

ok = 0
assert solapan((0, 10), (5, 15)); ok += 1
assert solapan((5, 8), (0, 10)); ok += 1
assert not solapan((0, 10), (10, 20)); ok += 1   # tocarse en el borde no es pisarse
assert not solapan((12, 14), (14, 16)); ok += 1
assert huecos([(0, 8), (16, 24)]) == [(8, 16)]; ok += 1
print(f"{ok}/5 asertos ✓")
