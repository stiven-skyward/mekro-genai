"""El formato Hermes: montarlo bien y —sobre todo— NO adivinar cuando llega roto.

Un modelo de 2 bits emite llamadas malformadas con frecuencia. Adivinar qué quiso decir
es ejecutar algo que no pidió, y estas herramientas escriben en disco y corren shell."""
from _util import Cuenta

from genai.cerebro.base import Llamada, Mensaje
from genai.cerebro.plantilla import analizar_llamadas, montar, separar_razonamiento

c = Cuenta("plantilla")

# ── montar ──────────────────────────────────────────────────────────────────
p = montar([Mensaje("sistema", "eres X"), Mensaje("usuario", "hola")],
           [{"type": "function", "function": {"name": "leer", "parameters": {}}}])
c("<|im_start|>system" in p and "<|im_end|>" in p, "usa los marcadores de Qwen")
c("<tools>" in p and '"name": "leer"' in p, "las firmas van dentro de <tools>")
c(p.endswith("<|im_start|>assistant\n"), "termina invitando al asistente a hablar")

p = montar([Mensaje("sistema", "s"),
            Mensaje("asistente", "voy", llamadas=[Llamada("leer", {"ruta": "a.py"})]),
            Mensaje("herramienta", "contenido", id_llamada="1")])
c("<tool_call>" in p, "las llamadas del asistente se reemiten en formato Hermes")
c("<tool_response>" in p, "las observaciones vuelven como tool_response")

# ── razonamiento ────────────────────────────────────────────────────────────
razon, visible = separar_razonamiento("<think>lo pienso</think>la respuesta")
c.igual(razon, "lo pienso", "el <think> se separa")
c.igual(visible, "la respuesta", "y no contamina la respuesta")

# ── analizar: lo válido ─────────────────────────────────────────────────────
prosa, lls, quejas = analizar_llamadas(
    'ahí voy\n<tool_call>\n{"name": "leer", "arguments": {"ruta": "a.py"}}\n</tool_call>')
c.igual(len(lls), 1, "se lee una llamada bien formada")
c.igual(lls[0].nombre, "leer", "con su nombre")
c.igual(lls[0].argumentos, {"ruta": "a.py"}, "y sus argumentos")
c.igual(prosa, "ahí voy", "la prosa queda limpia de la llamada")
c.igual(quejas, [], "sin quejas")

_, lls, _ = analizar_llamadas(
    '<tool_call>{"name":"a","arguments":{}}</tool_call>'
    '<tool_call>{"name":"b","arguments":{}}</tool_call>')
c.igual([l.nombre for l in lls], ["a", "b"], "varias llamadas en un turno")
c(lls[0].id != lls[1].id, "cada llamada tiene identificador propio")

# argumentos como cadena JSON: se le escapa a los modelos pequeños, y es recuperable
_, lls, _ = analizar_llamadas('<tool_call>{"name":"a","arguments":"{\\"x\\": 1}"}</tool_call>')
c.igual(lls[0].argumentos, {"x": 1}, "«arguments» en cadena JSON se recupera")

# ── analizar: lo roto NO se adivina ─────────────────────────────────────────
_, lls, quejas = analizar_llamadas('<tool_call>{"name": "leer", "arg</tool_call>')
c.igual(lls, [], "JSON roto no produce llamada")
c(quejas and "JSON inválido" in quejas[0], "produce una queja accionable")

_, lls, quejas = analizar_llamadas('<tool_call>{"arguments": {}}</tool_call>')
c(not lls and "sin «name»" in quejas[0], "sin nombre no hay llamada")

_, lls, quejas = analizar_llamadas('<tool_call>{"name":"a","arguments":[1,2]}</tool_call>')
c(not lls and "debe ser un objeto" in quejas[0], "argumentos que no son objeto se rechazan")

_, _, quejas = analizar_llamadas('<tool_call>{"name": "leer"')
c(any("truncó" in q for q in quejas), "una llamada sin cerrar se diagnostica como truncada")

# ── pensar=False: el prellenado de fábrica de Qwen3 que apaga el razonamiento ──
p = montar([Mensaje("sistema", "x"), Mensaje("usuario", "y")], pensar=False)
c(p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"),
  "sin pensar, el turno del asistente abre con el think vacío prellenado")
c(montar([Mensaje("usuario", "y")]).endswith("<|im_start|>assistant\n"),
  "con pensar (el defecto), nada cambia")

raise SystemExit(c.fin())
