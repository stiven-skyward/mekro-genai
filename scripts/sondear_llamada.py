#!/usr/bin/env python3
"""sondear_llamada.py — C8: ¿sabe el campeón emitir una llamada Hermes bien formada?

LA PREGUNTA
-----------
C4 midió que el campeón a 2 bits cambia el token más probable en el 44 % de las
posiciones de texto real. Eso no dice todavía si sabe **llamar a una herramienta**: el
andamiaje Hermes es texto de entropía casi nula y podría sobrevivir intacto aunque el
resto derive. La diferencia decide un hito: si el andamiaje se conserva, el problema del
campeón es de criterio y H1 sigue siendo el camino; si no se conserva, **H5
(decodificación restringida por gramática) deja de ser una comodidad de M2 y pasa a ser
la condición de existencia de M1**.

CÓMO SE MIDE SIN TENER BUCLE DE GENERACIÓN
-------------------------------------------
`banco/n0/humo/tarea.json` trae el **guion de oro**: las cuatro llamadas exactas que el
arnés espera. Se corre la tarea con el cerebro `eco`, que replica ese guion, y se captura
**el prompt exacto que el arnés habría mandado** en cada vuelta —con sus observaciones de
herramienta de verdad, no fabricadas—. Luego se fuerza la decodificación de los dos
modelos sobre la respuesta de oro y se mira, token a token, dónde se desvía el argmax.

No hace falta H2 (bucle con caché KV) ni H8 (especulativa): un pase por modelo.

TRES CIFRAS, Y LA QUE DECIDE ES LA PRIMERA
-------------------------------------------
  · `acuerdo_estructura`: sobre los tokens del ANDAMIAJE —«<tool_call>», «{"name": "»,
    «", "arguments": », «</tool_call>»—, que es lo que hace que la llamada parsee.
  · `acuerdo_oro`: sobre todos los tokens del oro. Ojo: aquí una discrepancia NO es un
    fallo — el oro no es la única respuesta correcta, y elegir `leer` antes que `bash` es
    otra estrategia, no un error. Por eso no es la cifra del veredicto.
  · `prefijo_exacto`: cuántos tokens del oro reproduce el modelo en fila antes de la
    primera desviación. Es lo que de verdad ocurriría generando en avaricioso.

USO
---
  python3 scripts/sondear_llamada.py
"""
from __future__ import annotations

# Las carreras van desatendidas con nohup: si la salida se bufferiza, el monitor que la
# vigila queda CIEGO y una carrera de media hora no emite una sola línea. Lección del
# 2026-08-23, con C16 corriendo 27 min sin señal. Se fuerza el vaciado en cada print.
import builtins as _b
_print_original = _b.print
print = lambda *a, **k: _print_original(*a, **{**k, "flush": True})

import argparse
import json
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F

RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ))

from medir_aceptacion import GRANDE, BORRADOR, flujo_final, _cabeza   # noqa: E402


# ── 1 · capturar los prompts que el arnés mandaría de verdad ────────────────
def capturar(dir_tarea: Path) -> list[tuple[str, str]]:
    """Corre la tarea con `eco` y devuelve [(prompt montado, respuesta de oro)]."""
    import shutil, tempfile
    from genai.cerebro.eco import CerebroEco
    from genai.cerebro.plantilla import montar
    from genai.herramientas import estandar
    from genai.memoria import HERRAMIENTAS as HOLO
    from genai.nucleo import Politica, Sesion, turno
    sys.path.insert(0, str(RAIZ / "scripts"))
    from correr_banco import SISTEMA

    tarea = json.loads((dir_tarea / "tarea.json").read_text(encoding="utf-8"))
    guion = tarea["guion"]
    capturas: list[tuple[str, str]] = []

    class EcoQueGraba(CerebroEco):
        def generar(self, mensajes, herramientas=(), max_tokens=512):
            paso = self.paso
            capturas.append((montar(mensajes, herramientas),
                             guion[paso] if paso < len(guion) else ""))
            return super().generar(mensajes, herramientas, max_tokens)

    trabajo = Path(tempfile.mkdtemp(prefix="c8-"))
    shutil.copytree(dir_tarea / "semilla", trabajo, dirs_exist_ok=True)
    registro = estandar()
    for h in HOLO:
        registro.registrar(h)
    sesion = Sesion(sistema=SISTEMA, cerebro=EcoQueGraba(guion=guion))
    antes = os.getcwd()
    os.chdir(trabajo)
    try:
        turno(sesion, registro, Politica(modo="lista"), tarea["encargo"],
              traza_por_pantalla=False)
    finally:
        os.chdir(antes)
        shutil.rmtree(trabajo, ignore_errors=True)
    # sólo las vueltas que emiten llamada: la última es prosa y no se juzga aquí
    return [(p, o) for p, o in capturas if "<tool_call>" in o]


# ── 2 · qué trozos del oro son ANDAMIAJE y no decisión ──────────────────────
_TROZOS = ['<tool_call>\n{"name": "', '", "arguments": ', "</tool_call>"]


def spans_andamiaje(oro: str) -> list[tuple[int, int]]:
    """Rangos de caracteres del oro que son formato puro: ni el nombre de la
    herramienta ni los argumentos, que sí son decisiones del modelo."""
    spans, desde = [], 0
    for t in _TROZOS:
        i = oro.find(t, desde)
        if i < 0:
            raise SystemExit(f"el oro no trae {t!r}: {oro[:80]!r}")
        spans.append((i, i + len(t)))
        desde = i + len(t)
    return spans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarea", default="banco/n0/humo")
    ap.add_argument("--hilos", type=int, default=0)
    ap.add_argument("--trozo", type=int, default=64)
    ap.add_argument("--salida", default="")
    a = ap.parse_args()
    torch.set_num_threads(a.hilos or os.cpu_count() or 8)
    dtype = torch.bfloat16
    t0 = time.time()

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(GRANDE))
    pares = capturar(RAIZ / a.tarea)
    print(f"{len(pares)} vueltas con llamada capturadas del arnés")

    # tokenizar prompt+oro y marcar qué posiciones se juzgan y cuáles son andamiaje
    filas = []
    for prompt, oro in pares:
        ip = tok(prompt, add_special_tokens=False)["input_ids"]
        eo = tok(oro, add_special_tokens=False, return_offsets_mapping=True)
        io, offs = eo["input_ids"], eo["offset_mapping"]
        spans = spans_andamiaje(oro)
        andamio = [any(s <= o0 and o1 <= e for s, e in spans) for o0, o1 in offs]
        filas.append({"ids": ip + io, "n_prompt": len(ip), "n_oro": len(io),
                      "andamio": andamio, "oro": oro})
    T = max(len(f["ids"]) for f in filas)
    print(f"ventana T={T} · oro por vuelta: {[f['n_oro'] for f in filas]}")

    # relleno a la DERECHA: en un modelo causal (y en las capas deltanet, que van de
    # izquierda a derecha) lo que va después no puede contaminar lo que se juzga
    relleno = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    ids = torch.full((len(filas), T), relleno, dtype=torch.long)
    for w, f in enumerate(filas):
        ids[w, :len(f["ids"])] = torch.tensor(f["ids"])

    print(f"[1/3] pase del GRANDE   {GRANDE}")
    fg, _ = flujo_final(GRANDE, ids, dtype, None)
    print(f"[2/3] pase del BORRADOR {BORRADOR}")
    fb, _ = flujo_final(BORRADOR, ids, dtype, None)
    print("[3/3] cabezas y desviación")
    Wg, Wb = _cabeza(GRANDE, dtype), _cabeza(BORRADOR, dtype)

    res = {"tarea": a.tarea, "vueltas": len(filas), "ventana": T, "por_vuelta": [],
           "modelos": {"grande": str(GRANDE), "borrador": str(BORRADOR)}}
    tot = {m: {"and_ok": 0, "and_n": 0, "oro_ok": 0, "oro_n": 0, "nll": 0.0}
           for m in ("grande", "borrador")}
    for w, f in enumerate(filas):
        s0, n = f["n_prompt"], f["n_oro"]
        # la posición s0-1+i predice el token de oro i
        obj = ids[w, s0:s0 + n]
        fila = {"vuelta": w + 1, "tokens_oro": n,
                "oro": f["oro"][:60].replace("\n", "⏎")}
        for nombre, flu, Wc in (("grande", fg, Wg), ("borrador", fb, Wb)):
            pred, nll = [], 0.0
            for c in range(0, n, a.trozo):
                e = min(c + a.trozo, n)
                lg = F.linear(flu[w, s0 - 1 + c:s0 - 1 + e], Wc).float()
                pred.append(lg.argmax(-1))
                nll += F.cross_entropy(lg, obj[c:e], reduction="sum").item()
                del lg
            pred = torch.cat(pred)
            ok = (pred == obj)
            am = torch.tensor(f["andamio"])
            prefijo = int((~ok).nonzero()[0].item()) if (~ok).any() else n
            fila[nombre] = {
                "acuerdo_oro": round(ok.float().mean().item(), 4),
                "acuerdo_estructura": round(ok[am].float().mean().item(), 4),
                "tokens_estructura": int(am.sum()),
                "prefijo_exacto": prefijo,
                "nll_por_token": round(nll / n, 4),
                # el detalle token a token se guarda: reanalizar no debe costar otro
                # pase de 44 min de CPU (lección de C8)
                "detalle": [
                    {"i": int(i), "oro": tok.decode([int(obj[i])]),
                     "dijo": tok.decode([int(pred[i])]),
                     "andamiaje": bool(f["andamio"][i])}
                    for i in range(n) if not bool(ok[i])],
                "primera_desviacion": (
                    "" if prefijo >= n else
                    f"oro={tok.decode([int(obj[prefijo])])!r} → "
                    f"dijo={tok.decode([int(pred[prefijo])])!r}"
                    f"{' [ANDAMIAJE]' if f['andamio'][prefijo] else ' [decisión]'}"),
            }
            t = tot[nombre]
            t["and_ok"] += int(ok[am].sum()); t["and_n"] += int(am.sum())
            t["oro_ok"] += int(ok.sum()); t["oro_n"] += n; t["nll"] += nll
        res["por_vuelta"].append(fila)

    res["global"] = {m: {"acuerdo_estructura": round(t["and_ok"] / t["and_n"], 4),
                         "acuerdo_oro": round(t["oro_ok"] / t["oro_n"], 4),
                         "nll_por_token": round(t["nll"] / t["oro_n"], 4),
                         "tokens_estructura": t["and_n"], "tokens_oro": t["oro_n"]}
                     for m, t in tot.items()}
    res["segundos"] = round(time.time() - t0, 1)

    print("\n" + json.dumps(res["por_vuelta"], indent=2, ensure_ascii=False))
    print("\nGLOBAL " + json.dumps(res["global"], ensure_ascii=False))
    g = res["global"]
    print(f"CIFRA acuerdo_estructura_campeon {g['borrador']['acuerdo_estructura']}")
    print(f"CIFRA acuerdo_estructura_bf16 {g['grande']['acuerdo_estructura']}")
    print(f"CIFRA acuerdo_oro_campeon {g['borrador']['acuerdo_oro']}")
    print(f"CIFRA acuerdo_oro_bf16 {g['grande']['acuerdo_oro']}")
    destino = Path(a.salida) if a.salida else (
        RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_C8-llamada.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nregistro: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
