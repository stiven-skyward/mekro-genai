"""cerebro/ — el modelo, enchufable. Ver base.py para el contrato y META.md para por qué.

    eco           determinista, sin modelo. Sirve para medir el ARNÉS aislado (M0).
    local_stream  el campeón v13 leído por capas desde disco. Correcto y lentísimo:
                  ~4,4 min/token en esta máquina. Existe para tener una referencia
                  de calidad, no para trabajar con él.
    local_packed  el campeón empaquetado a 2 bits reales en RAM. Es M1 y está por hacer
                  (holos/H1.md): hoy no existe el fichero porque no existe el formato.
"""
from .base import Cerebro, Llamada, Mensaje, Respuesta, Uso

__all__ = ["Cerebro", "Llamada", "Mensaje", "Respuesta", "Uso", "cargar",
           "para_rol", "cargar_rol", "ROLES"]

# ── MODO HÍBRIDO: un cerebro por ROL (M7.1b) ────────────────────────────────
# El reparto que el autor pidió, generalizado: el cerebro local sigue siendo el
# PRINCIPAL —quien decide y edita, donde vive la soberanía del proyecto— y los papeles
# auxiliares pueden ir a un modelo de nube con la clave del usuario.
#
# Por qué estos dos roles y no otros, con las cifras de este proyecto delante:
#
#   subagente   explorar son MUCHAS vueltas baratas en tokens y carísimas en reloj:
#               el prefill domina. Medido: 3 exploraciones = 22 vueltas (~11 min en
#               local, 46 s en nube). Es donde el cerebro local más sangra tiempo.
#   resumidor   el resumen del renacimiento es UNA generación de prosa. En local
#               cuesta minutos y por eso el defecto ahí es el resumen mecánico; con
#               un resumidor de nube, el Qwen local también conserva el PORQUÉ.
#
# Tres reglas que lo hacen honesto:
#   1. La nube NUNCA es carga crítica: si falta la clave o el proveedor falla, el rol
#      cae al cerebro principal. Sin nube, todo sigue funcionando igual.
#   2. Una carrera híbrida NO es una carrera local: el registro anota los dos cerebros
#      y sus tokens por separado. Comparar sus cifras con las de M2 sería mentir.
#   3. Se configura a mano y se ve: `~/.config/genai/cerebros.json` o `--cerebro-ROL`.
ROLES = ("principal", "subagente", "resumidor")


def _config_roles() -> dict:
    import json
    import os
    from pathlib import Path as _P
    ruta = _P(os.environ.get("MG_CEREBROS",
                             _P.home() / ".config" / "genai" / "cerebros.json"))
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def para_rol(rol: str, defecto: str = "") -> str:
    """Qué cerebro le toca a este papel. Precedencia: entorno → fichero → principal.

    El entorno gana para que una carrera pueda fijar el reparto sin tocar la
    configuración del usuario, que es como el banco mide sin efectos laterales."""
    import os
    if rol not in ROLES:
        raise ValueError(f"rol desconocido: {rol!r} (roles: {ROLES})")
    env = os.environ.get(f"MG_CEREBRO_{rol.upper()}")
    if env:
        return env
    cfg = _config_roles().get(rol)
    if cfg:
        return cfg
    # el principal manda: sin reparto explícito, todo el mundo usa el mismo cerebro
    return defecto or os.environ.get("MG_CEREBRO", "gguf")


def cargar_rol(rol: str, defecto: str = "", **kw):
    """Carga el cerebro del rol, CAYENDO al principal si el suyo no se puede.

    Es la regla 1 hecha código: la nube nunca es carga crítica. Devuelve
    (cerebro, nombre_real) para que el registro sepa qué se usó de verdad."""
    nombre = para_rol(rol, defecto)
    try:
        return cargar(nombre, **kw), nombre
    except SystemExit as e:
        respaldo = defecto or "gguf"
        if nombre == respaldo:
            raise
        print(f"⚠ el cerebro «{nombre}» del rol {rol} no está disponible ({e}); "
              f"se sigue con «{respaldo}»")
        return cargar(respaldo, **kw), respaldo


def cargar(nombre: str, **kw):
    """Fábrica por nombre. Deliberadamente explícita: elegir cerebro es una decisión
    de experimento, no una variable de entorno que se cuela sin que nadie la vea."""
    if nombre == "eco":
        from .eco import CerebroEco
        return CerebroEco(**kw)
    if nombre == "local_stream":
        from .local_stream import CerebroStream
        return CerebroStream(**kw)
    if nombre == "nube" or nombre.startswith("nube:"):
        # `nube:proveedor` o `nube:proveedor/modelo` — la clave la pone el usuario en
        # ~/.config/genai/claves.json. Una carrera de nube NUNCA cuenta como local.
        from .nube import CerebroNube
        resto = nombre.split(":", 1)[1] if ":" in nombre else "gemini"
        prov, _, modelo = resto.partition("/")
        return CerebroNube(prov or "gemini", modelo, **kw)
    if nombre == "gguf":
        from .local_gguf import CerebroGGUF
        return CerebroGGUF(**kw)
    if nombre == "local_packed":
        raise SystemExit(
            "local_packed no existe todavía: es el hito M1 y depende de H1 "
            "(empaquetar qwen38-h13b a 2 bits reales). `python3 holograma.py foco H1`")
    raise SystemExit(f"cerebro desconocido: {nombre!r} (eco, gguf, local_stream, local_packed)")
