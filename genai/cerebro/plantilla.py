"""plantilla.py — el formato Hermes de llamada a herramientas, que es el que Qwen trae
entrenado de fábrica.

POR QUÉ IMPORTA MÁS AQUÍ QUE EN OTROS ARNESES
---------------------------------------------
Un modelo grande de la nube tolera que le inventes un formato: si le pides «responde con
JSON entre corchetes triples», obedece. Un 27B a 2 bits, no: **desviarse del formato con
el que fue entrenado cuesta calidad medible y llamadas malformadas**, y aquí una llamada
malformada cuesta una vuelta entera del bucle, que son segundos o minutos.

Por eso el arnés habla EXACTAMENTE el dialecto de Qwen —que es el de Hermes, de Nous
Research—: definiciones de herramienta en JSON dentro de `<tools>` en el sistema, y
llamadas del modelo dentro de `<tool_call>`. No se inventa nada:

    <|im_start|>system
    …instrucciones…

    # Herramientas
    <tools>
    {"type":"function","function":{…}}
    </tools>
    Para llamar, devuelve dentro de <tool_call></tool_call>:
    <tool_call>
    {"name": …, "arguments": {…}}
    </tool_call><|im_end|>

El checkpoint trae su `chat_template.jinja`. Cuando haya tokenizador cargado se usa ESE
(`aplicar_plantilla_del_tokenizador`), porque es la verdad; lo de aquí es la
reimplementación que permite montar el prompt sin cargar 12 MB de tokenizador y, sobre
todo, saber qué se está mandando.

EL RAZONAMIENTO NO VUELVE (POR ESTA VÍA)
----------------------------------------
Qwen3 emite `<think>…</think>`. Ese bloque se guarda en la transcripción y `montar` NO lo
re-monta en el turno siguiente. OJO con el matiz que dejó C20 (2026-08-24): en el cerebro
GGUF los tokens crudos del razonamiento SÍ permanecen en la caché KV viva —quitarlos
obligaría a un borrado parcial que la caché del Qwen3.8 no admite, y el castigo medido es
re-evaluar el prompt entero: 3.359,5 s la carrera de humo—. `montar` sigue mandando aquí
para el arranque en frío y para cualquier cerebro sin caché; el camino incremental vive
en `local_gguf` y monta solo el SUFIJO con `montar_uno`.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Sequence

from .base import Llamada, Mensaje

INICIO, FIN = "<|im_start|>", "<|im_end|>"
ROL_HERMES = {"sistema": "system", "usuario": "user",
              "asistente": "assistant", "herramienta": "user"}

PREAMBULO_HERRAMIENTAS = """

# Herramientas

Puedes llamar a una o varias funciones. Sus firmas van dentro de <tools></tools>:
<tools>
{firmas}
</tools>

Para cada llamada devuelve un objeto JSON con el nombre y los argumentos dentro de
<tool_call></tool_call>:
<tool_call>
{{"name": "<nombre>", "arguments": <argumentos-json>}}
</tool_call>"""

_RE_LLAMADA = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S)
# Qwen3.8 NO emite JSON dentro de <tool_call> aunque el preámbulo se lo pida: revierte al
# formato XML con el que fue entrenado. Medido el 2026-08-23 con el GGUF Q2_K_XL, primera
# vuelta libre contra banco/n0. C8 no lo vio porque forzaba la decodificación sobre un oro
# que YA era JSON: en teacher forcing el modelo reproduce lo que se le da, y sólo generando
# libre se ve qué formato prefiere. Se acepta el suyo en vez de pelearse con él.
_RE_FUNC_XML = re.compile(r"<function=([\w.-]+)>\s*(.*?)\s*</function>", re.S)
_RE_PARAM_XML = re.compile(r"<parameter=([\w.-]+)>\s*(.*?)\s*</parameter>", re.S)
_RE_PENSAR = re.compile(r"<think>(.*?)</think>", re.S)


def montar_uno(m: Mensaje, herramientas: Sequence[dict] = (),
               primero: bool = False) -> str:
    """Un mensaje → su trozo exacto de plantilla. Es la pieza que permite montar solo
    el SUFIJO nuevo en el camino incremental de `local_gguf` (C20/C22)."""
    rol = ROL_HERMES[m.rol]
    cuerpo = m.contenido

    if m.rol == "sistema" and herramientas and primero:
        firmas = "\n".join(json.dumps(h, ensure_ascii=False) for h in herramientas)
        cuerpo += PREAMBULO_HERRAMIENTAS.format(firmas=firmas)

    if m.rol == "asistente" and m.llamadas:
        trozos = [cuerpo] if cuerpo else []
        for ll in m.llamadas:
            trozos.append("<tool_call>\n" + json.dumps(
                {"name": ll.nombre, "arguments": ll.argumentos},
                ensure_ascii=False) + "\n</tool_call>")
        cuerpo = "\n".join(trozos)

    if m.rol == "herramienta":
        cuerpo = f"<tool_response>\n{cuerpo}\n</tool_response>"

    return f"{INICIO}{rol}\n{cuerpo}{FIN}\n"


def montar(mensajes: Sequence[Mensaje], herramientas: Sequence[dict] = (),
           pensar: bool = True) -> str:
    """Los mensajes → el texto exacto que se le mete al modelo.

    `pensar=False` prellena `<think>\\n\\n</think>` al abrir el turno: es la convención
    de fábrica de Qwen3 (enable_thinking=false en su chat template) y apaga el
    razonamiento SIN salirse de la distribución de entrenamiento. Nació para el
    proponente del lazo (H6): dos vueltas reales murieron con 2.048 tokens de think
    sin llegar jamás al JSON pedido."""
    partes = [montar_uno(m, herramientas, primero=(i == 0))
              for i, m in enumerate(mensajes)]
    partes.append(f"{INICIO}assistant\n")
    if not pensar:
        partes.append("<think>\n\n</think>\n\n")
    return "".join(partes)


def separar_razonamiento(texto: str) -> tuple[str, str]:
    """Devuelve (razonamiento, respuesta). El primero no vuelve al contexto."""
    pensado = "\n".join(m.group(1).strip() for m in _RE_PENSAR.finditer(texto))
    return pensado, _RE_PENSAR.sub("", texto).strip()


def _llamadas_xml(crudo: str) -> list[Llamada]:
    """El formato XML de Qwen: <function=nombre><parameter=k>v</parameter></function>.

    Los valores llegan como texto, así que se intenta leerlos como JSON —para que un
    número siga siendo número y una lista siga siendo lista— y si no lo son se quedan
    como cadena, que es lo que el modelo quiso decir. No se adivina nada más: si no hay
    ni una función bien formada, se devuelve vacío y el que llama pone la queja.
    """
    fuera: list[Llamada] = []
    for f in _RE_FUNC_XML.finditer(crudo):
        args: dict = {}
        for p in _RE_PARAM_XML.finditer(f.group(2)):
            v = p.group(2)
            try:
                args[p.group(1)] = json.loads(v)
            except json.JSONDecodeError:
                args[p.group(1)] = v
        fuera.append(Llamada(nombre=f.group(1), argumentos=args, id=uuid.uuid4().hex[:8]))
    return fuera


def analizar_llamadas(texto: str) -> tuple[str, list[Llamada], list[str]]:
    """Texto generado → (prosa, llamadas, quejas).

    Las quejas son el mecanismo de recuperación: un `<tool_call>` con JSON roto NO se
    adivina ni se arregla en silencio. Se le devuelve al modelo la queja concreta para
    que reintente. Adivinar aquí es ejecutar algo que el modelo no pidió —y estas
    herramientas escriben en disco y corren shell.
    """
    llamadas: list[Llamada] = []
    quejas: list[str] = []
    for m in _RE_LLAMADA.finditer(texto):
        crudo = m.group(1)
        try:
            obj = json.loads(crudo)
        except json.JSONDecodeError as e:
            xml = _llamadas_xml(crudo)
            if xml:
                llamadas.extend(xml)
                continue
            quejas.append(f"tool_call con JSON inválido ({e.msg}): {crudo[:160]}")
            continue
        nombre = obj.get("name")
        args = obj.get("arguments", {})
        if not isinstance(nombre, str) or not nombre:
            quejas.append(f"tool_call sin «name»: {crudo[:160]}")
            continue
        if isinstance(args, str):                 # se le escapa a veces: JSON en cadena
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                quejas.append(f"«arguments» de {nombre} no es un objeto JSON: {args[:120]}")
                continue
        if not isinstance(args, dict):
            quejas.append(f"«arguments» de {nombre} debe ser un objeto, no {type(args).__name__}")
            continue
        llamadas.append(Llamada(nombre=nombre, argumentos=args, id=uuid.uuid4().hex[:8]))

    # Un `<tool_call>` abierto y sin cerrar es la firma de una generación truncada.
    if "<tool_call>" in texto and texto.count("<tool_call>") > texto.count("</tool_call>"):
        quejas.append("tool_call sin cerrar: la generación se truncó (sube max_tokens)")

    prosa = _RE_LLAMADA.sub("", texto).strip()
    return prosa, llamadas, quejas


def aplicar_plantilla_del_tokenizador(tokenizador, mensajes, herramientas=()):
    """La verdad, cuando hay tokenizador: el `chat_template.jinja` del checkpoint.

    Se prefiere SIEMPRE a `montar()` si el tokenizador está cargado. `montar()` existe
    para montar prompts sin pagar la carga del tokenizador y para poder ver, en las
    pruebas, exactamente qué se manda.
    """
    conv = []
    for m in mensajes:
        if m.rol == "herramienta":
            conv.append({"role": "tool", "content": m.contenido})
        elif m.rol == "asistente" and m.llamadas:
            conv.append({"role": "assistant", "content": m.contenido,
                         "tool_calls": [{"type": "function",
                                         "function": {"name": ll.nombre,
                                                      "arguments": ll.argumentos}}
                                        for ll in m.llamadas]})
        else:
            conv.append({"role": ROL_HERMES[m.rol], "content": m.contenido})
    return tokenizador.apply_chat_template(
        conv, tools=list(herramientas) or None,
        tokenize=False, add_generation_prompt=True)
