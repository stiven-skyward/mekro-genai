import nucleo


def por_lotes(lotes):
    return [nucleo.procesar(l) for l in lotes]
