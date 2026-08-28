"""`ver`: imágenes y PDFs para el cerebro que pueda con ellos (M7.4).

**La honestidad que ordena este fichero**: el cerebro OFICIAL de este proyecto es un
GGUF de texto. No ve imágenes, y ningún envoltorio va a hacer que las vea. Así que esta
herramienta pregunta primero si el cerebro es multimodal y, si no lo es, **lo dice y
propone lo que sí funciona** en vez de mandar bytes que el proveedor tirará en silencio
o, peor, que el modelo fingirá haber visto.

Un adjunto que se traga alguien por el camino es la peor avería posible: el modelo
responde con seguridad sobre una imagen que nunca recibió.

**Por qué el adjunto viaja en un mensaje de usuario aparte** y no dentro de la
observación: Anthropic acepta imágenes en un `tool_result`, pero Gemini y OpenAI no. Un
solo camino que funciona en los tres vale más que tres caminos que hay que recordar.
"""
from __future__ import annotations

import base64
from pathlib import Path

from .base import Herramienta, Resultado

# Los proveedores rondan los 5 MB por fichero; se para antes y con un motivo, en vez de
# gastar la subida para que la rechacen al otro lado.
TOPE_BYTES = 5 * 1024 * 1024

MEDIOS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
}
# Firma real del fichero. La extensión la escribe quien crea el fichero; esto es lo que
# el fichero ES, y es lo que se le declara al proveedor.
FIRMAS = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
]


def _medio_real(cabeza: bytes) -> str:
    for firma, medio in FIRMAS:
        if cabeza.startswith(firma):
            return medio
    if cabeza[:4] == b"RIFF" and cabeza[8:12] == b"WEBP":
        return "image/webp"
    return ""


def ver(ruta: str, cerebro=None) -> Resultado:
    f = Path(ruta)
    if not f.is_file():
        return Resultado(False, f"no existe o no es un fichero: {ruta}")
    tam = f.stat().st_size
    if tam > TOPE_BYTES:
        return Resultado(False, f"{ruta} pesa {tam / 1e6:.1f} MB y el tope es "
                                f"{TOPE_BYTES / 1e6:.0f} MB. Recórtalo o baja su "
                                f"resolución antes de enseñármelo.")
    if tam == 0:
        return Resultado(False, f"{ruta} está vacío")

    crudo = f.read_bytes()
    medio = _medio_real(crudo[:16]) or MEDIOS.get(f.suffix.lower(), "")
    if not medio:
        return Resultado(False, f"{ruta} no es una imagen ni un PDF que reconozca "
                                f"(PNG, JPEG, GIF, WebP, PDF). Si es texto, léelo con "
                                f"`leer`.")

    puede = getattr(cerebro, "multimodal", False)
    if not puede:
        cual = "imágenes" if medio.startswith("image/") else "PDFs"
        return Resultado(False, (
            f"este cerebro es de solo texto y no ve {cual}: mandártelo sería fingir "
            f"que lo miré. Dos salidas reales: usa un cerebro de nube multimodal "
            f"(`--cerebro nube:gemini`, `nube:anthropic`), o pásame el contenido en "
            f"texto — para un PDF, `bash` con `pdftotext {ruta} -`."))
    if medio == "application/pdf" and not getattr(cerebro, "pdf", False):
        return Resultado(False, (
            f"este cerebro ve imágenes pero no acepta PDFs por API. Conviértelo "
            f"(`pdftoppm -png {ruta} pagina`) y enséñame las páginas como imagen, o "
            f"saca el texto con `pdftotext {ruta} -`."))

    return Resultado(
        True,
        f"adjunto {f.name} ({medio}, {tam / 1024:.0f} KB) — va en el mensaje siguiente",
        datos={"adjunto": {"medio": medio, "nombre": f.name,
                           "datos": base64.b64encode(crudo).decode("ascii")}})


def para(cerebro=None) -> list[Herramienta]:
    """`ver` necesita saber QUÉ cerebro va a mirar, porque la respuesta honesta
    depende de ello. Se ata aquí, al construir el registro, en vez de con una variable
    global: dos sesiones con cerebros distintos en el mismo proceso no deben pisarse."""
    import functools
    return [Herramienta(**{**vars(HERRAMIENTAS[0]),
                           "funcion": functools.partial(ver, cerebro=cerebro)})]


HERRAMIENTAS = [
    Herramienta(
        nombre="ver",
        descripcion=("Mírate una imagen (PNG, JPEG, GIF, WebP) o un PDF del disco. "
                     "Solo sirve si el cerebro es multimodal; si no lo es, te lo dice "
                     "y te propone la alternativa en vez de fingir que lo vio."),
        parametros={
            "type": "object",
            "properties": {"ruta": {"type": "string",
                                    "description": "ruta del fichero"}},
            "required": ["ruta"],
        },
        funcion=ver,
        peligrosa=False,      # solo lee, como `leer`
    ),
]
