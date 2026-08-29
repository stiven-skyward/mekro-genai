"""bucle.py — plan → herramienta → observación → plan. El corazón, y es pequeño a propósito.

TODO ARNÉS AGÉNTICO ES ESTE BUCLE. Lo que los distingue no es el bucle sino **dónde
ponen los topes**. Aquí los topes no son defensa contra un modelo que se despista: son
el presupuesto de META.md hecho código.

    tope_vueltas   cada vuelta cuesta un prefill del contexto entero + una generación
    tope_tokens    el presupuesto real por tarea es de 2-5 K tokens generados
    tope_segundos  una carrera de banco que no acaba no puntúa

Cuando salta un tope, el bucle **no** miente diciendo que terminó: devuelve `motivo` y
eso va al registro. Una tarea agotada por presupuesto y una tarea fallada son cosas
distintas y se cuentan distinto.

LAS QUEJAS DE FORMATO SON PARTE DEL BUCLE
-----------------------------------------
Un modelo de 2 bits emite `<tool_call>` malformados con una frecuencia que un modelo
grande no tiene. `plantilla.analizar_llamadas` no adivina: devuelve quejas, y el bucle
se las devuelve al modelo como una observación más. Es más barato reintentar con la
queja concreta que reintentar a ciegas, y muchísimo más barato que ejecutar algo que
el modelo no pidió.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from .. import deshacer, tui
from ..cerebro.base import Uso
from ..ahorro import podar


def _env_si(clave: str, defecto: bool) -> bool:
    """La poda viene puesta; se apaga para medir el A/B (MG_PODA=0)."""
    v = __import__("os").environ.get(clave)
    return defecto if v is None else v.strip().lower() not in ("0", "no", "false")
from ..herramientas.base import Registro
from .permisos import Politica
from .sesion import Sesion


@dataclass
class Resultado:
    """Lo que sale de un turno. Las cuatro cifras de META.md salen de aquí."""
    motivo: str                    # «fin» | «tope_vueltas» | «tope_tokens» | «tope_segundos»
    texto: str                     # la última respuesta en prosa del cerebro
    vueltas: int
    uso: Uso
    intervenciones: int
    traza: list[dict] = field(default_factory=list)

    @property
    def terminado_bien(self) -> bool:
        return self.motivo == "fin"


def turno(sesion: Sesion, registro: Registro, politica: Politica,
          peticion: str, *, tope_vueltas: int = 24, tope_tokens: int = 6000,
          poda: bool = _env_si("MG_PODA", True),
          pensar_vueltas: int = 0,
          tope_segundos: int = 1800, preguntar: Callable | None = None,
          traza_por_pantalla: bool = True) -> Resultado:
    """Un encargo del usuario hasta que el cerebro deja de pedir herramientas."""
    from ..cerebro.plantilla import analizar_llamadas   # tarde: evita importar de más

    sesion.usuario(peticion)
    firmas = registro.firmas()
    t0 = time.time()
    traza: list[dict] = []
    ultimo_texto = ""
    # deshacer.py: el contenido de un fichero justo ANTES de que este turno lo toque
    # por primera vez —no antes de cada llamada suelta—, para que «deshaz lo que
    # acabo de pedir» sea la unidad, no «deshaz la tercera de las cinco ediciones».
    punto_control: dict[str, str | None] = {}

    for vuelta in range(1, tope_vueltas + 1):
        # think selectivo (C79→C80): el razonamiento vive donde se forma el criterio
        # (las primeras vueltas, el diagnóstico) y solo cuesta en las mecánicas.
        # 0 = pensar siempre, como toda la vida.
        if pensar_vueltas and hasattr(sesion.cerebro, "pensar"):
            sesion.cerebro.pensar = vuelta <= pensar_vueltas
        if sesion.uso.tokens_salida >= tope_tokens:
            return _fin("tope_tokens", ultimo_texto, sesion, traza, peticion, punto_control)
        if time.time() - t0 > tope_segundos:
            return _fin("tope_segundos", ultimo_texto, sesion, traza, peticion, punto_control)

        # los avisos de fondo llegan al EMPEZAR la vuelta: un agente síncrono no tiene
        # interrupciones, tiene vueltas (M5.3). Cada aviso se entrega una sola vez.
        from ..herramientas.fondo import avisos_pendientes
        for aviso in avisos_pendientes():
            sesion.usuario(f"[AVISO DE FONDO] {aviso}")
            traza.append({"vuelta": vuelta, "aviso_fondo": aviso})
            if traza_por_pantalla:
                print(tui.atenuado(f"  ·· {aviso}"))

        # El conteo EXACTO de lo que el modelo verá: mensajes montados MÁS las firmas
        # de herramientas, tokenizados de verdad. C72 murió dos veces en el mismo token
        # (7.730/8.000) por ESTIMAR — contenido crudo primero, montar sin firmas
        # después—; medir cuesta un tokenizado por vuelta y no miente. El margen es el
        # turno por generar (1024) más 200 de respiración. aprieta() queda como red.
        from ..cerebro.plantilla import montar as _montar
        entrada_exacta = sesion.cerebro.contar_tokens(_montar(sesion.mensajes, firmas))
        # El camino incremental arrastra el think crudo que montar NO ve (C72 murió
        # dos veces por eso): el contexto real allí es la caché viva del cerebro MÁS
        # el sufijo nuevo (lo posterior al último turno del asistente).
        vivo = getattr(sesion.cerebro, "tokens_en_contexto", lambda: 0)()
        if vivo:
            ultimo = max((i for i, m in enumerate(sesion.mensajes)
                          if m.rol == "asistente"), default=-1)
            sufijo = _montar(sesion.mensajes[ultimo + 1:]) if ultimo >= 0 else ""
            entrada_exacta = max(entrada_exacta,
                                 vivo + sesion.cerebro.contar_tokens(sufijo))
        if (entrada_exacta + 1024 + 200 > sesion.cerebro.contexto_max
                or sesion.aprieta()):
            # renacer y no compactar: C20 midió que reescribir por el medio cuesta un
            # arranque en frío del contexto GRANDE (la caché no admite borrado
            # parcial); renacer paga un frío PEQUEÑO y la tarea sigue viva (M5.1).
            # semántico si el cerebro es barato en reloj (nube: ~2 s por resumen);
            # mecánico con cerebro local, donde una generación extra cuesta minutos.
            # Mismo criterio honesto que el paralelismo del subagente.
            # semántico si el RESUMIDOR es barato en reloj — que en modo híbrido
            # puede ser de nube aunque el principal sea el Qwen local (M7.1b)
            from ..cerebro import para_rol
            _propio = str(getattr(sesion.cerebro, "nombre", ""))
            semantico = para_rol("resumidor", _propio).startswith("nube")
            ahorro = sesion.renacer(semantico=semantico)
            if hasattr(sesion.cerebro, "olvidar"):
                sesion.cerebro.olvidar()   # la caché vieja no casa con la vida nueva
            traza.append({"vuelta": vuelta, "renacimiento": ahorro})
            if traza_por_pantalla and ahorro:
                print(tui.atenuado(f"  ·· renacimiento: {ahorro} caracteres resumidos"))

        # 1024 y no el 512 por defecto: C24 midió una llamada truncada por el tope en
        # mitad del tool_call (rojo, vuelta 3: 512 tokens justos de think más llamada),
        # y cada truncado cuesta ~una vuelta (~400-500 s) en reemitir. La generación se
        # detiene sola en el EOS, así que el presupuesto no gastado no cuesta nada; el
        # gasto total por tarea lo sigue acotando tope_tokens.
        r = sesion.cerebro.generar(sesion.mensajes, firmas, max_tokens=1024)
        sesion.anotar_uso(r.uso)
        ultimo_texto = r.texto or ultimo_texto
        sesion.asistente(r.texto, r.llamadas, r.razonamiento)

        if r.motivo_parada == "interrumpido":
            # Ctrl-C a mitad de generación (M5.5): lo generado queda en la sesión,
            # el turno cierra con su motivo, y --continuar retoma donde se cortó.
            return _fin("interrumpido", ultimo_texto, sesion, traza, peticion, punto_control)

        if traza_por_pantalla:
            print(tui.atenuado(
                f"[{vuelta}] {r.uso.tokens_salida} tok · {r.uso.segundos:.1f} s"
                + (f" · {len(r.llamadas)} llamadas" if r.llamadas else "")))
            if r.texto and r.llamadas:
                # con llamadas de por medio esto es el razonamiento de paso, no la
                # respuesta final — se enseña recortado y sin markdown para no
                # confundirlo con el texto de cierre del turno
                print(tui.atenuado("  " + r.texto[:400].replace("\n", "\n  ")))

        # Formato roto: se le devuelve la queja concreta y se reintenta.
        _, _, quejas = analizar_llamadas(_recomponer(r))
        if quejas and not r.llamadas:
            sesion.observacion("", "Tu llamada a herramienta no se pudo leer:\n- "
                               + "\n- ".join(quejas)
                               + "\nVuelve a emitirla dentro de <tool_call>…</tool_call> "
                                 "con JSON válido.")
            traza.append({"vuelta": vuelta, "quejas": quejas})
            continue

        if not r.llamadas:
            # Un turno CORTADO por el tope de tokens no es una respuesta final: C29
            # midió la primera tarea n3 FALLANDO porque el think de diseño gastó el
            # turno entero sin llegar a ninguna llamada y esto lo daba por «fin» con
            # el presupuesto a medias (1.215 de 3.000 tokens). Se le pide continuar;
            # el contexto append-exacto hace barato el reintento (el think cortado ya
            # está en la caché KV) y tope_vueltas/tope_tokens frenan la reincidencia.
            if r.motivo_parada == "tope_tokens":
                sesion.usuario("Tu turno se cortó por el tope de tokens antes de "
                               "emitir ninguna llamada. No repitas lo pensado: emite "
                               "YA la llamada a herramienta o la respuesta final.")
                traza.append({"vuelta": vuelta, "cortado": "tope_tokens sin llamadas"})
                if traza_por_pantalla:
                    print(tui.atenuado("  ·· turno cortado sin llamadas: se le pide continuar"))
                continue
            return _fin("fin", ultimo_texto, sesion, traza, peticion, punto_control)

        for ll in r.llamadas:
            if ll.nombre not in registro:
                sesion.observacion(ll.id, f"no existe la herramienta «{ll.nombre}»")
                continue
            h = registro[ll.nombre]
            # la intención se enseña ANTES de decidir: Claude Code y OpenCode pintan
            # la tarjeta de la llamada aunque acabe vetada o denegada — es lo que se
            # PIDIÓ, y eso importa tanto como lo que se permitió.
            if traza_por_pantalla:
                print(tui.linea_herramienta(ll.firma()))
            d = politica.decidir(h, ll.argumentos, preguntar)
            if not d.permitido:
                sesion.intervenciones += 1
                sesion.observacion(ll.id, f"DENEGADO: {d.motivo}")
                traza.append({"vuelta": vuelta, "llamada": ll.firma(), "denegado": d.motivo})
                if traza_por_pantalla:
                    print(tui.linea_resultado(False, f"DENEGADO: {d.motivo}"))
                continue
            t1 = time.time()
            res = registro.invocar(ll.nombre, ll.argumentos)
            seg = time.time() - t1
            # PODA EN EL ORIGEN (docs/ahorro.md). Este es el único sitio por donde una
            # observación entra en la transcripción, y por tanto el único donde se puede
            # ahorrar sin romper el prefijo cacheado. Se aprieta según lo que le queda
            # de vida al dato: lo que entra pronto se reenvía muchas más veces.
            texto, ahorro = podar(ll.nombre, res.recortado(),
                                  vueltas_restantes=max(1, tope_vueltas - vuelta),
                                  activo=poda)
            sesion.ahorro["antes"] += ahorro["antes"]
            sesion.ahorro["despues"] += ahorro["despues"]
            sesion.observacion(ll.id, texto)
            # M7.4: una imagen no cabe en una observación —Gemini y OpenAI no las
            # aceptan ahí— así que viaja en un mensaje de usuario propio, justo
            # detrás. Un adjunto que el proveedor tira en silencio es peor que no
            # mandarlo: el modelo respondería con seguridad sobre algo que no vio.
            datos = res.datos or {}
            adj = datos.get("adjunto")
            if adj:
                sesion.adjuntar(adj)
            if res.ok and ll.nombre in ("editar", "escribir") and "despues" in datos:
                ruta = datos.get("ruta")
                # solo el PRIMER toque de este turno a esta ruta cuenta como punto de
                # control: si el mismo turno la edita dos veces, deshacer tiene que
                # devolver el estado de ANTES DEL TURNO, no el de la edición anterior.
                if ruta and ruta not in punto_control:
                    existia = not datos.get("creado", False)
                    punto_control[ruta] = datos.get("antes", "") if existia else None
            traza.append({"vuelta": vuelta, "llamada": ll.firma(),
                          "ok": res.ok, "segundos": round(seg, 2)})
            if traza_por_pantalla:
                resumen = (res.salida.splitlines() or [""])[0]
                print(tui.linea_resultado(res.ok, resumen, seg))
                if res.ok and ll.nombre in ("editar", "escribir") and "despues" in datos:
                    print(tui.diff(datos.get("antes", ""), datos["despues"]))

    return _fin("tope_vueltas", ultimo_texto, sesion, traza, peticion, punto_control)


def _recomponer(respuesta) -> str:
    """El texto tal cual salió del modelo, para poder detectar quejas de formato."""
    partes = [respuesta.texto]
    for ll in respuesta.llamadas:
        partes.append(f"<tool_call>{ll.nombre}</tool_call>")
    return "\n".join(p for p in partes if p)


def _fin(motivo: str, texto: str, sesion: Sesion, traza: list[dict],
        peticion: str, punto_control: dict[str, str | None]) -> Resultado:
    # el punto de control se guarda pase lo que pase —hasta un `tope_segundos` a
    # medias puede haber tocado ficheros, y ESOS son justo los que más interesa poder
    # deshacer sin gastar otra vuelta entera en pedirlo de nuevo.
    deshacer.guardar(sesion.id, peticion, punto_control)
    return Resultado(motivo=motivo, texto=texto, vueltas=sesion.vueltas,
                     uso=sesion.uso, intervenciones=sesion.intervenciones, traza=traza)
