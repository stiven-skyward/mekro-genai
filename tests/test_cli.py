"""genai/cli.py — funciones que no necesitan un proceso aparte para probarse.

Nace de un fallo real: `_mostrar_costo()` llamaba `cerebro.ahorro_cache()` como si
fuera un método, pero en `CerebroNube` es una `@property` — revienta con
"'float' object is not callable" en la PRIMERA carrera BYOK de verdad, y ningún test
existente lo vio porque todos usan `eco`, que no tiene `.precio` (así que la línea
nunca se ejecutaba). Esta prueba ejercita esa línea con un objeto que tiene la
`@property` de verdad, no un atributo plano — para que este fallo concreto no pueda
volver a colarse.
"""
import contextlib
import io

from _util import Cuenta

from genai.cli import _expandir_menciones, _mostrar_costo

c = Cuenta("cli")


class _FalsoUso:
    def __init__(self, entrada, salida):
        self.tokens_entrada, self.tokens_salida = entrada, salida


class _FalsoResultado:
    def __init__(self, entrada, salida):
        self.uso = _FalsoUso(entrada, salida)


class _CerebroConPropiedad:
    """La forma REAL de CerebroNube: `ahorro_cache` es una @property, no un método."""
    precio = {"input": 1.0, "output": 2.0}

    @property
    def ahorro_cache(self) -> float:
        return 0.25


class _CerebroSinPrecio:
    precio = None


buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    _mostrar_costo(_CerebroConPropiedad(), _FalsoResultado(1_000_000, 500_000))
salida = buf.getvalue()
c("$" in salida, "_mostrar_costo() imprime un coste cuando el cerebro tiene .precio "
                "— y NO revienta contra la @property real de CerebroNube")
c("2.0000" in salida or "$2.0000" in salida,
  "la cifra es la aritmética real: 1M de entrada a $1/M + 0,5M de salida a $2/M = $2")
c("25%" in salida, "y la línea también trae el ahorro de caché, leído como propiedad")

buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    _mostrar_costo(_CerebroSinPrecio(), _FalsoResultado(100, 100))
c(buf2.getvalue() == "", "sin `.precio` (local, suscripción, o BYOK sin dato de "
                        "catálogo) no imprime nada — no hay coste que inventar")

# ── _expandir_menciones: sanity directa, sin pasar por un proceso de chat ───
texto, rutas = _expandir_menciones("sin ninguna mención aquí")
c(rutas == [] and texto == "sin ninguna mención aquí",
  "sin @, el texto vuelve intacto y sin adjuntos")

texto2, rutas2 = _expandir_menciones("mira @/ruta/que/no/existe/de/verdad")
c(rutas2 == [] and "@/ruta/que/no/existe/de/verdad" in texto2,
  "una @mención que no es un fichero real se deja tal cual, no se rompe ni se inventa")

raise SystemExit(c.fin())
