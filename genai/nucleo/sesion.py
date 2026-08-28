"""sesion.py — el hilo de una conversación y su contabilidad.

DOS COSAS QUE OTROS ARNESES DAN POR SENTADAS Y AQUÍ NO
------------------------------------------------------
1. **La contabilidad es de primera clase.** META.md exige tokens y reloj de toda carrera.
   Si eso se calcula al final, a ojo, no es una medición. Se acumula aquí, vuelta a vuelta.
2. **El contexto tiene un techo y se choca contra él.** Con 32 K de ventana y salidas de
   herramienta de miles de caracteres, la sesión se llena en pocas vueltas. `presion()`
   dice cuánto queda ANTES de generar; `compactar()` decide qué se tira.

   La compactación por defecto es deliberadamente tonta y honesta: se tiran las
   observaciones de herramienta más viejas y se deja constancia de que se tiraron. Lo
   que Claude Code hace —resumir con el propio modelo— aquí cuesta una generación entera
   (minutos), así que la vía buena es la otra: **no llenarlo**, reconstruyendo contexto
   con hologramas en vez de acumulándolo. Ver META.md §puerta 1.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..cerebro.base import Llamada, Mensaje, Uso


@dataclass
class Sesion:
    sistema: str
    cerebro: object = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    mensajes: list[Mensaje] = field(default_factory=list)
    uso: Uso = field(default_factory=Uso)
    vueltas: int = 0
    intervenciones: int = 0
    compactaciones: int = 0
    inicio: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not self.mensajes:
            self.mensajes.append(Mensaje("sistema", self.sistema))

    # ── construir el hilo ───────────────────────────────────────────────────
    def usuario(self, texto: str) -> None:
        self.mensajes.append(Mensaje("usuario", texto))

    def asistente(self, texto: str, llamadas: list[Llamada] | None = None,
                  razonamiento: str = "") -> None:
        self.mensajes.append(Mensaje("asistente", texto, llamadas=llamadas or [],
                                     razonamiento=razonamiento))

    def observacion(self, id_llamada: str, texto: str) -> None:
        self.mensajes.append(Mensaje("herramienta", texto, id_llamada=id_llamada))

    # ── contabilidad ────────────────────────────────────────────────────────
    def anotar_uso(self, u: Uso) -> None:
        self.uso = self.uso + u
        self.vueltas += 1

    def presion(self) -> float:
        """Fracción del contexto ocupada. >0,8 y hay que hacer algo antes de generar."""
        cerebro = self.cerebro
        if cerebro is None:
            return 0.0
        # Se tokeniza el contenido REAL, no "x"*caracteres: el BPE comprime una tirada
        # del mismo carácter y aquello subestimaba por un factor 2,1 (medido 2026-08-24
        # sobre sesion.py entero: 1.329 tokens reales frente a 637 estimados). Con la
        # estimación corta, compactar() nunca saltaba y generar() moría por SystemExit.
        # Sigue siendo un suelo: la plantilla Hermes y el preámbulo de herramientas no
        # están aquí, por eso el umbral de 0,8 tiene que conservar ese margen.
        texto = "".join(m.contenido for m in self.mensajes)
        return cerebro.contar_tokens(texto) / cerebro.contexto_max

    def aprieta(self, max_tokens: int = 1024, sobrecarga: int = 1800) -> bool:
        """¿Toca renacer ANTES de generar? Dos reglas y CUALQUIERA manda: la fracción
        (0,8 de la ventana) y el HUECO ABSOLUTO. La segunda existe porque C72 midió la
        muerte exacta que la primera no ve: la plantilla, el preámbulo de herramientas
        y el turno por generar cuestan tokens FIJOS (~1.800 + max_tokens), y en una
        ventana chica ese coste fijo pesa más que cualquier porcentaje — la carrera
        murió a 7.730 de 8.000 con presion() en 0,78."""
        cerebro = self.cerebro
        if cerebro is None:
            return False
        # Sobre montar(), no sobre m.contenido: C72-bis murió DOS veces en el mismo
        # token (7.730/8.000) porque un mega-turno de 10 editar mete ~500 tokens de
        # JSON de llamadas más los envoltorios Hermes, invisibles para el contenido
        # crudo. Lo que se mide tiene que ser lo que el modelo VE; solo queda fuera
        # el preámbulo de herramientas (~1.100), cubierto por `sobrecarga`.
        from ..cerebro.plantilla import montar
        usados = cerebro.contar_tokens(montar(self.mensajes))
        return (usados / cerebro.contexto_max > 0.8
                or cerebro.contexto_max - usados < sobrecarga + max_tokens)

    def compactar(self, conservar_ultimas: int = 4) -> int:
        """Tira las observaciones de herramienta más viejas, DEJANDO CONSTANCIA.

        La constancia importa más de lo que parece: sin ella el modelo vuelve a pedir
        justo lo que se acaba de tirar, y entra en un bucle que cuesta vueltas caras.
        """
        indices = [i for i, m in enumerate(self.mensajes) if m.rol == "herramienta"]
        a_tirar = indices[:-conservar_ultimas] if len(indices) > conservar_ultimas else []
        if not a_tirar:
            return 0
        ahorro = 0
        for i in a_tirar:
            m = self.mensajes[i]
            ahorro += len(m.contenido)
            m.contenido = (f"[observación descartada por falta de contexto "
                           f"({len(m.contenido)} caracteres). Si la necesitas, "
                           "vuelve a pedirla acotada.]")
        self.compactaciones += 1
        return ahorro

    def _resumen_del_cerebro(self, hechas: list, tocados: list) -> str:
        """El resumen SEMÁNTICO (M7.2): lo escribe el cerebro y conserva el PORQUÉ.

        El mecánico dice «se llamó a editar sobre m3.py»; este dice «m3.py devolvía el
        signo cambiado y se corrigió, quedan m4-m9». Cuesta UNA generación extra
        (~400 tokens) y compra que el agente no repita trabajo ni pierda el hilo de su
        propia decisión — que es justo lo que C72 dejó como hipótesis sin medir.

        Si el cerebro falla o devuelve vacío, se cae al mecánico: perder el resumen
        jamás puede costar la sesión.

        El presupuesto es 2.000 y no 600 por una trampa medida: los modelos con
        razonamiento cuentan el think DENTRO de `maxOutputTokens` — con 600, Gemini
        3.7 gastó 579 pensando y devolvió 21 tokens de resumen truncado."""
        from ..cerebro.base import Mensaje

        peticion = next((m.contenido for m in self.mensajes if m.rol == "usuario"), "")
        # se le da la transcripción RECORTADA: lo que importa es la traza de
        # decisiones, no el contenido íntegro de lo leído
        traza = []
        for m in self.mensajes:
            if m.rol == "asistente":
                if m.contenido:
                    traza.append("PENSÉ: " + m.contenido[:400])
                for ll in m.llamadas:
                    traza.append("HICE: " + ll.firma())
            elif m.rol == "herramienta":
                traza.append("RESULTADO: " + m.contenido[:200])
        peticion_resumen = (
            "Resume el trabajo hecho hasta ahora para que puedas continuarlo sin "
            "repetir nada. En 6-10 frases, y en este orden: (1) qué se pedía; (2) qué "
            "has averiguado y qué has cambiado, con el PORQUÉ de cada decisión; (3) "
            "qué queda por hacer. Cita rutas concretas. No inventes nada que no esté "
            "en la traza.\n\nENCARGO ORIGINAL:\n" + peticion[:800]
            + "\n\nTRAZA:\n" + "\n".join(traza[-60:])[:6000])
        # modo híbrido (M7.1b): el resumidor puede ser un cerebro DISTINTO del
        # principal. Es lo que permite que un Qwen local conserve el PORQUÉ: el
        # resumen es una generación de prosa que en local cuesta minutos y en nube
        # segundos. Si no hay reparto, resume el cerebro de la sesión, como siempre.
        try:
            from ..cerebro import cargar_rol, para_rol
            propio = getattr(self.cerebro, "nombre", "")
            del_rol = para_rol("resumidor", propio)
            cerebro = (self.cerebro if del_rol == propio
                       else cargar_rol("resumidor", propio)[0])
            r = cerebro.generar(
                [Mensaje("sistema", "Resumes tu propio trabajo para continuarlo. "
                                    "Directo, concreto y sin adornos."),
                 Mensaje("usuario", peticion_resumen)], (), max_tokens=2000)
            texto = (r.texto or "").strip()
            if texto and del_rol != propio:
                self.gasto_auxiliar = getattr(self, "gasto_auxiliar", 0) + \
                    r.uso.tokens_salida
        except Exception:
            texto = ""
        return texto

    def renacer(self, conservar_ultimas: int = 4, semantico: bool = False) -> int:
        """El renacimiento (M5 brecha 1): la transcripción entera se sustituye por un
        contexto NUEVO y pequeño — sistema, petición original, resumen mecánico de lo
        hecho, y las últimas vueltas—. Cuesta UN prefill frío pequeño. Las alternativas
        están medidas y son peores: `compactar()` reescribe por el medio y, con la
        caché sin borrado parcial (C20), eso cuesta un frío del contexto GRANDE; y no
        hacer nada acaba en SystemExit al desbordar la ventana. El resumen es mecánico
        (determinista, gratis); un resumen escrito por el cerebro es una hipótesis
        futura que tendrá su ciclo. Devuelve los caracteres liberados."""
        antes = sum(len(m.contenido) for m in self.mensajes)
        peticion = next((m for m in self.mensajes if m.rol == "usuario"), None)
        hechas: list[str] = []
        tocados: list[str] = []
        for m in self.mensajes:
            if m.rol != "asistente":
                continue
            for ll in m.llamadas:
                hechas.append(ll.firma())
                ruta = (ll.argumentos or {}).get("ruta") if isinstance(
                    ll.argumentos, dict) else None
                if ll.nombre in ("editar", "escribir") and ruta and ruta not in tocados:
                    tocados.append(ruta)
        cuerpo = self._resumen_del_cerebro(hechas, tocados) if semantico else ""
        if not cuerpo:            # mecánico: siempre disponible, nunca miente
            cuerpo = (f"Llamadas ya ejecutadas ({len(hechas)}), en orden:\n- "
                      + "\n- ".join(hechas[-40:])
                      + (f"\nFicheros ya modificados: {', '.join(tocados)}"
                         if tocados else ""))
        elif tocados:             # el semántico se ancla con los hechos duros
            cuerpo += f"\n\n[Ficheros ya modificados: {', '.join(tocados)}]"
        resumen = (
            "[RENACIMIENTO: la transcripción anterior se resumió aquí para no "
            "desbordar la ventana. NO repitas lo ya hecho; continúa desde este punto.]\n"
            + cuerpo)
        nuevos = [m for m in self.mensajes if m.rol == "sistema"][:1]
        if peticion is not None:
            nuevos.append(peticion)
        nuevos.append(Mensaje("usuario", resumen))
        cola = [m for m in self.mensajes[-conservar_ultimas:] if m not in nuevos]
        # una observación sin su asistente delante es un huérfano de plantilla
        while cola and cola[0].rol == "herramienta":
            cola.pop(0)
        self.mensajes = nuevos + cola
        self.compactaciones += 1
        return antes - sum(len(m.contenido) for m in self.mensajes)

    # ── persistencia ────────────────────────────────────────────────────────
    def a_dict(self) -> dict:
        return {"id": self.id, "inicio": self.inicio, "vueltas": self.vueltas,
                "intervenciones": self.intervenciones,
                "compactaciones": self.compactaciones,
                "uso": {"tokens_entrada": self.uso.tokens_entrada,
                        "tokens_salida": self.uso.tokens_salida,
                        "segundos": self.uso.segundos,
                        "tokens_por_segundo": round(self.uso.tokens_por_segundo, 3)},
                "mensajes": [{"rol": m.rol, "contenido": m.contenido,
                              "llamadas": [{"nombre": l.nombre,
                                            "argumentos": l.argumentos, "id": l.id}
                                           for l in m.llamadas],
                              "id_llamada": m.id_llamada,
                              "razonamiento": m.razonamiento}
                             for m in self.mensajes]}

    @classmethod
    def de_dict(cls, d: dict, cerebro) -> "Sesion":
        """La vuelta a la vida (M5 brecha 2): reconstruye la sesión guardada tal cual.
        El primer `generar` tras cargar re-prefilla la transcripción entera UNA vez
        (proceso nuevo, caché vacía); de ahí en adelante el append-exacto de C22 vuelve
        a pagar solo el sufijo."""
        s = cls(sistema="", cerebro=cerebro)
        s.mensajes = [
            Mensaje(m["rol"], m["contenido"],
                    llamadas=[Llamada(l["nombre"], l["argumentos"], id=l.get("id", ""))
                              for l in m.get("llamadas", [])],
                    id_llamada=m.get("id_llamada", ""),
                    razonamiento=m.get("razonamiento", ""))
            for m in d.get("mensajes", [])]
        s.id = d.get("id", s.id)
        s.inicio = d.get("inicio", s.inicio)
        s.vueltas = d.get("vueltas", 0)
        s.intervenciones = d.get("intervenciones", 0)
        s.compactaciones = d.get("compactaciones", 0)
        uso = d.get("uso") or {}
        s.uso = Uso(uso.get("tokens_entrada", 0), uso.get("tokens_salida", 0),
                    uso.get("segundos", 0.0))
        return s

    def guardar(self, directorio: Path | str = "logs/sesiones") -> Path:
        d = Path(directorio)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{self.inicio[:10]}_{self.id}.json"
        p.write_text(json.dumps(self.a_dict(), indent=2, ensure_ascii=False),
                     encoding="utf-8")
        return p
