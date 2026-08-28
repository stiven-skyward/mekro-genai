#!/usr/bin/env python3
"""adopcion.py — la puerta de M3, abierta por el autor (2026-08-27).

M3 dice: «el ciclo de investigación sube la puntuación del banco sin humano en el
bucle, y el registro lo prueba». Medir no basta para eso: hace falta que un hallazgo
CAMBIE cómo se corre la carrera siguiente. Este módulo es ese cambio, con los
guardarraíles por delante de la ambición:

- **Solo mandos de carrera** (tope_tokens, tope_vueltas, tope_segundos). La adopción
  JAMÁS toca código: el espacio de auto-modificación es exactamente el espacio de
  banderas que el proponente ya tenía.
- **Solo victorias limpias**: ciclo CONFIRMADO, tareas_pct 100, 0 intervenciones, y la
  cifra al menos un 10 % mejor que la línea base (el suelo de ruido medido es ~9 %).
- **Reversión automática**: si una carrera posterior corre con mandos adoptados y la
  tarea FALLA, la adopción se revierte y queda anotado. El vigilante de adopciones no
  discute: el 100 % es sagrado.
- **Historial imborrable** en `registros/adopciones.json`: cada adopción y cada
  reversión, con su ciclo, sus cifras y su porqué. Como todo registro, no se borra.

La línea base de una tarea es su PRIMERA medición registrada (inmutable): mejorar es
mejorar respecto a donde se empezó, no respecto a un listón que se mueve.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SUELO_MEJORA = 0.10
# «contexto» entró tras la racha C74-C77: la frontera de compresión por topes quedó
# medida (lista rompe a 1.050-1.600 y el 10% exige <1.906) — el mando causal que SÍ
# comprime sin romper es la ventana chica con renacimiento (C72: 1.365 tokens, −35%).
# Es bandera de carrera (--contexto), dentro de la puerta que el autor abrió.
MANDOS = ("tope_vueltas", "tope_tokens", "tope_segundos", "contexto", "sin_pensar", "pensar_vueltas")
# SOLO tokens: la primera pasada del mecanismo (2026-08-27) adoptó «mejoras» de
# segundos que eran la máquina del día (varía ×2, C23) y mandos idénticos al defecto
# (mérito no atribuible). Una adopción exige métrica estable Y mando distinto.
CIFRA_POR_METRICA = {"tokens_media": "tokens_salida"}


def _ruta() -> Path:
    return Path(os.environ.get("MG_ADOPCIONES",
                               RAIZ / "registros" / "adopciones.json"))


def _estado() -> dict:
    if _ruta().exists():
        return json.loads(_ruta().read_text(encoding="utf-8"))
    return {"vigentes": {}, "historial": []}


def _guardar(estado: dict) -> None:
    _ruta().parent.mkdir(parents=True, exist_ok=True)
    _ruta().write_text(json.dumps(estado, ensure_ascii=False, indent=1),
                       encoding="utf-8")


def vigentes() -> dict:
    """tarea («nivel/tarea») → mandos adoptados hoy."""
    return {k: v["mandos"] for k, v in _estado()["vigentes"].items()}


def lineas_base() -> dict:
    """tarea → {tokens_salida, segundos} de su PRIMERA medición registrada."""
    base: dict[str, dict] = {}
    dir_reg = Path(os.environ.get("MG_REGISTROS", RAIZ / "registros"))
    for f in sorted(dir_reg.glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(r, dict) and r.get("cerebro") == "gguf"):
            continue
        for t in r.get("tareas") or []:
            clave = f"{r.get('nivel')}/{t.get('id')}"
            if t.get("id") and clave not in base and t.get("paso"):
                base[clave] = {"tokens_salida": t.get("tokens_salida"),
                               "segundos": t.get("segundos"),
                               "topes": r.get("topes") or {}, "registro": f.name}
    return base


def _mandos_de_comando(cmd: str) -> dict:
    m: dict[str, int] = {}
    if "--sin-pensar" in cmd:
        m["sin_pensar"] = 1
    for mando in MANDOS:
        b = re.search(rf"--{mando.replace('_', '-')}\s+(\d+)", cmd)
        if b:
            m[mando] = int(b.group(1))
    return m


def adoptar_desde_ciclos() -> list[dict]:
    """Recorre los ciclos CERRADOS y adopta las victorias limpias que mejoren la
    línea base más que el suelo. Devuelve las adopciones nuevas (ya guardadas)."""
    estado = _estado()
    base = lineas_base()
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    nuevas: list[dict] = []
    for f in sorted(dir_ciclos.glob("C*.json"),
                    key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0):
        c = json.loads(f.read_text(encoding="utf-8"))
        v, med = c.get("veredicto") or {}, c.get("medicion") or {}
        cif, cmd = med.get("cifras") or {}, med.get("comando") or ""
        met = (c.get("prediccion") or {}).get("metrica")
        if not (v.get("confirma") and cif.get("tareas_pct") == 100.0
                and cif.get("intervenciones") == 0.0 and met in CIFRA_POR_METRICA):
            continue
        m_niv = re.search(r"--nivel (\S+)", cmd)
        m_tar = re.search(r"--tarea (\S+)", cmd)
        if not (m_niv and m_tar):
            continue
        clave = f"{m_niv.group(1)}/{m_tar.group(1)}"
        cifra_base = (base.get(clave) or {}).get(CIFRA_POR_METRICA[met])
        valor = cif.get(met)
        if not cifra_base or valor is None:
            continue
        if valor > cifra_base * (1 - SUELO_MEJORA):
            continue                       # no mejora más que el ruido: no se adopta
        mandos = _mandos_de_comando(cmd)
        topes_base = (base.get(clave) or {}).get("topes") or {}
        if all(mandos.get(m) == topes_base.get(m) for m in MANDOS if m in mandos):
            continue          # mismos mandos que la base: la mejora no es atribuible
        if valor > mandos.get("tope_tokens", 10**9):
            # C73: C40 «ganó» REBASANDO su propio tope (uso 1.732 > tope 1.600) porque
            # el tope se chequea al empezar la vuelta — esa victoria es suerte, no
            # configuración, y adoptarla fue fatal. Se adopta solo lo que terminó
            # DENTRO de su presupuesto.
            continue
        muerde_tope = mandos.get("tope_tokens", 10**9) <= cifra_base
        muerde_contexto = 0 < mandos.get("contexto", 0) < 16384
        muerde_pensar = bool(mandos.get("sin_pensar")) or 0 < mandos.get(
            "pensar_vueltas", 0) < 99
        if not (muerde_tope or muerde_contexto or muerde_pensar):
            # ningún mando MUERDE: ni el tope corta el uso base (C37/C38) ni la
            # ventana encogida fuerza renacimiento (C72) — la mejora sería deriva
            continue
        ya = estado["vigentes"].get(clave)
        if ya and ya.get("valor", 1e12) <= valor:
            continue                       # lo vigente es igual o mejor
        adopcion = {"tarea": clave, "mandos": mandos, "metrica": met,
                    "valor": valor, "linea_base": cifra_base,
                    "mejora_pct": round(100 * (1 - valor / cifra_base), 1),
                    "ciclo": c["id"],
                    "cuando": datetime.now(timezone.utc).isoformat()[:19]}
        estado["vigentes"][clave] = adopcion
        estado["historial"].append({"accion": "adoptar", **adopcion})
        nuevas.append(adopcion)
    if nuevas:
        _guardar(estado)
    return nuevas


def revertir_si_fallo(clave: str, tareas_pct: float) -> bool:
    """El vigilante de adopciones: una carrera con mandos adoptados que NO llega al
    100 % revierte la adopción de esa tarea, con constancia. Devuelve si revirtió."""
    estado = _estado()
    if tareas_pct >= 100.0 or clave not in estado["vigentes"]:
        return False
    caida = estado["vigentes"].pop(clave)
    estado["historial"].append({"accion": "revertir", "tarea": clave,
                                "adopcion_caida": caida,
                                "tareas_pct_observado": tareas_pct,
                                "cuando": datetime.now(timezone.utc).isoformat()[:19]})
    _guardar(estado)
    return True


if __name__ == "__main__":
    nuevas = adoptar_desde_ciclos()
    for a in nuevas:
        print(f"ADOPTADO {a['tarea']}: {a['mandos']} — {a['metrica']} {a['valor']} "
              f"frente a base {a['linea_base']} ({a['mejora_pct']}% mejor, {a['ciclo']})")
    if not nuevas:
        print("nada nuevo que adoptar (vigentes: "
              f"{list(_estado()['vigentes']) or 'ninguna'})")
