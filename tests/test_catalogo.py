"""Catálogo de proveedores (models.dev): cualquier modelo sin código por proveedor.

Lo que se vigila, y ninguna de estas pruebas necesita red:

1. que **los ocho de fábrica manden** — son los que tienen medición detrás (caché,
   firmas de pensamiento, PDF) y el catálogo no sabe nada de eso;
2. que el `npm` de cada proveedor se traduzca al dialecto correcto, que es toda la
   idea: los tres dialectos ya escritos cubren los 207;
3. que **funcione sin red** una vez cacheado, porque un arnés que presume de local no
   puede necesitar una descarga para arrancar;
4. que lo que no se puede hacer se DIGA — firma de nube, URL desconocida, nombre mal
   escrito— en vez de fallar con un 404 sin explicación.
"""
import json
import os
import tempfile
import time
from pathlib import Path

from _util import Cuenta

from genai import catalogo
from genai.cerebro.nube import PROVEEDORES

c = Cuenta("catalogo")
tmp = Path(tempfile.mkdtemp(prefix="catalogo-"))

FALSO = {
    "unoai":     {"id": "unoai", "npm": "@ai-sdk/openai-compatible", "name": "UnoAI",
                  "api": "https://api.uno.example/v1", "env": ["UNO_KEY"],
                  "models": {"uno-grande": {"id": "uno-grande", "name": "Uno Grande"},
                             "uno-chico": {"id": "uno-chico", "name": "Uno Chico"}}},
    "dosant":    {"id": "dosant", "npm": "@ai-sdk/anthropic", "name": "DosAnt",
                  "api": "https://api.dos.example/v1/", "env": ["DOS_KEY"],
                  "models": {"dos-1": {"id": "dos-1", "name": "Dos 1"}}},
    "tresgoo":   {"id": "tresgoo", "npm": "@ai-sdk/google", "name": "TresGoo",
                  "api": "https://api.tres.example", "models": {}},
    "vertexoso": {"id": "vertexoso", "npm": "@ai-sdk/google-vertex", "name": "Vertexoso",
                  "api": "https://x.example", "models": {}},
    "sinurl":    {"id": "sinurl", "npm": "@ai-sdk/cohere", "name": "SinUrl",
                  "models": {}},
    "conenv":    {"id": "conenv", "npm": "@ai-sdk/openai-compatible", "name": "ConEnv",
                  "api": "https://${MI_CUENTA}.example/v1", "models": {}},
    "amazon-bedrock": {"id": "amazon-bedrock", "npm": "@ai-sdk/amazon-bedrock",
                       "name": "Bedrock", "models": {}},
}

catalogo.CACHE = tmp / "modelos.json"
catalogo.CACHE.write_text(json.dumps(FALSO), encoding="utf-8")
catalogo.FUENTE = "http://127.0.0.1:9/no-existe"     # cualquier red aquí es un fallo

# ── 3. sin red, con la caché de disco ──────────────────────────────────────
cat, queja = catalogo.descargar()
c(len(cat) == len(FALSO) and not queja,
  "con la caché fresca no se toca la red: un arnés local no necesita descargar nada "
  "para arrancar")

os.utime(catalogo.CACHE, (0, 0))                     # caché vieja → intenta bajar
cat, queja = catalogo.descargar()
c(len(cat) == len(FALSO) and "sin refrescar" in queja,
  "si el catálogo está viejo y la red falla, se usa el de disco Y SE DICE, en vez de "
  "quedarse sin proveedores")

catalogo.CACHE.write_text("{esto no es json", encoding="utf-8")
cat, queja = catalogo.descargar()
c(cat == {} and "no se pudo bajar" in queja,
  "una caché corrupta más red caída da queja accionable, no una excepción")
catalogo.CACHE.write_text(json.dumps(FALSO), encoding="utf-8")
os.utime(catalogo.CACHE, (time.time(), time.time()))

# ── 2. el npm decide el dialecto ───────────────────────────────────────────
c(catalogo._dialecto("@ai-sdk/anthropic") == "anthropic", "anthropic → dialecto propio")
c(catalogo._dialecto("@ai-sdk/google") == "gemini", "google → gemini")
c(catalogo._dialecto("@ai-sdk/openai-compatible") == "openai", "compatible → openai")
c(catalogo._dialecto("@lo-que-sea/raro") == "openai",
  "y lo desconocido se asume compatible con OpenAI, que es lo que habla el 90 % del "
  "catálogo: equivocarse ahí cuesta un 404, no un desastre")
c(catalogo._dialecto("@ai-sdk/google-vertex") == "",
  "vertex NO: exige firma de Google Cloud, no una clave en una cabecera")

cfg, q = catalogo.resolver("unoai")
c(cfg["dialecto"] == "openai" and cfg["url"] == "https://api.uno.example/v1",
  "un proveedor del catálogo da dialecto y URL listos para CerebroNube")
c(cfg["modelo"] == "uno-grande" and cfg["env"] == "UNO_KEY",
  "y trae el primer modelo como defecto y la variable de entorno de su clave")
c(catalogo.resolver("dosant")[0]["url"] == "https://api.dos.example/v1",
  "la barra final se quita: concatenar rutas después con dos barras da 404")

# ── 4. lo que no se puede hacer, se dice ───────────────────────────────────
_, q = catalogo.resolver("vertexoso")
c("firma propia" in q, "vertex se rechaza explicando por qué, no con un 403 mudo")
_, q = catalogo.resolver("amazon-bedrock")
c("firma de su nube" in q,
  "y lo mismo Bedrock, Azure y compañía: SigV4 y tokens de nube no son «una clave»")
_, q = catalogo.resolver("sinurl")
c("no dice la URL" in q and "claves.json" in q,
  "si el catálogo no trae URL, se dice cómo escribirla a mano")
_, q = catalogo.resolver("uno")
c("no está entre los" in q and "unoai" in q,
  "un nombre incompleto sugiere los que se le parecen en vez de solo negarse")

os.environ.pop("MI_CUENTA", None)
_, q = catalogo.resolver("conenv")
c("MI_CUENTA" in q,
  "una URL con ${VARIABLE} dice QUÉ variable falta: es la diferencia entre un error "
  "accionable y un 404")
os.environ["MI_CUENTA"] = "miempresa"
cfg, _ = catalogo.resolver("conenv")
c(cfg["url"] == "https://miempresa.example/v1", "y con la variable puesta, se sustituye")
os.environ.pop("MI_CUENTA")

# ── búsqueda ───────────────────────────────────────────────────────────────
c(len(catalogo.buscar("")) == 3,
  "sin filtro salen los 3 modelos del catálogo de juguete")
c([m for _, m, _ in catalogo.buscar("uno-ch")] == ["uno-chico"],
  "y con filtro, solo los que casan")
c(len(catalogo.buscar("", tope=2)) == 2, "el tope se respeta: la lista no se desborda")

# ── 1. los ocho de fábrica mandan ──────────────────────────────────────────
fuente = (Path(__file__).resolve().parents[1] / "genai" / "cerebro" / "nube.py"
          ).read_text(encoding="utf-8")
i = fuente.index("base = PROVEEDORES.get(proveedor)")
c("if base is None" in fuente[i:i + 600],
  "el catálogo solo se consulta si el nombre NO está de fábrica: los ocho medidos "
  "ganan siempre, porque el catálogo no sabe de caché ni de firmas de pensamiento")
c({"openai", "anthropic", "gemini"} <= set(PROVEEDORES),
  "y los tres con medición real siguen ahí")

raise SystemExit(c.fin())
