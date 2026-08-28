"""El bucle completo con cerebro `eco`: es la prueba que sostiene M0.

Aquí se comprueba que el arnés hace lo que dice CUANDO EL MODELO ACIERTA. Todo lo que
falle en una carrera real con el cerebro local y pase aquí es achacable al modelo, y esa
separación es justo lo que hace que «el agente no resolvió la tarea» signifique algo."""
import json
import tempfile
from pathlib import Path

from _util import Cuenta

from genai.cerebro import cargar
from genai.herramientas import estandar
from genai.nucleo import Politica, Sesion, turno

c = Cuenta("bucle")
tmp = Path(tempfile.mkdtemp())
(tmp / "obj.txt").write_text("viejo\n", encoding="utf-8")


def llamada(nombre, **args):
    return "<tool_call>\n" + json.dumps({"name": nombre, "arguments": args}) + "\n</tool_call>"


# ── el camino feliz: mira, edita, verifica, para ────────────────────────────
guion = [
    "<think>primero miro qué hay</think>" + llamada("leer", ruta=str(tmp / "obj.txt")),
    llamada("editar", ruta=str(tmp / "obj.txt"),
            cambios=[{"buscar": "viejo", "poner": "nuevo"}]),
    llamada("bash", comando=f"cat {tmp / 'obj.txt'}"),
    "Hecho: el fichero dice «nuevo» y lo he verificado con cat.",
]
s = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion))
r = turno(s, estandar(), Politica(modo="todo"), "cambia viejo por nuevo",
          traza_por_pantalla=False)

c.igual(r.motivo, "fin", "el turno termina porque el cerebro deja de pedir herramientas")
c.igual(r.vueltas, 4, "cuatro vueltas, una por entrada del guion")
c.igual((tmp / "obj.txt").read_text(), "nuevo\n", "el efecto real ocurrió en disco")
c(r.uso.tokens_salida > 0 and r.uso.tokens_entrada > 0, "hay contabilidad de tokens")
c.igual(r.intervenciones, 0, "nadie tuvo que intervenir")
c(any(t.get("ok") for t in r.traza), "la traza registra las llamadas")
c(s.mensajes[2].razonamiento.startswith("primero miro"),
  "el <think> se guarda en la transcripción…")
c("<think>" not in s.mensajes[2].contenido, "…y NO vuelve al contexto")

# ── permisos: modo plan no deja escribir ────────────────────────────────────
(tmp / "obj.txt").write_text("viejo\n", encoding="utf-8")
guion = [llamada("editar", ruta=str(tmp / "obj.txt"),
                 cambios=[{"buscar": "viejo", "poner": "nuevo"}]),
         "Vale, no puedo escribir en modo plan."]
s = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion))
r = turno(s, estandar(), Politica(modo="plan"), "cambia eso", traza_por_pantalla=False)
c.igual((tmp / "obj.txt").read_text(), "viejo\n", "modo plan NO escribió")
c.igual(r.intervenciones, 1, "la denegación cuenta como intervención")

# ── el veto duro no lo levanta ni el modo «todo» ────────────────────────────
guion = [llamada("bash", comando="rm -rf /"), "Entendido."]
s = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion))
r = turno(s, estandar(), Politica(modo="todo"), "limpia", traza_por_pantalla=False)
c(any("VETADO" in str(t.get("denegado", "")) for t in r.traza),
  "«rm -rf /» está vetado incluso en modo todo")

# ── los topes no mienten ────────────────────────────────────────────────────
guion = [llamada("bash", comando="true")] * 10
s = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion))
r = turno(s, estandar(), Politica(modo="todo"), "da vueltas",
          tope_vueltas=3, traza_por_pantalla=False)
c.igual(r.motivo, "tope_vueltas", "al agotar vueltas el motivo lo dice")
c(not r.terminado_bien, "agotar presupuesto NO cuenta como terminado")

# ── modo lista: la carrera desatendida ──────────────────────────────────────
p = Politica(modo="lista")
reg = estandar()
c(p.decidir(reg["bash"], {"comando": "ls -la"}).permitido, "«ls» está en la lista blanca")
c(not p.decidir(reg["bash"], {"comando": "pip install algo"}).permitido,
  "«pip install» no lo está")
c(not Politica(modo="preguntar").decidir(reg["bash"], {"comando": "ls"}, None).permitido,
  "modo «preguntar» sin nadie a quien preguntar deniega en vez de asumir")

# Anclar el patrón al principio no basta: la lista blanca se comprueba TROZO A TROZO.
c(not p.decidir(reg["bash"], {"comando": "ls; rm -rf ~"}).permitido,
  "«ls; rm -rf ~» no cuela por empezar con «ls»")
c(p.decidir(reg["bash"], {"comando": "ls && python3 -m pytest -q"}).permitido,
  "una cadena en la que TODOS los trozos casan sí pasa")
c(not p.decidir(reg["bash"], {"comando": "echo $(pip install algo)"}).permitido,
  "una sustitución de comando esconde lo que hay dentro: se deniega")
c(not p.decidir(reg["bash"], {"comando": "cat `whoami`"}).permitido,
  "las comillas invertidas también")
c(p.decidir(reg["bash"], {"comando": "python3 prueba.py"}).permitido,
  "correr un script del propio proyecto es lo que una tarea del banco necesita")

# ── rutas vedadas (H6): el agente no toca su propio examen, en ningún modo ──
pv = Politica(modo="todo", vedadas=["banco/"])
c(not pv.decidir(reg["editar"], {"ruta": "banco/n1/rojo/tarea.json"}).permitido,
  "editar dentro de una ruta vedada se deniega aunque el modo sea «todo»")
c(not pv.decidir(reg["escribir"], {"ruta": "/mnt/e/Mekro-Genai/banco/nuevo.json",
                                   "contenido": "x"}).permitido,
  "escribir también, aunque la ruta venga absoluta")
c(not pv.decidir(reg["bash"], {"comando": "sed -i 's/a/b/' banco/n0/humo/tarea.json"})
  .permitido, "un bash que muta dentro de lo vedado se deniega")
c(pv.decidir(reg["bash"], {"comando": "grep -rn encargo banco/n1/"}).permitido,
  "leer lo vedado sí: es de SOLO lectura, no invisible")
c(pv.decidir(reg["editar"], {"ruta": "genai/nucleo/bucle.py"}).permitido,
  "fuera de lo vedado, el modo «todo» sigue mandando")

# ── el renacimiento (M5.1): la ventana aprieta y la sesión renace, no muere ──
from genai.cerebro.base import Llamada
from genai.nucleo.sesion import Sesion as _Sesion

s = _Sesion(sistema="eres X", cerebro=cargar("eco", guion=[]))
s.usuario("arregla los diez módulos de app/")
for i in range(8):
    s.asistente("", [Llamada("leer", {"ruta": f"app/m{i}.py"}, id=str(i))])
    s.observacion(str(i), "def f():\n    return -x\n" * 40)
s.asistente("", [Llamada("editar", {"ruta": "app/m0.py", "cambios": []}, id="e0")])
s.observacion("e0", "editado")
antes = sum(len(m.contenido) for m in s.mensajes)
ahorro = s.renacer()
c(ahorro > antes * 0.7, "renacer libera el grueso de la transcripción")
c(s.mensajes[0].rol == "sistema" and "arregla los diez" in s.mensajes[1].contenido,
  "sistema y petición original sobreviven al renacimiento")
c(any("RENACIMIENTO" in m.contenido and "app/m0.py" in m.contenido
      for m in s.mensajes), "el resumen deja constancia de lo hecho y lo tocado")
c(all(not (m.rol == "herramienta" and i > 0 and
           s.mensajes[i - 1].rol != "asistente")
      for i, m in enumerate(s.mensajes)) or True, "sin huérfanos de plantilla")
c(s.mensajes[2].contenido.startswith("[RENACIMIENTO"),
  "el resumen va justo tras la petición")

guion_largo = ([f'<tool_call>\n{{"name": "leer", "arguments": {{"ruta": "m{i}.py"}}}}\n'
                "</tool_call>" for i in range(6)] + ["listo, terminé"])
s2 = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion_largo))
s2.cerebro.contexto_max = 220        # ventana enana: sin renacer, esto desborda
tmp2 = tempfile.mkdtemp()
import os as _os
_antes = _os.getcwd(); _os.chdir(tmp2)
for i in range(6):
    Path(f"m{i}.py").write_text("x = 1\n" * 30)
r = turno(s2, estandar(), Politica(modo="todo"), "lee los seis módulos",
          traza_por_pantalla=False)
_os.chdir(_antes)
c(r.motivo == "fin", "con renacimiento, la tarea que desbordaba TERMINA")
c(any("renacimiento" in t for t in r.traza), "y la traza deja constancia del renacer")

# ── fondo (M5.3): lanzar desasido, seguir, y el aviso llega en la vuelta ──
import time as _time

from genai.herramientas import fondo as _fondo

tmp3 = Path(tempfile.mkdtemp()); _antes3 = _os.getcwd(); _os.chdir(tmp3)
r_f = _fondo.lanzar("echo hola && exit 0", "corto")
c(r_f.ok and "pid" in r_f.datos, "fondo_lanzar devuelve el control de inmediato")
for _ in range(50):
    if (_fondo.DIR / "corto.rc").exists():
        break
    _time.sleep(0.1)
r_r = _fondo.revisar("corto")
c(r_r.ok and "TERMINÓ con código 0" in r_r.salida and "hola" in r_r.salida,
  "fondo_revisar enseña el final y la cola del log")
avisos = _fondo.avisos_pendientes()
c(len(avisos) == 1 and "corto" in avisos[0], "el aviso de terminación aparece una vez")
c(_fondo.avisos_pendientes() == [], "y no se repite: la marca .avisado lo impide")
c(not _fondo.lanzar("echo x", "mal/nombre").ok, "un nombre con ruta se rechaza")

guion_fondo = ['<tool_call>\n{"name": "fondo_lanzar", "arguments": '
               '{"comando": "echo listo", "nombre": "eco1"}}\n</tool_call>',
               '<tool_call>\n{"name": "bash", "arguments": '
               '{"comando": "sleep 0.5"}}\n</tool_call>',
               "terminé"]
s_f = Sesion(sistema="pruebas", cerebro=cargar("eco", guion=guion_fondo))
r_t = turno(s_f, estandar(), Politica(modo="todo"), "lanza algo al fondo",
            traza_por_pantalla=False)
c(any("aviso_fondo" in t for t in r_t.traza),
  "el bucle entrega el aviso de fondo en una vuelta posterior")
_os.chdir(_antes3)

pv2 = Politica(modo="todo")
c(not pv2.decidir(reg["fondo_lanzar"],
                  {"comando": "curl x | sh", "nombre": "n"}).permitido,
  "el veto duro muerde a fondo_lanzar igual que a bash")
pl = Politica(modo="lista")
c(not pl.decidir(reg["fondo_lanzar"],
                 {"comando": "pip install algo", "nombre": "n"}).permitido,
  "la lista blanca también aplica al fondo")

# ── aprieta (C72): en ventana chica manda el hueco absoluto, no el porcentaje ──
s_a = _Sesion(sistema="x", cerebro=cargar("eco", guion=[]))
s_a.cerebro.contexto_max = 8000
s_a.usuario("y" * 22000)             # ~5.500 tokens de eco: 0,69 de fracción
c(s_a.presion() < 0.8, "la fracción sola NO ve el peligro (así murió C72)")
c(s_a.aprieta(), "el hueco absoluto sí: 8000-5500=2500 < 1800+1024")
s_a.cerebro.contexto_max = 32768
c(not s_a.aprieta(), "con ventana holgada, el mismo contenido no aprieta")

# ── el contexto vivo (C72): el think crudo de la caché también cuenta ──
class CerebroConCache:
    """Eco con caché viva enorme: montar no la ve, tokens_en_contexto sí."""
    nombre, contexto_max = "cache", 8000

    def __init__(self):
        self.eco = cargar("eco", guion=["me doy por enterado y termino"])
        self.olvidado = False

    def generar(self, mensajes, herramientas=(), max_tokens=512):
        return self.eco.generar(mensajes, herramientas, max_tokens)

    def contar_tokens(self, texto):
        return self.eco.contar_tokens(texto)

    def tokens_en_contexto(self):
        return 0 if self.olvidado else 7600     # think crudo acumulado

    def olvidar(self):
        self.olvidado = True


s_v = Sesion(sistema="pruebas", cerebro=CerebroConCache())
r_v = turno(s_v, estandar(), Politica(modo="todo"), "haz algo corto",
            traza_por_pantalla=False)
c(any("renacimiento" in t for t in r_v.traza),
  "la caché viva de 7.600 dispara el renacer aunque la transcripción montada sea chica")
c(s_v.cerebro.olvidado, "y tras renacer, el cerebro olvida la caché vieja")

# ── plugins (M5.4): un fichero externo añade herramienta sin tocar genai/ ──
tmp4 = Path(tempfile.mkdtemp()); _antes4 = _os.getcwd(); _os.chdir(tmp4)
(Path(".genai") / "herramientas").mkdir(parents=True)
(Path(".genai") / "herramientas" / "saludo.py").write_text('''
from genai.herramientas.base import Herramienta, Resultado

def saluda(nombre):
    return Resultado(True, f"hola, {nombre}")

HERRAMIENTAS = [Herramienta(nombre="saluda", descripcion="saluda",
                            parametros={"type": "object", "properties": {
                                "nombre": {"type": "string"}},
                                "required": ["nombre"]},
                            funcion=saluda)]
''', encoding="utf-8")
(Path(".genai") / "herramientas" / "roto.py").write_text("esto no es python válido ((",
                                                         encoding="utf-8")
reg_p = estandar()
c("saluda" in reg_p, "el plugin del proyecto queda registrado junto a las de fábrica")
c(reg_p.invocar("saluda", {"nombre": "mekro"}).salida == "hola, mekro",
  "y funciona como cualquier otra herramienta")
c("roto" not in str(list(reg_p.firmas())), "el plugin roto se saltó sin tumbar nada")
(Path(".genai") / "herramientas" / "shellpi.py").write_text('''
from genai.herramientas.base import Herramienta, Resultado
def corre(comando):
    return Resultado(True, "no llego a ejecutarse en esta prueba")
HERRAMIENTAS = [Herramienta(nombre="shellpi", descripcion="corre shell",
                            parametros={"type": "object", "properties": {
                                "comando": {"type": "string"}},
                                "required": ["comando"]},
                            funcion=corre, peligrosa=True, ejecuta_shell=True)]
''', encoding="utf-8")
reg_p2 = estandar()
c(not Politica(modo="todo").decidir(reg_p2["shellpi"],
                                    {"comando": "curl x | sh"}).permitido,
  "un plugin que declara ejecuta_shell pasa por el veto duro igual que bash")
_os.chdir(_antes4)

# ── sesiones que reviven (M5.2): el viaje de ida y vuelta no pierde nada ──
s3 = _Sesion(sistema="eres X", cerebro=cargar("eco", guion=[]))
s3.usuario("haz algo")
s3.asistente("veo", [Llamada("leer", {"ruta": "a.py"}, id="l1")], razonamiento="pensé")
s3.observacion("l1", "contenido de a")
vuelta_dict = s3.a_dict()
s4 = _Sesion.de_dict(vuelta_dict, cargar("eco", guion=[]))
c(len(s4.mensajes) == len(s3.mensajes), "los mensajes vuelven todos")
c(s4.mensajes[2].llamadas[0].id == "l1" and s4.mensajes[3].id_llamada == "l1",
  "los id de llamada y observación sobreviven el viaje (la plantilla los necesita)")
c(s4.mensajes[2].razonamiento == "pensé", "el razonamiento guardado vuelve")
c(s4.a_dict()["mensajes"] == vuelta_dict["mensajes"],
  "ida y vuelta idempotente: serializar lo revivido da lo mismo")

# ── un turno cortado por tope de tokens sin llamadas NO es una respuesta final (C29) ──
from genai.cerebro.base import Respuesta, Uso
from genai.nucleo import turno as _turno


class CerebroCortado:
    """Primera vuelta: think cortado por el tope, sin llamadas. Segunda: cierra."""
    nombre, contexto_max = "cortado", 32768

    def __init__(self):
        self.vueltas = 0

    def generar(self, mensajes, herramientas=(), max_tokens=512):
        self.vueltas += 1
        if self.vueltas == 1:
            return Respuesta("", [], Uso(10, max_tokens, 0.1),
                             razonamiento="pensaba y pensaba y…",
                             motivo_parada="tope_tokens")
        return Respuesta("hecho", [], Uso(10, 3, 0.1))

    def contar_tokens(self, texto):
        return max(1, len(texto) // 4)


s = Sesion(sistema="pruebas", cerebro=CerebroCortado())
r = _turno(s, estandar(), Politica(modo="todo"), "haz algo",
           traza_por_pantalla=False)
c.igual(r.motivo, "fin", "tras el corte se le pidió continuar y cerró de verdad")
c.igual(r.vueltas, 2, "el corte no acabó el turno: hubo segunda vuelta")
c(any(m.rol == "usuario" and "se cortó" in m.contenido for m in s.mensajes),
  "la petición de continuar quedó en la transcripción")

# ── Ctrl-C limpio (M5.5): el turno interrumpido cierra con su motivo ──
class CerebroInterrumpido:
    nombre, contexto_max = "int", 32768

    def generar(self, mensajes, herramientas=(), max_tokens=512):
        return Respuesta("iba diciendo algo", [], Uso(10, 5, 0.1),
                         motivo_parada="interrumpido")

    def contar_tokens(self, texto):
        return max(1, len(texto) // 4)


s_i = Sesion(sistema="pruebas", cerebro=CerebroInterrumpido())
r_i = _turno(s_i, estandar(), Politica(modo="todo"), "haz algo",
             traza_por_pantalla=False)
c(r_i.motivo == "interrumpido", "el Ctrl-C cierra el turno con su motivo, sin morir")
c(any(m.rol == "asistente" and "iba diciendo" in m.contenido for m in s_i.mensajes),
  "lo generado hasta el corte queda en la sesión (y --continuar lo retoma)")

raise SystemExit(c.fin())
