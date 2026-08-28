"""Economía de tokens (docs/ahorro.md): poda en el origen y caché de prefijo.

Lo que se vigila aquí no es «que ahorre» —eso lo mide un ciclo con el banco— sino las
tres propiedades sin las cuales el ahorro sería una avería con buena prensa:

1. que la poda **aprieta cuando quedan muchas vueltas y afloja cuando quedan pocas**,
   que es la ley que distingue esto de un tope fijo;
2. que **lo podado se puede recuperar**, porque podar no es perder;
3. que la caché de prefijo **se pide donde hay que pedirla y no donde rompería**.
"""
import os
import tempfile
from pathlib import Path

from _util import Cuenta

from genai import ahorro
from genai.nucleo.sesion import Sesion

c = Cuenta("ahorro")
tmp = Path(tempfile.mkdtemp(prefix="ahorro-"))
os.environ["MG_PODADO"] = str(tmp / "podado")

# ── ley 1: el tope depende de lo que le queda de vida al dato ───────────────
c(ahorro.factor_vueltas(2) == 1.0,
  "con la tarea acabándose no se aprieta: el dato ya casi no se reenvía")
c(ahorro.factor_vueltas(20) < ahorro.factor_vueltas(6) < ahorro.factor_vueltas(3),
  "cuantas más vueltas quedan, más se aprieta: el coste es tamaño × vueltas")
c(ahorro.factor_vueltas(500) >= ahorro.MIN_FACTOR,
  "pero hay suelo: apretar hasta lo inútil no es ahorrar, es cegar al modelo")

grande = "\n".join(f"linea de relleno numero {i}" for i in range(1200))
pronto, _ = ahorro.podar("bash", grande, vueltas_restantes=20)
tarde, _ = ahorro.podar("bash", grande, vueltas_restantes=2)
c(len(pronto) < len(tarde),
  "la MISMA salida entra más corta en la vuelta 2 que en la penúltima")

# ── ley 2: podar no es perder ──────────────────────────────────────────────
texto, cifras = ahorro.podar("bash", grande, vueltas_restantes=20)
c(cifras["despues"] < cifras["antes"], "la poda declara sus dos cifras, antes y después")
refs = list((tmp / "podado").glob("*.txt"))
c(refs and refs[0].read_text(encoding="utf-8") == grande,
  "lo podado se guardó ENTERO: es recuperable, no se ha perdido")
c(refs[0].stem in texto, "y el aviso dice con qué referencia recuperarlo")

# ── el brazo de control: sin él, ningún ahorro sería demostrable ────────────
crudo, cifras = ahorro.podar("bash", grande, vueltas_restantes=20, activo=False)
c(crudo == grande and cifras["antes"] == cifras["despues"],
  "con la poda apagada no se toca ni un carácter: hay contra qué medir")

# ── los filtros quitan ruido, no criterio ──────────────────────────────────
verde = "\n".join(f"test_{i} ... ok" for i in range(60)) + "\n60 passed in 1.2s"
t, _ = ahorro.podar("bash", verde, vueltas_restantes=10)
c("60 passed" in t and len(t) < len(verde),
  "una suite en verde se resume, pero el veredicto sobrevive")

rojo = verde.replace("test_7 ... ok", "test_7 ... FAILED\n  assert 3 == 4")
t, _ = ahorro.podar("bash", rojo, vueltas_restantes=10)
c("FAILED" in t and "assert 3 == 4" in t,
  "un fallo NUNCA se poda: es exactamente el dato por el que se llamó a la herramienta")

muchos = "\n".join(f"genai/nucleo/bucle.py:{i}:  hallado" for i in range(40))
t, _ = ahorro.podar("grep", muchos, vueltas_restantes=10)
c("40 aciertos" in t and len(t) < len(muchos),
  "40 aciertos en un fichero no pagan 40 veces la ruta")

uno_por_fichero = "\n".join(f"mod{i}.py:{i}:  hallado" for i in range(10))
t, _ = ahorro.podar("grep", uno_por_fichero, vueltas_restantes=10)
c(t == uno_por_fichero,
  "pero si cada acierto está en un fichero distinto, agrupar no ahorra: no se toca")

c(ahorro.podar("bash", "salida corta", vueltas_restantes=20)[0] == "salida corta",
  "lo pequeño se deja en paz: podar 30 caracteres cuesta más de lo que ahorra")

# ── REGRESIÓN: el filtro tiene que hablar los dos idiomas ──────────────────
# Lo encontró banco/n3/ruidosa. El filtro solo-inglés no reconocía «FALLO», caía al
# recorte por la mitad y se llevaba justo la línea por la que se llamó a la
# herramienta. Un ahorro que esconde la aguja no es un ahorro: es una avería que
# además miente, y encima silenciosa.
import subprocess  # noqa: E402
from pathlib import Path as _P  # noqa: E402

sem = _P(__file__).resolve().parents[1] / "banco" / "n3" / "ruidosa" / "semilla"
if sem.is_dir():
    pr = subprocess.run(["python3", "prueba.py"], cwd=sem, capture_output=True, text=True)
    crudo = pr.stdout + pr.stderr
    t, cif = ahorro.podar("bash", crudo, vueltas_restantes=12)
    c("campo_37" in t,
      "la aguja SOBREVIVE a la poda en una salida de 182 líneas donde el veredicto "
      "final no dice cuál falla")
    c("FALLAN 1 de 180" in t, "y el veredicto también")
    c(cif["despues"] < cif["antes"] * 0.25,
      f"recortando de verdad: {cif['antes']} → {cif['despues']} caracteres")

esp = "\n".join(f"ok validador_{i}" for i in range(50)) + "\nFALLO validador_9 mal\n1 de 50 casos"
c("validador_9" in ahorro.podar("bash", esp, vueltas_restantes=12)[0],
  "«FALLO» en español se reconoce igual que «FAILED» en inglés")
c("aserto" in ahorro.podar("bash", "\n".join(["✗ x"] * 3 + ["1/3 asertos"]) * 40,
                           vueltas_restantes=12)[0],
  "y «✗», que es como escribe sus veredictos este proyecto")

# ── la sesión lleva la cuenta ──────────────────────────────────────────────
c(Sesion(sistema="x").ahorro == {"antes": 0, "despues": 0},
  "toda sesión nace con el contador de ahorro a cero, para que salga en el registro")

# ── caché de prefijo: se pide donde ahorra y no donde rompería ─────────────
from genai.cerebro.nube import CerebroNube  # noqa: E402

n = CerebroNube.__new__(CerebroNube)
n.cache = {"leidos": 0, "totales": 0}
c(n.ahorro_cache == 0.0, "sin llamadas todavía, el ahorro de caché es 0 y no un fallo")
n._anotar_cache(900, 1000)
c(n.ahorro_cache == 0.9,
  "el ahorro de caché se MIDE con lo que responde el proveedor, no se supone")

fuente = Path("genai/cerebro/nube.py").read_text(encoding="utf-8")
c("cache_control" in fuente and 'msgs[-3]' in fuente,
  "Anthropic exige marcar el bloque, y se marca el PENÚLTIMO turno: marcar el último "
  "no cachearía nada porque es justo lo que cambia")
c("cached_tokens" in fuente and "cachedContentTokenCount" in fuente,
  "en OpenAI y Gemini la caché es automática, pero se contabiliza igual: "
  "un ahorro que no se mide no existe")

raise SystemExit(c.fin())
