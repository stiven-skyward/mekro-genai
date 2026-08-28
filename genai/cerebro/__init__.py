"""cerebro/ — el modelo, enchufable. Ver base.py para el contrato y META.md para por qué.

    eco           determinista, sin modelo. Sirve para medir el ARNÉS aislado (M0).
    local_stream  el campeón v13 leído por capas desde disco. Correcto y lentísimo:
                  ~4,4 min/token en esta máquina. Existe para tener una referencia
                  de calidad, no para trabajar con él.
    local_packed  el campeón empaquetado a 2 bits reales en RAM. Es M1 y está por hacer
                  (holos/H1.md): hoy no existe el fichero porque no existe el formato.
"""
from .base import Cerebro, Llamada, Mensaje, Respuesta, Uso

__all__ = ["Cerebro", "Llamada", "Mensaje", "Respuesta", "Uso", "cargar"]


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
