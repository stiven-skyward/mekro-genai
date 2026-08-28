"""Caché de prefijo de los proveedores (docs/ahorro.md), en frío y sin red.

C82 midió que la entrada es el 89 % de la factura y que la poda solo alcanza al 11 %.
La caché de prefijo es la única palanca que toca el 100 %, así que lo que se vigila aquí
son las tres formas de perderla, que son silenciosas las tres:

1. **pedirla donde no ahorra** — marcar el último turno, que es justo lo que cambia;
2. **recrearla demasiado** — escribir una caché cuesta como entrada normal, así que
   rehacerla cada vuelta es pagar dos veces por no ahorrar nada;
3. **dejarla viva** — una caché que sobrevive a la tarea se sigue cobrando por horas.
"""
import json
from pathlib import Path

from _util import Cuenta

from genai.cerebro.base import Mensaje
from genai.cerebro.nube import CerebroNube

c = Cuenta("cache")
RAIZ = Path(__file__).resolve().parents[1]


def desnudo(dialecto="gemini"):
    n = CerebroNube.__new__(CerebroNube)
    n.dialecto, n.modelo, n.clave = dialecto, "m", "k"
    n.url, n.temperatura = "https://x/v1beta", 0.0
    n.cache, n._cache_g, n.cachear = {"leidos": 0, "totales": 0}, None, True
    n._firmas_pensamiento = {}
    return n


# ── la contabilidad: sin ella, «ahorra» es un adjetivo ─────────────────────
n = desnudo()
c(n.ahorro_cache == 0.0, "sin llamadas, el ahorro es 0 y no un fallo")
n._anotar_cache(900, 1000)
n._anotar_cache(100, 1000)
c(n.ahorro_cache == 0.5,
  "el ahorro se acumula sobre el total, no se promedia por llamada: lo que importa "
  "es la factura entera")
c(n._anotar_cache(0, 0) is None and n.ahorro_cache == 0.5,
  "y un cero no divide por cero ni ensucia la cifra")

# ── Anthropic: el marcador va donde ahorra ─────────────────────────────────
fuente = (RAIZ / "genai" / "cerebro" / "nube.py").read_text(encoding="utf-8")
c("cache_control" in fuente, "Anthropic exige pedir la caché a mano y se pide")
c("msgs[-3]" in fuente and "msgs[-1]" not in fuente.split("cache_control")[1][:400],
  "se marca el PENÚLTIMO turno: marcar el último no cachearía nada, porque es "
  "exactamente lo que cambia entre vuelta y vuelta")

# ── OpenAI y Gemini: automática una, explícita la otra ─────────────────────
c("cached_tokens" in fuente and "prompt_cache_hit_tokens" in fuente,
  "en OpenAI y DeepSeek la caché es automática, pero se CUENTA: medido 76,6 % en "
  "una carrera real de n1/anadir con gpt-4.1-mini")
c("cachedContents" in fuente,
  "Gemini no tiene caché implícita —tres peticiones idénticas de 6.008 tokens y no "
  "reportó ni una— así que se pide explícita")

# ── la aritmética de cuándo recrear ────────────────────────────────────────
c(CerebroNube.CACHE_MINIMO == 1024,
  "1.024 es el mínimo del API, medido: con 603 responde 400 diciéndolo")
c(0 < CerebroNube.CACHE_COLA_MAX <= 1.0,
  "escribir una caché cuesta como entrada normal: T·(1+0,25·K) frente a T·K gana "
  "solo a partir de K>1,33, así que no se recrea hasta que se amortice")


class Falsa(CerebroNube):
    """Cuenta cuántas veces se habría escrito una caché, sin salir a la red."""

    def __init__(self):
        for k, v in vars(desnudo()).items():
            setattr(self, k, v)
        self.creadas = 0

    def _cache_crear(self, prefijo, sistema, tools):
        self.creadas += 1
        self._cache_g = {"nombre": f"c{self.creadas}", "hasta": len(prefijo),
                         "tokens": 9999}
        return self._cache_g


from genai.cerebro.nube import _aprox_tokens  # noqa: E402


def simular(vueltas, tam_turno):
    """La MISMA decisión que toma _gemini, sin red: un encargo grande y estable, y
    turnos de `tam_turno` caracteres detrás."""
    f = Falsa()
    contenidos = [{"role": "user", "parts": [{"text": "x" * 24000}]}]
    for _ in range(vueltas):
        contenidos.append({"role": "model", "parts": [{"text": "y" * tam_turno}]})
        prefijo = contenidos[:-1]
        cc = f._cache_g
        if _aprox_tokens(prefijo) >= f.CACHE_MINIMO and (
                not cc or _aprox_tokens(contenidos[cc["hasta"]:-1])
                >= f.CACHE_COLA_MAX * max(1, cc["tokens"])):
            f._cache_crear(prefijo, "", None)
            f._cache_g["tokens"] = _aprox_tokens(prefijo)
    return f.creadas


chicos = simular(10, 300)
c(chicos <= 3,
  f"con turnos pequeños detrás de un encargo grande, la caché se reescribe {chicos} "
  f"veces en 10 vueltas y no 10: reescribir cada vuelta es pagar la escritura sin "
  f"llegar a leerla dos veces")
c(chicos >= 1, "pero se escribe: una caché que nunca se crea no ahorra nada")
c(simular(10, 40000) > chicos,
  "y si los turnos son enormes se reescribe MÁS: la cola sin cachear crece deprisa y "
  "dejarla fuera sería no cachear casi nada. El umbral mira TOKENS, no número de "
  "mensajes — un turno de 20 caracteres y uno de 40.000 pesan igual en la cuenta de "
  "mensajes y nada parecido en la factura")

# ── un prefijo pequeño no se intenta ───────────────────────────────────────
g = Falsa()
corto = [{"role": "user", "parts": [{"text": "hola"}]}]
aprox = sum(len(json.dumps(p, ensure_ascii=False)) for p in corto) / 4
c(aprox < g.CACHE_MINIMO,
  "un prefijo por debajo del mínimo se descarta ANTES de pedirlo: un 400 previsible "
  "no se provoca para luego capturarlo")

# ── el interruptor, para poder medir contra su ausencia ────────────────────
h = desnudo(); h.cachear = False
c(h.cachear is False, "la caché se puede apagar: sin brazo de control no hay medición")

# ── cabeceras extra por proveedor ──────────────────────────────────────────
# Existen porque una clave de Anthropic ligada a identidad responde 400 sin
# `anthropic-workspace-id`, y porque un proxy corporativo delante de cualquier
# proveedor pide las suyas. Se ponen en claves.json, sin tocar código.
c("cabeceras" in fuente and "cab.update(self.cabeceras)" in fuente,
  "el dialecto de Anthropic mezcla las cabeceras extra con las suyas")
c('"x-api-key": self.clave' in fuente,
  "sin que las extra puedan pisar la clave ni la versión del API, que van primero")

# ── que no quede nada vivo ─────────────────────────────────────────────────
c("def cerrar" in fuente and "_cache_borrar" in fuente,
  "hay una forma explícita de cerrar: una caché que sobrevive a la tarea se sigue "
  "cobrando por horas aunque el TTL acabe barriéndola")
for quien in ("scripts/correr_banco.py", "genai/cli.py"):
    c("cerrar()" in (RAIZ / quien).read_text(encoding="utf-8"),
      f"y {quien} la cierra al terminar, que es donde de verdad se deja de pagar")

k = desnudo()
k._cache_g = None
c(k.cerrar() is None, "cerrar sin caché viva no revienta")
k.dialecto = "openai"
c(k.cerrar() is None, "ni en un dialecto que no usa caché explícita")

raise SystemExit(c.fin())
