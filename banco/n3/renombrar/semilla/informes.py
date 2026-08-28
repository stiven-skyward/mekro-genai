from nucleo import procesar, resumir


def informe_corto(datos):
    return f"{len(procesar(datos))} valores"


def informe_largo(datos):
    r = resumir(datos)
    return f"{r['n']} valores, suman {r['suma']}"
