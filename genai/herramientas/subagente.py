"""subagente.py — paralelismo DENTRO de una tarea (M7 brecha 1).

El problema, medido en este mismo proyecto: explorar cuesta contexto. Leer diez
módulos para encontrar uno mete diez observaciones gordas en la transcripción, y la
ventana se llena de material que ya no hace falta — C72 midió lo que eso cuesta.

La solución es la que usa Claude Code: **un subagente con contexto AISLADO**. Recibe
un encargo de exploración, trabaja en su propia sesión con herramientas de solo
lectura, y al terminar devuelve UNA conclusión. Lo que leyó muere con él; lo que
aprendió vuelve en un párrafo.

    contexto principal sin subagente:  encargo + 10 lecturas de 1.500 tokens = 15.000
    contexto principal con subagente:  encargo + 1 conclusión de ~200 tokens

Tres decisiones que lo hacen honesto:

1. **Solo lectura, siempre.** El subagente recibe `estandar(incluir_peligrosas=False)`:
   lee, busca, mira símbolos. No escribe, no ejecuta. Un explorador que edita es un
   agente suelto sin supervisión.
2. **Su presupuesto es suyo y acotado.** Vueltas y tokens propios; si se pasa, vuelve
   con lo que tenga y lo dice. Nunca hereda el presupuesto del padre.
3. **Paralelo de verdad solo si el cerebro lo permite.** Con un GGUF local hay UN
   modelo y una CPU: los subagentes van en serie y la ganancia es de CONTEXTO, no de
   reloj. Con cerebro de nube (o con la malla) sí hay concurrencia real y la ganancia
   es de las dos. El arnés no miente sobre esto: `paralelo` solo activa hilos cuando
   el cerebro es de nube.
"""
from __future__ import annotations

import concurrent.futures
import json
from typing import Sequence

from .base import Herramienta, Registro, Resultado

TOPES = {"tope_vueltas": 8, "tope_tokens": 2500, "tope_segundos": 900}

SISTEMA = """Eres un subagente de exploración de Mekro-Genai. Tu único trabajo es
AVERIGUAR y responder, no cambiar nada: solo tienes herramientas de lectura.

- Orientate con `grep` o `simbolos` antes de leer ficheros enteros.
- Cuando sepas la respuesta, respóndela SIN llamar a ninguna herramienta.
- Tu respuesta es lo ÚNICO que verá quien te preguntó: sé concreto, cita rutas y
  líneas, y no repitas el contenido de los ficheros — resume lo que significa."""


def _uno(encargo: str, cerebro_nombre: str, topes: dict) -> tuple[str, dict]:
    """Una exploración completa en sesión aislada. Devuelve (conclusión, cifras)."""
    from ..cerebro import cargar
    from ..nucleo import Politica, Sesion, turno
    from . import estandar

    cerebro = cargar(cerebro_nombre)
    sesion = Sesion(sistema=SISTEMA, cerebro=cerebro)
    # SIN la herramienta subagente: un subagente que puede lanzar subagentes es una
    # recursión sin fondo. La exploración anidada la decide el agente principal.
    base = estandar(incluir_peligrosas=False, plugins=False)
    registro = Registro([base[n] for n in sorted(base._por_nombre)
                         if n != "subagente"])
    r = turno(sesion, registro,
              Politica(modo="plan"),          # «plan» niega todo lo que escriba
              encargo, traza_por_pantalla=False, **topes)
    cifras = {"vueltas": r.vueltas, "tokens": r.uso.tokens_salida,
              "segundos": round(r.uso.segundos, 1), "motivo": r.motivo}
    texto = r.texto.strip() or "(el subagente no llegó a una conclusión)"
    if r.motivo != "fin":
        texto += f"\n[AVISO: el subagente paró por «{r.motivo}»: la respuesta puede " \
                 "estar incompleta.]"
    return texto, cifras


def explorar(encargos: list | str, cerebro: str = "", paralelo: bool = True) -> Resultado:
    """Lanza uno o varios subagentes de exploración y devuelve solo sus conclusiones."""
    if isinstance(encargos, str):
        encargos = [encargos]
    encargos = [str(e) for e in encargos if str(e).strip()][:6]   # tope de cordura
    if not encargos:
        return Resultado(False, "no hay nada que explorar: pasa uno o más encargos.")

    nombre = cerebro or _cerebro_por_defecto()
    # concurrencia real SOLO con cerebro de nube: con un GGUF local hay un modelo y
    # una CPU, y fingir hilos ahí solo añadiría contención
    hilos = len(encargos) if (paralelo and nombre.startswith("nube")) else 1

    resultados = []
    if hilos > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=hilos) as pool:
            futuros = [pool.submit(_uno, e, nombre, dict(TOPES)) for e in encargos]
            resultados = [f.result() for f in futuros]
    else:
        resultados = [_uno(e, nombre, dict(TOPES)) for e in encargos]

    partes, gasto = [], {"vueltas": 0, "tokens": 0, "segundos": 0.0}
    for encargo, (texto, cifras) in zip(encargos, resultados):
        partes.append(f"── {encargo[:90]}\n{texto}")
        for k in gasto:
            gasto[k] = round(gasto[k] + cifras.get(k, 0), 1)
    cabecera = (f"[{len(encargos)} subagente(s) · {'en paralelo' if hilos > 1 else 'en serie'}"
                f" · {gasto['vueltas']} vueltas y {gasto['tokens']} tokens SUYOS, que no "
                f"entran en tu contexto]")
    return Resultado(True, cabecera + "\n\n" + "\n\n".join(partes), {"gasto": gasto})


def _cerebro_por_defecto() -> str:
    """El subagente usa el mismo cerebro que la sesión padre, salvo que se le diga
    otro. Se resuelve por variable de entorno para no acoplar el registro al núcleo."""
    import os
    return os.environ.get("MG_CEREBRO", "gguf")


HERRAMIENTAS = [
    Herramienta(
        nombre="subagente",
        descripcion=(
            "Lanza subagentes de EXPLORACIÓN con contexto aislado y recibe solo sus "
            "conclusiones. Úsalo cuando averiguar algo exigiría leer mucho: «¿dónde "
            "se valida X?», «¿qué hace el paquete Y?». Puedes pasar VARIOS encargos "
            "a la vez y se resuelven juntos. Los subagentes solo LEEN: lo que "
            "descubran lo aplicas tú. Lo que ellos lean no ocupa tu contexto."),
        parametros={"type": "object", "properties": {
            "encargos": {"type": "array", "items": {"type": "string"},
                         "description": "una pregunta de exploración por subagente "
                                        "(máximo 6)"}},
            "required": ["encargos"]},
        peligrosa=False,
        funcion=explorar),
]
