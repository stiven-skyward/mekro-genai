"""El lazo autónomo de H6, en frío: la vuelta entera con eco y los frenos puestos.

Lo que se vigila no es que el lazo funcione cuando todo va bien: es que se NIEGUE a
correr cuando no debe (racha de refutaciones, propuesta inválida, ciclo a medias) y que
la vuelta buena deje el ciclo CERRADO con las dos puertas pasadas."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _util import Cuenta

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
import lazo as mod  # noqa: E402

c = Cuenta("lazo")
tmp = Path(tempfile.mkdtemp(prefix="lazo-prueba-"))
entorno = {**os.environ, "MG_CICLOS": str(tmp / "ciclos"),
           "MG_REGISTROS": str(tmp / "registros")}
(tmp / "ciclos").mkdir(parents=True)


def lazo(*args):
    return subprocess.run([sys.executable, str(RAIZ / "scripts" / "lazo.py"), *args],
                          capture_output=True, text=True, env=entorno, cwd=RAIZ)


# ── validar: la propuesta hostil no llega ni a abrir ciclo ──────────────────
buena = {"pregunta": "¿pasa humo con eco?", "revision": "eco pasa n0 desde M0",
         "metrica": "tareas_pct", "umbral": "==100", "porque": "es el guion de oro",
         "carrera": {"nivel": "n0", "tarea": "humo", "cerebro": "eco",
                     "tope_vueltas": 8, "tope_tokens": 2000, "tope_segundos": 120},
         "leccion": "prueba fría: eco sigue pasando humo, el lazo cierra la vuelta"}
c(mod.validar(buena) == [], "la propuesta bien formada no tiene quejas")
c(any("metrica" in q or "métrica" in q for q in
      mod.validar({**buena, "metrica": "vibes"})), "una métrica inventada se rechaza")
c(any("umbral" in q for q in mod.validar({**buena, "umbral": "mejor"})),
  "un umbral sin operador se rechaza")
c(any("fuera de rango" in q for q in mod.validar(
    {**buena, "carrera": {**buena["carrera"], "tope_tokens": 999999}})),
  "un tope fuera de rango se rechaza")
c(any("no existe" in q for q in mod.validar(
    {**buena, "carrera": {**buena["carrera"], "tarea": "inventada"}})),
  "una tarea que no existe se rechaza")

c(any("deliberan" in q for q in mod.validar({**buena, "revision": "bla " * 300})),
  "un campo que rumia (más de 700 caracteres) se rechaza mecánicamente")

cmd = mod.construir_comando(buena["carrera"], "x")
c(cmd[2].endswith("correr_banco.py") and "--tarea" in cmd and "humo" in cmd,
  "el comando sale de la plantilla fija, no de texto del modelo")

# ── la vuelta entera, en frío ───────────────────────────────────────────────
prop = tmp / "propuesta.json"
prop.write_text(json.dumps(buena, ensure_ascii=False), encoding="utf-8")
r = lazo("--propuesta", str(prop))
c(r.returncode == 0, f"la vuelta fría termina bien (dijo: {r.stdout[-200:]!r})")
c1 = json.loads((tmp / "ciclos" / "C1.json").read_text(encoding="utf-8"))
c(c1["fase"] == "cerrado" and c1["veredicto"]["confirma"],
  "el ciclo quedó CERRADO y confirmado, con las dos puertas pasadas")
c(c1["leccion"].startswith("prueba fría"), "la lección quedó escrita")
c(list((tmp / "registros").glob("*lazo-C1*")), "la carrera dejó su registro aparte")

# ── el guardia de novedad: repetir la carrera+métrica de C1 ya no vale ──────
os.environ["MG_CICLOS"] = str(tmp / "ciclos")
c(any("ya está medida" in q for q in mod.validar(buena)),
  "la misma carrera con la misma métrica, ya veredictada en C1, se rechaza")
c(mod.validar({**buena, "metrica": "tokens_media", "umbral": "<500"}) == [],
  "cambiar la métrica vuelve a hacerla proponible")
del os.environ["MG_CICLOS"]

# ── freno: propuesta inválida → ni abre ciclo ───────────────────────────────
prop.write_text(json.dumps({**buena, "umbral": "ojalá"}), encoding="utf-8")
r = lazo("--propuesta", str(prop))
c(r.returncode == 2 and not (tmp / "ciclos" / "C2.json").exists(),
  "la propuesta inválida no abre ciclo: código 2 y ningún C2")

# ── freno: la racha de refutaciones para el lazo ────────────────────────────
for i in range(2, 6):
    (tmp / "ciclos" / f"C{i}.json").write_text(json.dumps(
        {"id": f"C{i}", "pregunta": "x", "fase": "cerrado",
         "veredicto": {"confirma": False}}), encoding="utf-8")
prop.write_text(json.dumps(buena, ensure_ascii=False), encoding="utf-8")
r = lazo("--propuesta", str(prop))
c(r.returncode == 1 and "estancamiento" in r.stdout,
  "cuatro refutados seguidos: el lazo PARA y pide revisión, no corre")

# ── el supervisor: el freno humano gana antes de lanzar nada ────────────────
parar = tmp / "parar.ahora"
parar.touch()
r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "supervisor.py"),
                    "--parar", str(parar)], capture_output=True, text=True)
c(r.returncode == 0 and "FRENO: parada humana" in r.stdout,
  "con el fichero de parada presente, el supervisor ni lanza: freno y abajo")

raise SystemExit(c.fin())
