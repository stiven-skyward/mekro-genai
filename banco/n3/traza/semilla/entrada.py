"""Paso 1: leer los registros crudos."""


def leer(lineas):
    """Cada línea es «nombre,cantidad». Devuelve dicts.

    La cantidad debe salir de aquí como NÚMERO: es el contrato de este paso, y los
    pasos siguientes cuentan con él.
    """
    fuera = []
    for l in lineas:
        if not l.strip():
            continue
        nombre, cantidad = l.split(",")
        fuera.append({"nombre": nombre.strip(), "cantidad": cantidad.strip()})
    return fuera
