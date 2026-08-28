from agenda import alta, busca, listado

ag = {}
alta(ag, "  ana ", "600-1")
alta(ag, "bruno", "600-2")
alta(ag, "berta", "600-3")

ok = 0
assert "ana" in ag; ok += 1
assert busca(ag, "b") == ["berta", "bruno"]; ok += 1
assert listado(ag) == ["ana: 600-1", "berta: 600-3", "bruno: 600-2"]; ok += 1
print(f"{ok}/3 asertos ✓")
