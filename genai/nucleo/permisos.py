"""permisos.py — quién decide si una llamada se ejecuta.

Se toma de Claude Code la idea de **modo de permiso** (una política, no una pregunta
suelta por llamada) y se le añade lo que aquí hace falta: las carreras del banco corren
solas y de noche, así que el modo por defecto de una carrera no puede ser «pregúntale a
un humano». La política tiene que ser **legible antes de arrancar** y quedar en el
registro, para que una carrera se pueda reproducir sabiendo qué se le permitió.

MODOS
-----
    plan       nada que escriba. Solo leer, buscar, grep. Para explorar sin riesgo.
    preguntar  lo peligroso se consulta por consola. Es el modo interactivo por defecto.
    lista      lo peligroso se permite si casa con la lista blanca. Es el modo de carrera.
    todo       todo pasa. Solo dentro de un sandbox desechable (ver docs/arquitectura.md
               §OpenChamber): en el repositorio de verdad, esto es cómo se pierde trabajo.

EL VETO DURO
------------
Hay comandos que no se permiten en NINGÚN modo, ni siquiera en «todo». No es paranoia:
es que un modelo pequeño confunde con facilidad el directorio de la tarea con la raíz, y
el coste esperado de esa confusión no tiene comparación con lo que se gana permitiéndola.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MODOS = ("plan", "preguntar", "lista", "todo")

# Se comprueba sobre el comando normalizado. Cada patrón lleva su porqué al lado.
VETO = [
    (r"\brm\s+(-[a-zA-Z]*\s+)*(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\s+/(\s|$)",
     "rm -rf sobre la raíz del sistema"),
    (r"\brm\s+.*\s+~(/\s*)?$", "rm sobre el directorio personal entero"),
    (r":\(\)\s*\{.*\}\s*;\s*:", "fork bomb"),
    (r"\bmkfs(\.\w+)?\b", "formatear un sistema de ficheros"),
    (r"\bdd\b.*\bof=/dev/(sd|nvme|hd)", "escribir a crudo sobre un disco"),
    (r">\s*/dev/(sd|nvme|hd)\w+", "redirigir a un dispositivo de bloque"),
    (r"\bgit\s+push\b.*--force", "reescribir historia remota"),
    (r"\bchmod\s+(-R\s+)?777\s+/(\s|$)", "abrir permisos de la raíz"),
    (r"\bcurl\b[^|]*\|\s*(ba)?sh", "ejecutar lo que devuelva la red"),
    (r"\bwget\b[^|]*\|\s*(ba)?sh", "ejecutar lo que devuelva la red"),
]

# Lo que una carrera del banco necesita y basta. Se amplía a mano y se justifica.
# Toda herramienta que ejecute UN COMANDO DE SHELL pasa por el veto, las rutas
# vedadas y la lista blanca por igual: si solo se mirara «bash», un lanzador de
# fondo (M5.3) sería un agujero por el que colar cualquier cosa.
EJECUTAN_SHELL = ("bash", "fondo_lanzar")

LISTA_BLANCA = [
    r"^(ls|cat|head|tail|wc|find|grep|rg|file|stat|du|df|pwd|echo|which|nproc|free)\b",
    r"^git\s+(status|diff|log|show|branch|rev-parse|ls-files)\b",
    r"^python3?\s+-m\s+(pytest|unittest)\b",
    r"^python3?\s+[\w./-]+\.py(\s|$)",
    # C23 midió 4 intervenciones (~600 s) por rechazar `python3 -c`: es verificación
    # legítima de una línea, no un agujero. `python` a secas sigue fuera: no existe
    # en la máquina y el prompt de sistema ya lo avisa.
    r"^python3\s+-c\s",
    r"^(pytest|mypy|ruff|black)\b",
    r"^python3\s+(holograma|ciclo)\.py\b",
    r"^(make|npm\s+test|cargo\s+test)\b",
]


def _ejecuta_shell(herramienta) -> bool:
    """Por nombre (las de fábrica) O por declaración (los plugins de M5.4)."""
    return (herramienta.nombre in EJECUTAN_SHELL
            or getattr(herramienta, "ejecuta_shell", False))


@dataclass
class Decision:
    permitido: bool
    motivo: str = ""


@dataclass
class Politica:
    modo: str = "preguntar"
    lista_blanca: list[str] = field(default_factory=lambda: list(LISTA_BLANCA))
    # H6: el agente que investiga el arnés NO puede tocar su propio examen. Una ruta
    # vedada es de solo lectura en TODO modo: editar/escribir ahí se deniega, y un bash
    # que la nombre junto a algo que muta, también. Es un guardarraíl contra el
    # accidente y el atajo cómodo, no un sandbox: la trampa deliberada la para la
    # revisión del registro, no este regex.
    vedadas: list[str] = field(default_factory=list)
    # Se rellena en cada carrera: qué se preguntó y qué se contestó. Va al registro.
    historial: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.modo not in MODOS:
            raise ValueError(f"modo desconocido: {self.modo!r} (modos: {MODOS})")

    def decidir(self, herramienta, argumentos: dict, preguntar=None) -> Decision:
        d = self._decidir(herramienta, argumentos, preguntar)
        self.historial.append({"herramienta": herramienta.nombre,
                               "permitido": d.permitido, "motivo": d.motivo})
        return d

    def _decidir(self, herramienta, argumentos: dict, preguntar) -> Decision:
        if _ejecuta_shell(herramienta):
            comando = " ".join(str(argumentos.get("comando", "")).split())
            for patron, porque in VETO:
                if re.search(patron, comando):
                    # El veto es anterior al modo: ni «todo» lo levanta.
                    return Decision(False, f"VETADO ({porque}). Este comando no se "
                                           "ejecuta en ningún modo de permiso.")
        if self.vedadas:
            if herramienta.nombre in ("editar", "escribir"):
                ruta = str(argumentos.get("ruta", ""))
                for v in self.vedadas:
                    if ruta.startswith(v) or f"/{v}" in ruta:
                        return Decision(False, f"VEDADO: «{v}» es de solo lectura para "
                                               "este agente, en todo modo de permiso.")
            if _ejecuta_shell(herramienta):
                orden = str(argumentos.get("comando", ""))
                muta = re.search(r"\brm\b|\bmv\b|\bcp\b|sed\s+-i|\btee\b|>>?|"
                                 r"\btruncate\b|\bchmod\b", orden)
                for v in self.vedadas:
                    if v in orden and muta:
                        return Decision(False, f"VEDADO: «{v}» solo se lee; ese comando "
                                               "podría escribir ahí y no se ejecuta.")
        if not herramienta.peligrosa:
            return Decision(True, "solo lectura")
        if self.modo == "plan":
            return Decision(False, "modo «plan»: en este turno no se escribe ni se "
                                   "ejecuta nada. Propón el cambio en texto.")
        if self.modo == "todo":
            return Decision(True, "modo «todo»")
        if self.modo == "lista":
            if not _ejecuta_shell(herramienta):
                return Decision(True, "escritura de fichero permitida en modo «lista»")
            return self._contra_lista(str(argumentos.get("comando", "")))
        # modo «preguntar»
        if preguntar is None:
            return Decision(False, "modo «preguntar» sin nadie a quien preguntar: una "
                                   "carrera desatendida debe correr en modo «lista».")
        return preguntar(herramienta, argumentos)


    def _contra_lista(self, comando: str) -> Decision:
        """Cada trozo del comando por separado, y nada que esconda un comando.

        Anclar el patrón al principio NO basta: «ls; rm -rf ~» empieza por «ls» y casaría
        con la lista blanca entera. Y una sustitución —`$(…)` o comillas invertidas— mete
        un comando ENTERO donde la comprobación no lo ve. Ambas cosas convierten una lista
        blanca en decoración.
        """
        if "$(" in comando or "`" in comando or "${" in comando:
            return Decision(False, "modo «lista»: no se admiten sustituciones de comando "
                                   "($(…), `…`): esconden un comando que la lista blanca "
                                   "no puede comprobar.")
        if "<(" in comando or ">(" in comando:
            return Decision(False, "modo «lista»: no se admite sustitución de proceso.")
        trozos = [t.strip() for t in re.split(r"\|\||&&|[;|\n]", comando) if t.strip()]
        if not trozos:
            return Decision(False, "comando vacío")
        for trozo in trozos:
            if not any(re.search(pat, trozo) for pat in self.lista_blanca):
                return Decision(False, f"modo «lista»: «{trozo[:60]}» no está en la lista "
                                       "blanca. Usa una herramienta específica o pide que "
                                       "se amplíe la lista (y que quede justificado).")
        return Decision(True, f"los {len(trozos)} trozos casan con la lista blanca")


def _vista_previa_edicion(herramienta, argumentos: dict) -> str | None:
    """Diff ANTES de aprobar —lo que Claude Code enseña en su propio modal de
    permiso—, calculado en memoria y sin tocar disco: si algo falla (ambiguo, ruta
    inexistente) se calla y se cae al recuadro de argumentos normal; la validación de
    verdad la sigue haciendo `editar()`/`escribir()` cuando de verdad se ejecute."""
    from .. import tui
    try:
        from pathlib import Path
        ruta = Path(str(argumentos.get("ruta", "")))
        if herramienta.nombre == "escribir":
            antes = ruta.read_text(encoding="utf-8", errors="ignore") if ruta.exists() else ""
            return tui.diff(antes, str(argumentos.get("contenido", "")))
        if herramienta.nombre == "editar" and ruta.exists():
            original = ruta.read_text(encoding="utf-8")
            texto = original
            for c in argumentos.get("cambios", []):
                viejo, nuevo = c.get("buscar", ""), c.get("poner", "")
                if texto.count(viejo) == 1:
                    texto = texto.replace(viejo, nuevo, 1)
            return tui.diff(original, texto)
    except Exception:  # noqa: BLE001 — esto es solo una vista previa, no la edición
        return None
    return None


def preguntar_por_consola(herramienta, argumentos: dict) -> Decision:
    import json

    from .. import tui

    lineas = [f"{tui.resalte(herramienta.nombre)} quiere ejecutar:"]
    previa = (_vista_previa_edicion(herramienta, argumentos)
             if herramienta.nombre in ("editar", "escribir") else None)
    if previa:
        lineas += previa.split("\n")
    else:
        cuerpo = json.dumps(argumentos, ensure_ascii=False, indent=2)
        lineas += ["  " + l for l in cuerpo.splitlines()]
    print()
    print(tui.caja(lineas, titulo="permiso"))
    try:
        r = input(f"  {tui.negrita('¿permitir?')} [s/N] ").strip().lower()
    except EOFError:
        return Decision(False, "sin terminal para preguntar")
    return Decision(r in ("s", "si", "sí", "y"), "decidido por el humano")
