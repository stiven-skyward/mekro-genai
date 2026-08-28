"""Cálculo de tarifas. Las reglas se aplican EN ORDEN y la primera que casa manda."""


FESTIVOS = {"2026-01-01", "2026-08-15", "2026-12-25"}
SOCIOS = {"ana", "beto", "cira"}


def es_finde(dia):
    import datetime
    return datetime.date.fromisoformat(dia).weekday() >= 5


def precio(base, cliente, dia):
    """Devuelve el precio final en céntimos.

    Reglas, en este orden:
      1. En festivo NADIE tiene descuento: se paga el recargo del 20 %.
      2. Un socio paga el 80 %.
      3. El resto paga la base.
    """
    if dia in FESTIVOS:
        return round(base * 1.20)
    if cliente in SOCIOS:
        return round(base * 0.80)
    return base
