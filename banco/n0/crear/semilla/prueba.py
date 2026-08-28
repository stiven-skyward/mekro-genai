from pila import Pila

p = Pila()
assert p.vacia()
p.apilar(1)
p.apilar(2)
assert not p.vacia()
assert p.desapilar() == 2
assert p.desapilar() == 1
assert p.vacia()
print('4/4 asertos ✓')
