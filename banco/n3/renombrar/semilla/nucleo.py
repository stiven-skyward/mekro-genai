"""El corazón del cálculo."""


def procesar(datos):
    """Normaliza una lista de números: quita None y redondea a 2 decimales."""
    return [round(x, 2) for x in datos if x is not None]


def resumir(datos):
    limpios = procesar(datos)
    return {"n": len(limpios), "suma": round(sum(limpios), 2)}
