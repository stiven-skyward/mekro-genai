"""Imágenes y PDFs (M7.4): que llegue de verdad, o que se diga que no llega.

La avería que estas pruebas existen para impedir es una sola y es silenciosa: **el
modelo responde con seguridad sobre una imagen que nunca recibió**. Pasa de dos formas
—el cerebro es de texto y nadie lo comprobó, o el proveedor tiró el adjunto por venir en
un sitio que no acepta— y las dos se ven igual desde fuera: una respuesta convincente.

Así que se vigila: que un cerebro de texto lo RECHACE, que el adjunto viaje donde los
tres proveedores lo aceptan, y que el tipo se decida por la firma del fichero y no por
la extensión que alguien escribió.
"""
import base64
import struct
import tempfile
import zlib
from pathlib import Path

from _util import Cuenta

from genai.cerebro.base import Mensaje
from genai.herramientas import estandar
from genai.herramientas.vista import _medio_real, para, ver
from genai.nucleo.sesion import Sesion

c = Cuenta("vista")
tmp = Path(tempfile.mkdtemp(prefix="vista-"))


def png(ruta: Path) -> Path:
    """Un PNG de 1×1 de verdad, construido a mano: sin dependencias nuevas."""
    def trozo(tipo, datos):
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))
    ruta.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + trozo(b"IEND", b""))
    return ruta


imagen = png(tmp / "punto.png")
(tmp / "doc.pdf").write_bytes(b"%PDF-1.4\n% de juguete\n")
(tmp / "vacio.png").write_bytes(b"")
(tmp / "texto.txt").write_text("no soy una imagen", encoding="utf-8")


class Texto:      # el cerebro OFICIAL: GGUF, solo texto
    multimodal = False


class Visual:     # un cerebro de nube que ve imágenes pero no acepta PDF
    multimodal = True
    pdf = False


class Completo:   # Gemini o Anthropic
    multimodal = True
    pdf = True


# ── la avería silenciosa: un cerebro de texto NO recibe bytes ───────────────
r = ver(str(imagen), cerebro=Texto())
c(not r.ok, "con un cerebro de solo texto, `ver` RECHAZA en vez de mandar bytes al vacío")
c("fingir" in r.salida, "y dice por qué: mandarlo sería fingir que lo miró")
c("nube:" in r.salida and "pdftotext" in r.salida,
  "el rechazo propone las dos salidas reales, no deja al modelo sin plan")
c(not ver(str(imagen), cerebro=None).ok,
  "sin cerebro declarado tampoco se manda: el silencio no se interpreta como que sí")

r = ver(str(tmp / "doc.pdf"), cerebro=Visual())
c(not r.ok and "pdftoppm" in r.salida,
  "un cerebro que ve imágenes pero no PDFs lo dice, y explica cómo convertirlo")
c(ver(str(imagen), cerebro=Visual()).ok,
  "pero ese mismo cerebro sí acepta la imagen: la capacidad se mira por tipo")

# ── el tipo lo decide la FIRMA, no la extensión ────────────────────────────
mentiroso = tmp / "en-realidad-es-png.jpg"
mentiroso.write_bytes(imagen.read_bytes())
r = ver(str(mentiroso), cerebro=Completo())
c(r.ok and r.datos["adjunto"]["medio"] == "image/png",
  "un PNG con extensión .jpg se declara como PNG: la extensión la escribe cualquiera, "
  "la firma es lo que el fichero ES")
c(_medio_real(b"%PDF-1.7 x") == "application/pdf", "el PDF se reconoce por su firma")
c(_medio_real(b"hola mundo") == "", "y lo que no es nada de esto, no se inventa")

# ── entradas degeneradas ───────────────────────────────────────────────────
c(not ver(str(tmp / "no-existe.png"), cerebro=Completo()).ok, "un fichero que no está")
c(not ver(str(tmp / "vacio.png"), cerebro=Completo()).ok, "un fichero vacío")
r = ver(str(tmp / "texto.txt"), cerebro=Completo())
c(not r.ok and "`leer`" in r.salida,
  "un fichero de texto se rechaza señalando la herramienta correcta")

# ── el adjunto llega íntegro y en un mensaje de usuario propio ──────────────
r = ver(str(imagen), cerebro=Completo())
c(r.ok and base64.b64decode(r.datos["adjunto"]["datos"]) == imagen.read_bytes(),
  "los bytes viajan intactos: lo que se codifica es el fichero, no una versión de él")
c("adjunto" not in r.salida.lower() or len(r.salida) < 200,
  "y lo que ve el modelo es un acuse corto, no el base64: eso se reenviaría cada vuelta")

s = Sesion(sistema="x")
s.adjuntar(r.datos["adjunto"])
m = s.mensajes[-1]
c(m.rol == "usuario" and len(m.adjuntos) == 1,
  "el adjunto va en un mensaje de USUARIO propio: ni Gemini ni OpenAI aceptan "
  "imágenes dentro de la respuesta a una llamada de herramienta")

# ── los tres dialectos lo emiten donde su API lo espera ────────────────────
from genai.cerebro.nube import CerebroNube  # noqa: E402

n = CerebroNube.__new__(CerebroNube)
msg = Mensaje("usuario", "mira", adjuntos=[r.datos["adjunto"]])

partes = n._gemini_contenidos([msg])[0]["parts"]
c(any("inlineData" in p for p in partes), "Gemini: inlineData")

bloques = n._bloques_adjuntos(msg)
c(bloques[0]["type"] == "image" and bloques[0]["source"]["type"] == "base64",
  "Anthropic: bloque `image` con source base64")
pdfm = Mensaje("usuario", "x", adjuntos=[{"medio": "application/pdf", "datos": "AA",
                                          "nombre": "d.pdf"}])
c(n._bloques_adjuntos(pdfm)[0]["type"] == "document",
  "Anthropic: un PDF va como `document`, no como `image`")

ops = n._partes_openai(msg)
c(any(p.get("type") == "image_url" for p in ops), "OpenAI: image_url con data: URI")
c(not any(p.get("type") == "image_url" for p in n._partes_openai(pdfm)),
  "OpenAI: un PDF NO se cuela como imagen; `ver` ya lo paró mirando cerebro.pdf")

# ── la herramienta en el registro ──────────────────────────────────────────
c("ver" in estandar(), "`ver` está en el juego estándar")
c(not estandar()["ver"].peligrosa, "y no es peligrosa: solo lee, como `leer`")
atado = para(Completo())[0]
c(atado.funcion(str(imagen)).ok,
  "el cerebro se ata al construir el registro, no con una global: dos sesiones con "
  "cerebros distintos en el mismo proceso no se pisan")

raise SystemExit(c.fin())
