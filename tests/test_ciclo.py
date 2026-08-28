"""El ciclo: se prueba sobre todo que las DOS PUERTAS aguantan.

Sin ellas el fichero es papeleo. Con ellas, el proyecto no puede racionalizar un número
después de verlo."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _util import Cuenta

c = Cuenta("ciclo")
RAIZ = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp())
# MG_RAIZ apunta al temporal a propósito: el veredicto ESCRIBE en CONTINUIDAD.md, y una
# prueba que ensucia el registro real del proyecto sería peor que no tenerla.
entorno = {**os.environ, "MG_CICLOS": str(tmp / "ciclos"), "MG_RAIZ": str(tmp)}
(tmp / "CONTINUIDAD.md").write_text("# falso\n", encoding="utf-8")


def ciclo(*args):
    return subprocess.run([sys.executable, "ciclo.py", *args], cwd=RAIZ,
                          capture_output=True, text=True, env=entorno)


import ciclo as mod  # noqa: E402

# ── el contrato CIFRA ───────────────────────────────────────────────────────
c.igual(mod._cifras("bla\nCIFRA tokens 2400\nbla"), {"tokens": 2400.0},
        "se extrae la cifra declarada")
c.igual(mod._cifras("CIFRA ppl 7.46e0"), {"ppl": 7.46}, "notación científica vale")
c.igual(mod._cifras("cifra tokens 24"), {}, "en minúsculas NO cuela: el contrato es estricto")
c.igual(mod._cifras("CIFRA tokens muchos"), {},
        "un valor no numérico no se adivina: adivinar aquí es inventar un experimento")

c(mod._cumple(2400, "<3000"), "comparación menor-que")
c(not mod._cumple(3200, "<3000"), "y su negativa")
c(mod._cumple(7.5, "~7.46±2%"), "tolerancia porcentual")
c(not mod._cumple(8.0, "~7.46±2%"), "fuera de tolerancia")

# ── PUERTA 1: no se mide sin haber predicho ─────────────────────────────────
c(ciclo("abrir", "T1", "¿baja el coste?").returncode == 0, "se abre un ciclo")
r = ciclo("medir", "T1", "--", "echo", "CIFRA tokens 100")
c(r.returncode != 0, "medir SIN predicción falla")
c("no tiene predicción escrita" in r.stdout + r.stderr,
  "y explica por qué: sin predicción el número no refuta nada")

# ── una predicción exige su porqué, y no se reescribe ────────────────────────
c(ciclo("predecir", "T1", "tokens", "<3000").returncode != 0,
  "una predicción sin --porque se rechaza")
c(ciclo("predecir", "T1", "tokens", "<3000", "--porque", "menos vueltas").returncode == 0,
  "con --porque se acepta")
r = ciclo("predecir", "T1", "tokens", "<9999", "--porque", "ahora que vi el número")
c(r.returncode != 0 and "Abre un ciclo nuevo" in r.stdout + r.stderr,
  "reescribir la predicción es exactamente lo que el fichero impide")

# ── medir y contrastar ──────────────────────────────────────────────────────
r = ciclo("medir", "T1", "--", "echo", "CIFRA tokens 2400")
c(r.returncode == 0 and "CONFIRMA" in r.stdout, "una medición dentro de lo predicho CONFIRMA")

# ── PUERTA 2: no se cierra sin lección ──────────────────────────────────────
c(ciclo("veredicto", "T1").returncode != 0, "veredicto sin --leccion falla")
r = ciclo("veredicto", "T1", "--leccion", "menos vueltas sí baja el coste")
c(r.returncode == 0 and "CONFIRMA" in r.stdout, "con lección, se cierra")

datos = (tmp / "ciclos" / "T1.json").read_text(encoding="utf-8")
c('"fase": "cerrado"' in datos, "el ciclo queda cerrado en disco")
c("menos vueltas sí baja el coste" in datos, "la lección queda registrada")
c("menos vueltas sí baja el coste" in (tmp / "CONTINUIDAD.md").read_text(encoding="utf-8"),
  "y también va a CONTINUIDAD.md, donde no se borra nunca")

# ── refutar también es cerrar ───────────────────────────────────────────────
ciclo("abrir", "T2", "¿y esta?")
ciclo("predecir", "T2", "ppl", "<5", "--porque", "corazonada")
ciclo("medir", "T2", "--", "echo", "CIFRA ppl 7.46")
r = ciclo("veredicto", "T2", "--leccion", "la corazonada era falsa y ya está medido")
c("REFUTA" in r.stdout, "una predicción incumplida REFUTA, y eso es un resultado")

# ── la asimetría de la sonda: refutar cierra, confirmar no ──────────────────
ciclo("abrir", "T3", "¿y con sonda?")
ciclo("predecir", "T3", "frac", ">=0.95", "--porque", "debería estar la estructura")
ciclo("sonda", "T3", "--", "echo", "CIFRA frac 0.0003")
r = ciclo("veredicto", "T3", "--leccion", "la sonda barata zanjó sin gastar la cara")
c(r.returncode == 0 and "REFUTA" in r.stdout,
  "una SONDA que refuta cierra el ciclo: para eso existe la comprobación barata")

ciclo("abrir", "T4", "¿y si la sonda confirma?")
ciclo("predecir", "T4", "frac", ">=0.95", "--porque", "corazonada")
ciclo("sonda", "T4", "--", "echo", "CIFRA frac 0.99")
r = ciclo("veredicto", "T4", "--leccion", "salió bien en la muestra")
c(r.returncode != 0 and "no cierra nada" in r.stdout + r.stderr,
  "una sonda que CONFIRMA no cierra: creerse la primera señal favorable es el error")

c("T2" in ciclo("listar").stdout, "listar los enseña")
c("T4" in ciclo("estado").stdout, "estado señala el ciclo que sigue a medias")

# ── el vigilante (H6): la racha de ciclos cerrados sin confirmar ──
def _c(nid, confirma):
    return {"id": nid, "fase": "cerrado", "veredicto": {"confirma": confirma}}

n, ids = mod.racha_sin_confirmar([_c("C1", True), _c("C2", False), _c("C3", False)])
c(n == 2 and ids == ["C2", "C3"], "dos refutados al final: racha 2, en orden")
n, _ = mod.racha_sin_confirmar([_c("C1", False), _c("C2", True)])
c(n == 0, "el último confirmó: racha 0, lo anterior no cuenta")
n, _ = mod.racha_sin_confirmar(
    [_c("C1", True), {"id": "C9", "fase": "predicho", "veredicto": None},
     _c("C2", False)])
c(n == 1, "un ciclo a medias no rompe ni alarga la racha: solo cuentan cerrados")

raise SystemExit(c.fin())
