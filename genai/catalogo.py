"""Catálogo de proveedores: cualquier modelo, sin escribir código para cada uno.

`nube.py` trae ocho proveedores a mano porque son los que se han usado y medido. Esto
añade los **207 de models.dev** —7.483 modelos— sin una línea por proveedor, y la razón
por la que funciona es que ahí fuera casi todo el mundo habla el mismo dialecto:

    @ai-sdk/openai, @ai-sdk/openai-compatible, …  →  dialecto openai   (~190)
    @ai-sdk/anthropic                             →  dialecto anthropic  (9)
    @ai-sdk/google                                →  dialecto gemini     (1)

Es decir: los tres dialectos que ya estaban escritos cubren el catálogo entero. Lo que
faltaba no era código, era **la tabla**.

**Se cachea en disco y se usa sin red.** Un arnés cuya identidad es correr en local no
puede necesitar una descarga para arrancar. La primera vez se baja; después se lee del
disco, y si el catálogo no se puede refrescar se sigue con el que hay y se dice.

**Los ocho de fábrica mandan.** Si un nombre está en `PROVEEDORES`, gana ese: son los
que tienen medición detrás (caché, firmas de pensamiento, PDF) y el catálogo no sabe
nada de eso.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

FUENTE = "https://models.dev/api.json"
CACHE = Path.home() / ".config" / "genai" / "modelos.json"
FRESCO = 7 * 24 * 3600          # una semana; el catálogo no cambia cada hora
AGENTE = "Mozilla/5.0 (compatible; Mekro-Genai)"

# npm del proveedor → dialecto que ya sabemos hablar
DIALECTOS = (
    ("@ai-sdk/anthropic", "anthropic"),
    ("@ai-sdk/google-vertex", ""),          # necesita firma de Google Cloud: no vale
    ("@ai-sdk/google", "gemini"),
)


# models.dev omite la URL de 26 proveedores porque da por hecho que su SDK la sabe, y
# resulta que son los nombres grandes. Cinco ya están de fábrica en nube.py; estos son
# los demás cuyo endpoint es público y está documentado. Se puede pisar cualquiera
# escribiendo `url` en claves.json.
URL_CONOCIDA = {
    "mistral":    "https://api.mistral.ai/v1",
    "cerebras":   "https://api.cerebras.ai/v1",
    "togetherai": "https://api.together.xyz/v1",
    "deepinfra":  "https://api.deepinfra.com/v1/openai",
    "perplexity": "https://api.perplexity.ai",
    "cohere":     "https://api.cohere.ai/compatibility/v1",
}
# Estos NO se resuelven a propósito: no se autentican con una clave en una cabecera sino
# con la firma de su nube (SigV4, cuentas de servicio, tokens de Azure AD). Decirlo es
# mejor que dejar que fallen con un 403 sin explicación.
FIRMA_DE_NUBE = {"amazon-bedrock", "google-vertex", "google-vertex-anthropic", "azure",
                 "azure-cognitive-services", "watsonx", "sap-ai-core", "vercel"}


def _dialecto(npm: str) -> str:
    for pista, d in DIALECTOS:
        if npm.startswith(pista):
            return d
    return "openai"        # el resto habla chat/completions, con o sin «compatible»


def descargar(forzar: bool = False) -> tuple[dict, str]:
    """Devuelve (catálogo, queja). Nunca lanza: sin catálogo el arnés sigue vivo."""
    fresco = CACHE.is_file() and (time.time() - CACHE.stat().st_mtime) < FRESCO
    if fresco and not forzar:
        try:
            return json.loads(CACHE.read_text(encoding="utf-8")), ""
        except ValueError:
            pass                              # caché corrupta: se vuelve a bajar
    try:
        pedido = urllib.request.Request(FUENTE, headers={"User-Agent": AGENTE,
                                                         "Accept": "application/json"})
        d = json.load(urllib.request.urlopen(pedido, timeout=60))
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(d), encoding="utf-8")
        return d, ""
    except Exception as e:                    # noqa: BLE001 — la red es de otros
        if CACHE.is_file():
            try:
                return (json.loads(CACHE.read_text(encoding="utf-8")),
                        f"catálogo sin refrescar ({e}); se usa el de disco")
            except ValueError:
                pass
        return {}, (f"no se pudo bajar el catálogo de proveedores ({e}) y no hay copia "
                    f"en disco. Los ocho de fábrica siguen funcionando.")


def _sustituir_entorno(url: str) -> tuple[str, str]:
    """Algunas URLs traen `${CLOUDFLARE_ACCOUNT}` y cosas así: se rellenan del entorno.
    Si falta una, se dice CUÁL — es la diferencia entre un error accionable y un 404."""
    faltan = [v for v in re.findall(r"\$\{([A-Z0-9_]+)\}", url) if not os.environ.get(v)]
    if faltan:
        return url, (f"esa URL necesita {', '.join(faltan)} en el entorno; "
                     f"expórtala y vuelve a intentarlo")
    return re.sub(r"\$\{([A-Z0-9_]+)\}", lambda m: os.environ[m.group(1)], url), ""


def resolver(proveedor: str) -> tuple[dict, str]:
    """Config para `CerebroNube`, sacada del catálogo. Devuelve (cfg, queja)."""
    cat, queja = descargar()
    p = cat.get(proveedor)
    if not p:
        if not cat:
            return {}, queja
        cerca = [k for k in cat if proveedor.lower() in k.lower()][:6]
        pista = f" ¿Querías {', '.join(cerca)}?" if cerca else ""
        return {}, (f"«{proveedor}» no está entre los {len(cat)} proveedores conocidos."
                    f"{pista} Lista completa: `genai proveedores`.")
    dial = _dialecto(p.get("npm", ""))
    if not dial:
        return {}, (f"«{proveedor}» usa {p.get('npm')}, que exige una firma propia "
                    f"(no es HTTP con una clave). No se puede hablar con lo que hay aquí.")
    if proveedor in FIRMA_DE_NUBE:
        return {}, (f"«{proveedor}» no se autentica con una clave en una cabecera, sino "
                    f"con la firma de su nube. Eso no es HTTP con `urllib` y no se "
                    f"puede hacer desde aquí sin añadir dependencias.")
    url = p.get("api") or URL_CONOCIDA.get(proveedor, "")
    if not url:
        return {}, (f"el catálogo no dice la URL de «{proveedor}». Escríbela a mano en "
                    f"claves.json: {{\"{proveedor}\": {{\"url\": \"https://…\", "
                    f"\"dialecto\": \"{dial}\", \"clave\": \"…\"}}}}")
    url, faltan = _sustituir_entorno(url)
    if faltan:
        return {}, faltan
    modelos = list((p.get("models") or {}).keys())
    return ({"dialecto": dial, "url": url.rstrip("/"),
             "modelo": modelos[0] if modelos else "",
             "env": (p.get("env") or [None])[0],
             "nombre": p.get("name", proveedor), "modelos": modelos}, queja)


def buscar(texto: str, tope: int = 25) -> list[tuple[str, str, str]]:
    """(proveedor, modelo, nombre legible) que casen con el texto."""
    cat, _ = descargar()
    t = texto.lower().strip()
    fuera = []
    for pid, p in sorted(cat.items()):
        for mid, m in (p.get("models") or {}).items():
            if not t or t in mid.lower() or t in pid.lower():
                fuera.append((pid, mid, m.get("name", mid)))
                if len(fuera) >= tope:
                    return fuera
    return fuera
