from cesta import agrupar

ok = 0
assert agrupar(["ajo", "atun", "pan"]) == {"a": ["ajo", "atun"], "p": ["pan"]}; ok += 1
assert agrupar(["col"]) == {"c": ["col"]}; ok += 1   # una cesta nueva parte de cero
assert agrupar([]) == {}; ok += 1
print(f"{ok}/3 asertos ✓")
