#!/usr/bin/env python3
"""guardian.py — el supervisor de SALUD del trabajo autónomo (M7).

`supervisor.py` encadena vueltas de investigación; este guardián es otra cosa: vigila
que el proyecto no se descarrile mientras alguien —humano o lazo— trabaja sobre él.
Comprueba invariantes y grita cuando uno se rompe, en vez de esperar a que alguien
mire.

Los invariantes, y por qué cada uno:

    suites          las pruebas cuentan asertos en verde; si bajan, algo se rompió
    anclas          `holograma.py verificar`: un ancla rota es un puntero muerto
    ciclos          ningún ciclo a medias (un `medir` sin `veredicto` es una deuda)
    secretos        NINGUNA clave en los ficheros versionados — el repo es PÚBLICO
    limpio          nada sin commitear más de N vueltas: el trabajo sin registrar
                    se pierde y las mediciones sin registro no existen
    disco           por debajo de 5 GB no se corre nada más

Escribe una línea por ronda en `logs/guardian.log` con el veredicto de cada invariante
y un `ALERTA` cuando alguno falla, que es lo que un monitor puede seguir.

    nohup python3 -u scripts/guardian.py >> logs/guardian.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# lo que parece una clave de verdad: prefijos de los proveedores que soportamos
HUELLAS_SECRETO = [
    r"AQ\.[A-Za-z0-9_-]{30,}",          # claves de Google AI Studio
    r"sk-[A-Za-z0-9_-]{20,}",           # OpenAI, DeepSeek, Moonshot
    r"sk-ant-[A-Za-z0-9_-]{20,}",       # Anthropic
    r"xai-[A-Za-z0-9]{20,}",            # xAI
    r"ghp_[A-Za-z0-9]{30,}",            # GitHub
    r"-----BEGIN [A-Z ]*PRIVATE KEY",   # cualquier clave privada
]


def _correr(cmd: list[str], segundos: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True,
                          timeout=segundos)


def suites() -> tuple[bool, str]:
    total, rotas = 0, []
    for t in sorted((RAIZ / "tests").glob("test_*.py")):
        r = _correr([sys.executable, str(t)])
        cola = (r.stdout or "").strip().splitlines()[-1:] or [""]
        m = re.search(r"(\d+)/(\d+) asertos", cola[0])
        if m and m.group(1) == m.group(2):
            total += int(m.group(1))
        elif "asertos en verde" in cola[0]:
            total += int(re.search(r"(\d+)", cola[0]).group(1))
        else:
            rotas.append(t.name)
    return (not rotas, f"{total} asertos" + (f" · ROTAS: {rotas}" if rotas else ""))


def anclas() -> tuple[bool, str]:
    r = _correr([sys.executable, str(RAIZ / "holograma.py"), "verificar"], 120)
    cola = (r.stdout or "").strip().splitlines()[-1:] or [""]
    return ("rota" not in cola[0].lower() and bool(cola[0]), cola[0][:60])


def ciclos() -> tuple[bool, str]:
    r = _correr([sys.executable, str(RAIZ / "ciclo.py"), "estado"], 120)
    salida = (r.stdout or "").strip()
    a_medias = "ningún ciclo en curso" not in salida
    # un ciclo recién abierto es normal; el problema es uno MEDIDO sin veredicto
    medido = "fase «medido»" in salida
    return (not medido, salida.splitlines()[0][:80] if salida else "?")


def secretos() -> tuple[bool, str]:
    """La comprobación que más importa: el repositorio es PÚBLICO."""
    r = _correr(["git", "ls-files"], 120)
    sospechosos = []
    for nombre in (r.stdout or "").split():
        f = RAIZ / nombre
        if not f.is_file() or f.stat().st_size > 2_000_000:
            continue
        try:
            texto = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for patron in HUELLAS_SECRETO:
            m = re.search(patron, texto)
            if not m:
                continue
            # Una cabecera PEM sin cuerpo base64 detrás es documentación, no una
            # clave (lo destapó la primera ronda del guardián: una tabla de «qué
            # patrones son secretos» disparó la alarma). Se exige el material.
            if "PRIVATE KEY" in m.group(0):
                cuerpo = texto[m.end():m.end() + 400]
                if not re.search(r"[A-Za-z0-9+/]{60,}", cuerpo):
                    continue
            sospechosos.append(f"{nombre} ({m.group(0)[:24]}…)")
            break
    return (not sospechosos, "limpio" if not sospechosos
            else f"‼ POSIBLE CLAVE EN: {sospechosos}")


def sin_commitear() -> tuple[bool, int, str]:
    r = _correr(["git", "status", "--porcelain"], 120)
    n = len([l for l in (r.stdout or "").splitlines() if l.strip()])
    return (True, n, f"{n} ficheros")


def disco() -> tuple[bool, str]:
    libre = shutil.disk_usage(RAIZ).free / 2**30
    return (libre > 5, f"{libre:.0f} GB libres")


def ronda(paciencia: dict) -> bool:
    """Una comprobación completa. Devuelve si todo está sano."""
    sello = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res = {"suites": suites(), "anclas": anclas(), "ciclos": ciclos(),
           "secretos": secretos(), "disco": disco()}
    _, pendientes, txt_git = sin_commitear()

    # el trabajo sin registrar se pierde: se avisa a partir de la tercera ronda seguida
    paciencia["sucio"] = paciencia.get("sucio", 0) + 1 if pendientes else 0
    sano = all(ok for ok, _ in res.values())

    linea = " · ".join(f"{k}:{'ok' if ok else 'MAL'}({d})" for k, (ok, d) in res.items())
    print(f"[{sello}] {linea} · git:{txt_git}", flush=True)

    for k, (ok, d) in res.items():
        if not ok:
            print(f"[{sello}] ALERTA {k}: {d}", flush=True)
    if paciencia["sucio"] >= 3:
        print(f"[{sello}] ALERTA git: {pendientes} ficheros sin commitear en "
              f"{paciencia['sucio']} rondas — el trabajo sin registrar se pierde",
              flush=True)
    return sano


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cada", type=int, default=900, help="segundos entre rondas")
    ap.add_argument("--una", action="store_true", help="una ronda y salir")
    ap.add_argument("--parar", default=str(RAIZ / "logs" / "guardian.parar"))
    a = ap.parse_args()

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] guardián arriba "
          f"(ronda cada {a.cada} s · para con: touch {a.parar})", flush=True)
    while True:
        sano = ronda({} if a.una else globals().setdefault("_paciencia", {}))
        if a.una:
            return 0 if sano else 1
        if Path(a.parar).exists():
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] parada humana. Guardián abajo.",
                  flush=True)
            return 0
        time.sleep(a.cada)


if __name__ == "__main__":
    raise SystemExit(main())
