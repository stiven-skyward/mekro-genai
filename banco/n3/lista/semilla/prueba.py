import os
import subprocess
import sys

if os.path.exists("lista.jsonl"):
    os.remove("lista.jsonl")


def cli(*args):
    r = subprocess.run([sys.executable, "orden.py", *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


ok = 0

# ── el módulo, a pelo ──────────────────────────────────────────────
from lista import anadir, pendientes, tachar

anadir("pan")
anadir("leche")
assert pendientes() == ["pan", "leche"]; ok += 1
tachar("pan")
assert pendientes() == ["leche"]; ok += 1

# ── el CLI es OTRO proceso: la persistencia tiene que cruzarlo ─────
codigo, salida = cli("ver")
assert codigo == 0 and salida == "leche"; ok += 1
codigo, salida = cli("anadir", "queso")
assert codigo == 0; ok += 1
codigo, salida = cli("ver")
assert salida == "leche\nqueso"; ok += 1
codigo, salida = cli("tachar", "pan")          # ya no está pendiente
assert codigo == 1; ok += 1

print(f"{ok}/6 asertos ✓")
