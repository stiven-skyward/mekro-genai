"""El carro de la compra: solo admite artículos del catálogo."""
from catalogo import precio


class Carro:
    def __init__(self):
        self._articulos = []

    def anadir(self, nombre, unidades=1):
        if unidades <= 0:
            raise ValueError("las unidades deben ser positivas")
        precio(nombre)                      # valida que exista, o revienta aquí
        self._articulos.append((nombre, unidades))

    def total(self):
        return sum(precio(n) * u for n, u in self._articulos)
