"""Contrato de tarifas.py. Las cuatro primeras YA PASAN: no pueden romperse."""
from tarifas import precio

fallos = []


def comprueba(que, obtenido, esperado):
    if obtenido != esperado:
        fallos.append(f"✗ {que}: esperaba {esperado}, obtuve {obtenido}")
    else:
        print(f"✓ {que}")


# ── las que ya pasaban ─────────────────────────────────────────────────────
comprueba("festivo manda sobre socio", precio(1000, "ana", "2026-01-01"), 1200)
comprueba("festivo a no socio", precio(1000, "zoe", "2026-12-25"), 1200)
comprueba("socio en dia laborable", precio(1000, "beto", "2026-03-10"), 800)
comprueba("no socio en dia laborable", precio(1000, "zoe", "2026-03-10"), 1000)

# ── la nueva: fin de semana ────────────────────────────────────────────────
# En fin de semana hay un 10 % de recargo sobre lo que tocara. Se aplica DESPUES
# de las reglas anteriores, sobre el precio ya calculado.
comprueba("finde a no socio", precio(1000, "zoe", "2026-03-14"), 1100)
comprueba("finde a socio", precio(1000, "ana", "2026-03-14"), 880)
# LA TRAMPA: 2026-08-15 es festivo Y sabado. El recargo de finde NO se suma al de
# festivo, porque la regla 1 ya cerro el caso y las reglas paran en la primera que casa.
comprueba("festivo que ademas cae en finde", precio(1000, "ana", "2026-08-15"), 1200)

if fallos:
    print("\n".join(fallos))
    raise SystemExit(f"FALLAN {len(fallos)} de 7")
print("7/7 asertos ✓")
