"""El camino append-exacto de C22, sin cargar el modelo (la carga es perezosa).

C20 midió el castigo de equivocarse aquí: la caché del Qwen3.8 GGUF no admite borrado
parcial, así que un sufijo mal montado no corrompe —el cotejo de prefijo lo detecta y
re-evalúa todo— pero cuesta la carrera entera (3.359,5 s la de humo). Estas pruebas
vigilan la lógica pura: cuándo se extiende y cuándo se arranca en frío."""
from _util import Cuenta

from genai.cerebro.base import Llamada, Mensaje
from genai.cerebro.local_gguf import CerebroGGUF
from genai.cerebro.plantilla import montar, montar_uno

c = Cuenta("local_gguf")

# ── montar_uno compone exactamente montar ───────────────────────────────────
hs = [{"type": "function", "function": {"name": "leer", "parameters": {}}}]
ms = [Mensaje("sistema", "eres X"), Mensaje("usuario", "hola"),
      Mensaje("asistente", "veo", llamadas=[Llamada("leer", {"ruta": "a.py"})]),
      Mensaje("herramienta", "contenido", id_llamada="1")]
compuesto = "".join(montar_uno(m, hs, primero=(i == 0)) for i, m in enumerate(ms))
c(compuesto + "<|im_start|>assistant\n" == montar(ms, hs),
  "montar es la suma de montar_uno más la apertura del asistente")
c("<tool_response>" in montar_uno(ms[3]), "la observación va envuelta en tool_response")

# ── el sufijo incremental: cuándo sí ────────────────────────────────────────
cerebro = CerebroGGUF()          # sin _cargar(): nada de esto toca el GGUF
m1 = [Mensaje("sistema", "eres X"), Mensaje("usuario", "arregla suma.py")]
c(cerebro._sufijo_incremental(m1) is None, "sin contexto cacheado no hay sufijo: frío")

# simula una generación hecha: contexto con tokens y huellas de m1 + turno propio
cerebro._ids_contexto = [1, 2, 3]
cerebro._huellas = [cerebro._huella(m) for m in m1] + [None]

m2 = m1 + [Mensaje("asistente", "veo", llamadas=[Llamada("leer", {"ruta": "s.py"})]),
           Mensaje("herramienta", "def sumar…", id_llamada="1")]
suf = cerebro._sufijo_incremental(m2)
c(suf is not None, "la transcripción que solo crece por el final extiende")
c(suf.startswith("<|im_end|>\n"), "el sufijo cierra primero nuestro turno cacheado")
c("<tool_response>\ndef sumar…\n</tool_response>" in suf,
  "el sufijo lleva la observación nueva plantillada")
c(suf.endswith("<|im_start|>assistant\n"), "y abre el turno siguiente del asistente")
c("veo" not in suf,
  "nuestro turno de asistente NO se re-plantilla: sus tokens crudos ya están en caché")

# ── cuándo no: cada camino de vuelta al frío ────────────────────────────────
c(cerebro._sufijo_incremental(m2[:3]) is None, "sin mensajes nuevos no hay sufijo")

reescrito = [Mensaje("sistema", "eres OTRO")] + m2[1:]
c(cerebro._sufijo_incremental(reescrito) is None,
  "un mensaje viejo reescrito (compactar) manda al frío, jamás a podar")

sin_hueco = [m1[0], m1[1], Mensaje("usuario", "otra cosa"),
             Mensaje("herramienta", "x", id_llamada="1")]
c(cerebro._sufijo_incremental(sin_hueco) is None,
  "si donde iba nuestro turno no hay un asistente, frío")

# ── la huella distingue lo que importa ──────────────────────────────────────
a = Mensaje("asistente", "t", llamadas=[Llamada("leer", {"ruta": "a"})])
b = Mensaje("asistente", "t", llamadas=[Llamada("leer", {"ruta": "b"})])
c(CerebroGGUF._huella(a) != CerebroGGUF._huella(b),
  "cambiar los argumentos de una llamada cambia la huella")
c(CerebroGGUF._huella(a) == CerebroGGUF._huella(
    Mensaje("asistente", "t", llamadas=[Llamada("leer", {"ruta": "a"})])),
  "dos mensajes iguales dan la misma huella")

raise SystemExit(c.fin())
