#!/usr/bin/env python3
"""supervisor.py — encadena vueltas del lazo (H6) sin humano: termina una, dispara otra.

El pedido del autor (2026-08-25): que no haya que escribir «procede» entre vueltas. Este
supervisor es deliberadamente TONTO: no propone, no mide, no opina. Solo lanza
`lazo.py`, espera, mira cómo acabó y decide si lanzar otra. Toda la inteligencia vive en
el lazo y en el ciclo; toda la prudencia vive en los frenos:

- **Parada humana**: `touch logs/supervisor.parar` — se comprueba antes de cada vuelta.
- **El vigilante manda**: si `ciclo.py racha` alcanza el umbral, no se lanza más.
- **El proponente no levanta cabeza**: dos vueltas seguidas sin propuesta válida
  (código 2) → parar y pedir revisión. Cada intento fallido cuesta ~30-60 min de CPU.
- **Disco**: por debajo de 10 GB libres no se corre nada (los registros no se borran).
- **Un lazo a la vez**: si hay uno vivo (arrancado a mano o por otra instancia), se
  espera, no se duplica.

    nohup python3 -u scripts/supervisor.py >> logs/supervisor.log 2>&1 &
    echo $! > logs/supervisor.pid
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

UMBRAL_RACHA = 4
FALLOS_PROPUESTA_MAX = 2
DISCO_MIN_GB = 10
ESPERA_ENTRE_VUELTAS = 60
ESPERA_SI_OCUPADO = 300


def anota(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def lazo_vivo() -> bool:
    r = subprocess.run(["pgrep", "-f", r"lazo\.py"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def freno_duro(parar: Path) -> str:
    if parar.exists():
        return f"parada humana ({parar})"
    if shutil.disk_usage(RAIZ).free < DISCO_MIN_GB * 2**30:
        return f"menos de {DISCO_MIN_GB} GB libres en disco"
    r = subprocess.run([sys.executable, str(RAIZ / "ciclo.py"), "racha",
                       str(UMBRAL_RACHA)], capture_output=True, text=True)
    if r.returncode != 0:
        return f"el vigilante: {r.stdout.strip()}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parar", default=str(RAIZ / "logs" / "supervisor.parar"))
    ap.add_argument("--vueltas-max", type=int, default=0,
                    help="0 = sin tope; los frenos son quienes paran")
    a = ap.parse_args()
    parar = Path(a.parar)

    anota("supervisor arriba: los frenos mandan, la ambición espera")
    vuelta, fallos_propuesta = 0, 0
    while True:
        razon = freno_duro(parar)
        if razon:
            anota(f"FRENO: {razon}. Supervisor abajo.")
            return 0
        if lazo_vivo():
            anota("hay un lazo en curso: espero sin duplicar")
            time.sleep(ESPERA_SI_OCUPADO)
            continue
        if a.vueltas_max and vuelta >= a.vueltas_max:
            anota(f"tope de {a.vueltas_max} vueltas alcanzado. Supervisor abajo.")
            return 0

        vuelta += 1
        anota(f"vuelta {vuelta}: lanzo lazo.py")
        r = subprocess.run([sys.executable, "-u", str(RAIZ / "scripts" / "lazo.py")],
                           capture_output=True, text=True, cwd=RAIZ)
        cola = (r.stdout or "").strip().splitlines()[-3:]
        anota(f"vuelta {vuelta} acabó con código {r.returncode} · " + " / ".join(cola))

        if r.returncode == 0:
            fallos_propuesta = 0
        elif r.returncode == 1:
            anota("el lazo paró por sus propios frenos. Supervisor abajo.")
            return 0
        else:
            fallos_propuesta += 1
            if fallos_propuesta >= FALLOS_PROPUESTA_MAX:
                anota(f"{fallos_propuesta} vueltas seguidas sin propuesta válida: "
                      "esto no se arregla insistiendo. Supervisor abajo, pide revisión "
                      "(intentos crudos en logs/lazo-intento-*.txt).")
                return 0
        time.sleep(ESPERA_ENTRE_VUELTAS)


if __name__ == "__main__":
    raise SystemExit(main())
