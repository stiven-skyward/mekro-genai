from validadores import (valida_correo, valida_edad, valida_puerto,
                         valida_reintentos, valida_usuario)

ok = 0
assert valida_usuario("ana"); ok += 1
assert not valida_usuario("  ana "); ok += 1
assert valida_correo("a@b.es"); ok += 1
assert not valida_edad(""); ok += 1
assert valida_reintentos("3"); ok += 1
assert not valida_puerto(0); ok += 1
assert not valida_puerto("8080"); ok += 1
assert valida_puerto(8080); ok += 1
assert valida_puerto(65535); ok += 1     # el último puerto direccionable es legal
assert not valida_puerto(65536); ok += 1
print(f"{ok}/10 asertos ✓")
