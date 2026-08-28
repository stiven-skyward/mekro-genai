from entrada import leer
from filtro import positivos
from salida import total


def correr(lineas):
    return total(positivos(leer(lineas)))
