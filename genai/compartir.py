"""Compartir una sesión: un HTML autocontenido, sin nube y sin cuenta.

OpenCode comparte pegando la sesión en un servidor suyo y dando un enlace. Aquí eso no
cabe: un arnés cuya identidad es no depender de terceros no puede necesitar el servidor
de nadie para que enseñes tu propia conversación. Así que se exporta a **un fichero
HTML que se abre solo**, sin CSS ni tipografías de fuera, y que se manda por donde uno
mande sus ficheros. Si además quieres un enlace, `genai sesiones servir` ya lo sirve en
tu máquina.

**El tachado no es un extra: es la razón de que este fichero exista.** Una transcripción
guarda TODO lo que el agente leyó. Si leyó un `.env`, un `claves.json` o pegó una URL
firmada, eso está dentro. Compartir sin mirar es la forma más fácil de filtrar una clave
que hay en todo el proyecto, y pasa justo cuando uno está contento con el resultado y
quiere enseñarlo.

Tres decisiones que salen de ahí:

1. **Se tacha por patrón y se DICE cuántas veces.** Tachar en silencio sería peor:
   quien comparte necesita saber que su sesión llevaba secretos, no solo que ya no los
   lleva.
2. **El tachado es de mejor esfuerzo y se admite.** Una lista de patrones no puede
   cazarlo todo — una clave interna de tu empresa no se parece a nada conocido. El
   fichero lo dice en su cabecera, para que quien comparta mire antes de mandar.
3. **No se sube a ninguna parte.** Exportar deja un fichero. Publicarlo es una decisión
   humana y separada.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

# Lo que se tacha. Cada patrón viene de una familia de credenciales real; lo genérico
# —«password»— se deja fuera a propósito, porque tachar de más llena el documento de
# agujeros y acaba en que nadie mira los avisos.
PATRONES = [
    ("clave de Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("clave de OpenAI", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("clave de Google", re.compile(r"AIza[A-Za-z0-9_\-]{30,}")),
    ("clave de Google (OAuth)", re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}")),
    ("token de GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("token de Slack", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("clave de AWS", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("cabecera Authorization", re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)"
                                          r"[A-Za-z0-9._\-]{16,}")),
    ("clave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?"
                                 r"-----END [A-Z ]*PRIVATE KEY-----")),
    ("URL con credenciales", re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")),
]


def tachar(texto: str) -> tuple[str, dict[str, int]]:
    """Devuelve (texto tachado, {familia: veces}). Nunca devuelve el original a medias."""
    cuenta: dict[str, int] = {}
    for nombre, patron in PATRONES:
        def _sub(m, _n=nombre):
            cuenta[_n] = cuenta.get(_n, 0) + 1
            # se conserva el prefijo capturado cuando lo hay (Authorization:, https://)
            cabeza = m.group(1) if m.groups() else ""
            return f"{cabeza}[TACHADO: {_n}]"
        texto = patron.sub(_sub, texto)
    return texto, cuenta


_CSS = """
:root{--fondo:#fbfbfa;--texto:#1a1a19;--tenue:#6b6b66;--linea:#e3e3df;
--usuario:#eef2ff;--asist:#fff;--herr:#f5f5f3;--acento:#3d5afe;--mal:#c1121f}
:root:not([data-tema="claro"]){@media (prefers-color-scheme:dark){
:root{--fondo:#161614;--texto:#e8e6e3;--tenue:#9a978f;--linea:#2e2c28;
--usuario:#1c2333;--asist:#1d1b18;--herr:#201e1a;--acento:#8fa4ff;--mal:#ff6b6b}}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1rem;background:var(--fondo);color:var(--texto);
font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:52rem;margin:0 auto}
h1{font-size:1.3rem;margin:0 0 .2rem}
.meta{color:var(--tenue);font-size:.85rem;margin-bottom:1.5rem}
.aviso{border:1px solid var(--mal);border-radius:8px;padding:.8rem 1rem;
margin-bottom:1.5rem;font-size:.9rem}
.aviso b{color:var(--mal)}
.m{border:1px solid var(--linea);border-radius:10px;padding:.7rem .9rem;margin:.7rem 0}
.usuario{background:var(--usuario)} .asistente{background:var(--asist)}
.herramienta{background:var(--herr)}
.rol{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;
color:var(--tenue);margin-bottom:.35rem}
pre{white-space:pre-wrap;word-wrap:break-word;margin:.4rem 0;font:13px/1.5
ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto}
.llamada{border-left:3px solid var(--acento);padding-left:.7rem;margin:.5rem 0}
.tachado{background:var(--mal);color:#fff;padding:0 .25rem;border-radius:3px;
font-weight:600}
footer{color:var(--tenue);font-size:.8rem;margin-top:2rem;border-top:1px solid
var(--linea);padding-top:1rem}
"""


def _pre(texto: str) -> str:
    t = html.escape(texto)
    return re.sub(r"\[TACHADO: ([^\]]+)\]",
                  r'<span class="tachado">[TACHADO: \1]</span>', t)


def _tachar_hondo(x, cuenta: dict[str, int]):
    """Tacha CADA cadena del árbol, no el JSON serializado.

    Tachar sobre `json.dumps(...)` parece más simple y está mal: ahí un salto de línea
    es la letra `n` literal detrás de una barra, así que los patrones anclados con `\b`
    —AWS, el OAuth de Google— dejan de casar y el secreto SE ESCAPA. Lo encontró la
    prueba, que mira el HTML final y no el contador."""
    if isinstance(x, str):
        limpio, c2 = tachar(x)
        for k, v in c2.items():
            cuenta[k] = cuenta.get(k, 0) + v
        return limpio
    if isinstance(x, dict):
        return {k: _tachar_hondo(v, cuenta) for k, v in x.items()}
    if isinstance(x, list):
        return [_tachar_hondo(v, cuenta) for v in x]
    return x


def a_html(transcripcion: dict, titulo: str = "") -> tuple[str, dict[str, int]]:
    cuenta: dict[str, int] = {}
    d = _tachar_hondo(transcripcion, cuenta)

    u = d.get("uso") or {}
    cab = [f'<h1>{html.escape(titulo or "Sesión de Mekro-Genai")}</h1>',
           f'<div class="meta">{html.escape(str(d.get("inicio", "")))[:19]} · '
           f'{d.get("vueltas", 0)} vueltas · {u.get("tokens_salida", 0)} tokens de '
           f'salida / {u.get("tokens_entrada", 0)} de entrada · '
           f'{d.get("intervenciones", 0)} intervenciones</div>']

    total = sum(cuenta.values())
    if total:
        detalle = ", ".join(f"{n} ×{v}" for n, v in sorted(cuenta.items()))
        cab.append(f'<div class="aviso"><b>Se tacharon {total} posibles secretos</b> '
                   f'({html.escape(detalle)}).<br>El tachado va por patrones conocidos '
                   f'y <b>no puede cazarlo todo</b>: una credencial interna no se parece '
                   f'a nada conocido. Lee esto antes de mandarlo a alguien.</div>')
    else:
        cab.append('<div class="aviso">No se encontró ningún secreto de los patrones '
                   'conocidos. Eso <b>no</b> es garantía: el tachado es de mejor '
                   'esfuerzo. Léelo antes de compartirlo.</div>')

    cuerpo = []
    for m in d.get("mensajes", []):
        rol = m.get("rol", "?")
        partes = [f'<div class="rol">{html.escape(rol)}</div>']
        if m.get("contenido"):
            partes.append(f"<pre>{_pre(m['contenido'])}</pre>")
        for ll in m.get("llamadas") or []:
            # los argumentos ya vienen tachados por _tachar_hondo, campo a campo
            args = json.dumps(ll.get("argumentos", {}), ensure_ascii=False)[:2000]
            partes.append(f'<div class="llamada"><pre>{html.escape(ll.get("nombre",""))}'
                          f'({_pre(args)})</pre></div>')
        cuerpo.append(f'<div class="m {html.escape(rol)}">{"".join(partes)}</div>')

    pagina = (f"<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
              f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
              f"<title>{html.escape(titulo or 'Sesión de Mekro-Genai')}</title>"
              f"<style>{_CSS}</style></head><body><main>"
              + "".join(cab) + "".join(cuerpo)
              + "<footer>Exportado por Mekro-Genai. Fichero autocontenido: no pide "
                "nada a ninguna red al abrirse.</footer></main></body></html>")
    return pagina, cuenta


def exportar(transcripcion: dict, destino: Path | str,
             titulo: str = "") -> tuple[Path, dict[str, int]]:
    pagina, cuenta = a_html(transcripcion, titulo)
    p = Path(destino)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(pagina, encoding="utf-8")
    return p, cuenta
