"""Cerebros de nube (BYOK): la conversión a cada dialecto, sin tocar la red.

Lo que se vigila: que la transcripción del arnés se traduzca bien a los tres dialectos
que existen, que la clave del usuario NUNCA se invente ni se filtre, y que el nombre
del cerebro delate siempre que la carrera fue de nube — la regla que impide confundir
una cifra de nube con una local."""
import json
import os
import tempfile
from pathlib import Path

from _util import Cuenta

tmp = Path(tempfile.mkdtemp(prefix="nube-prueba-"))
os.environ["MG_CLAVES"] = str(tmp / "claves.json")
(tmp / "claves.json").write_text(json.dumps({
    "gemini": {"clave": "falsa-gemini"},
    "anthropic": {"clave": "falsa-anthropic"},
    "deepseek": {"clave": "falsa-deepseek"},
}), encoding="utf-8")

from genai.cerebro import cargar                       # noqa: E402
from genai.cerebro.base import Llamada, Mensaje        # noqa: E402
from genai.cerebro.nube import CerebroNube, _limpiar_esquema  # noqa: E402

c = Cuenta("nube")

# ── sin clave, se niega y dice cómo arreglarlo ──────────────────────────────
try:
    CerebroNube("openai")
    sin_clave = False
except SystemExit as e:
    sin_clave = "falta tu clave" in str(e) and str(tmp) in str(e)
c(sin_clave, "sin clave configurada, avisa y dice dónde ponerla (no inventa nada)")

try:
    CerebroNube("proveedor-que-no-existe")
    desconocido = False
except SystemExit as e:
    desconocido = "desconocido" in str(e)
c(desconocido, "un proveedor desconocido se rechaza con la lista de los conocidos")

# ── el nombre delata la nube: la regla que protege las cifras ───────────────
g = cargar("nube:gemini/gemini-3.7-flash")
c(g.nombre == "nube:gemini/gemini-3.7-flash",
  "el nombre del cerebro lleva proveedor y modelo: el registro nunca miente")
c(cargar("nube:deepseek").modelo == "deepseek-chat",
  "sin modelo explícito, se usa el por defecto del proveedor")

# ── una transcripción con herramientas, traducida a los tres dialectos ──────
tr = [Mensaje("sistema", "eres X"),
      Mensaje("usuario", "arregla suma.py"),
      Mensaje("asistente", "voy", llamadas=[Llamada("leer", {"ruta": "a.py"}, id="c1")]),
      Mensaje("herramienta", "def f(): pass", id_llamada="c1")]

o = cargar("nube:deepseek")._openai_mensajes(tr)
c([m["role"] for m in o] == ["system", "user", "assistant", "tool"],
  "dialecto OpenAI: los cuatro roles en orden")
c(o[2]["tool_calls"][0]["function"]["name"] == "leer"
  and json.loads(o[2]["tool_calls"][0]["function"]["arguments"])["ruta"] == "a.py",
  "la llamada viaja como tool_call con sus argumentos serializados")
c(o[3]["tool_call_id"] == "c1", "la observación se ata a su llamada por id")

a = cargar("nube:anthropic")._anthropic_mensajes(tr)
c([m["role"] for m in a] == ["user", "assistant", "user"],
  "dialecto Anthropic: el sistema sale de messages (va en su campo aparte)")
c(a[1]["content"][1]["type"] == "tool_use" and a[1]["content"][1]["id"] == "c1",
  "la llamada va como bloque tool_use con su id")
c(a[2]["content"][0]["type"] == "tool_result"
  and a[2]["content"][0]["tool_use_id"] == "c1",
  "la observación vuelve como tool_result atado al mismo id")

ge = g._gemini_contenidos(tr)
c([m["role"] for m in ge] == ["user", "model", "user"],
  "dialecto Gemini: el asistente es «model» y el sistema va aparte")
c(ge[1]["parts"][1]["functionCall"]["name"] == "leer",
  "la llamada va como functionCall")
c(ge[2]["parts"][0]["functionResponse"]["name"] == "leer",
  "la respuesta recupera el nombre de la función desde la llamada que la pidió")

# ── firmas de pensamiento (Gemini 3.x devuelve 400 si no vuelven) ───────────
g._firmas_pensamiento["c1"] = "FIRMA-XYZ"
ge2 = g._gemini_contenidos(tr)
c(ge2[1]["parts"][1].get("thoughtSignature") == "FIRMA-XYZ",
  "la firma de pensamiento se reinyecta en su functionCall (Gemini 3.x la exige)")

# ── esquemas: Gemini rechaza claves que OpenAI acepta ───────────────────────
limpio = _limpiar_esquema({"type": "object", "additionalProperties": False,
                           "properties": {"x": {"type": "string", "default": "a"}}})
c("additionalProperties" not in limpio and "default" not in limpio["properties"]["x"],
  "las claves que Gemini rechaza se podan en vez de reventar la llamada")
c(limpio["properties"]["x"]["type"] == "string", "y lo que sí entiende se conserva")

# ── la clave del usuario no se filtra al registro ni al nombre ──────────────
c("falsa-gemini" not in g.nombre and "falsa-gemini" not in repr(g.nombre),
  "la clave jamás aparece en el nombre que va al registro")

# ── .precio: BYOK sí lo trae si el catálogo lo conoce; suscripción, NUNCA ───
from genai import catalogo                             # noqa: E402

_cache_vieja = catalogo.CACHE
tmp_cat = tmp / "modelos.json"
catalogo.CACHE = tmp_cat
try:
    tmp_cat.write_text(json.dumps({
        "deepseek": {"models": {"deepseek-chat": {"cost": {"input": 3, "output": 12}}}}}),
        encoding="utf-8")
    op = CerebroNube("deepseek")
    c(op.precio == {"input": 3, "output": 12},
      "BYOK con un modelo que el catálogo conoce trae el precio real")

    tmp_cat.write_text(json.dumps({"deepseek": {"models": {}}}), encoding="utf-8")
    op2 = CerebroNube("deepseek")
    c(op2.precio is None,
      "y si el catálogo no tiene ESE modelo, precio es None — nunca una cifra inventada")

    import genai.copilot as _cop_mod                    # noqa: E402
    _cop_original = _cop_mod.config
    _cop_mod.config = lambda: {"dialecto": "openai", "url": "https://x", "clave": "tok-falso"}
    try:
        cop = CerebroNube("copilot")
        c(cop.precio is None,
          "una suscripción (Copilot) NUNCA muestra precio: no hay coste por token "
          "que el usuario esté pagando de verdad, y mostrarlo sería engañoso")
    finally:
        _cop_mod.config = _cop_original
finally:
    catalogo.CACHE = _cache_vieja

raise SystemExit(c.fin())
