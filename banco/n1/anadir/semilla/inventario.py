"""Inventario mínimo: cantidades por nombre, nunca negativas."""


class Inventario:
    def __init__(self):
        self._piezas = {}

    def entra(self, nombre, cantidad):
        if cantidad <= 0:
            raise ValueError("la cantidad que entra debe ser positiva")
        self._piezas[nombre] = self._piezas.get(nombre, 0) + cantidad

    def hay(self, nombre):
        return self._piezas.get(nombre, 0)
