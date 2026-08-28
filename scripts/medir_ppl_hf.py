#!/usr/bin/env python3
"""medir_ppl_hf.py — PPL de un checkpoint HF sobre el corpus CONGELADO.

Existe para que las comparaciones valgan: el corpus de este proyecto es el propio
repositorio y cambia mientras se mide, así que toda cifra va con la huella del corpus.
"""
from __future__ import annotations
import builtins as _b
_p = _b.print
print = lambda *a, **k: _p(*a, **{**k, "flush": True})
import argparse, json, os, sys, time
from pathlib import Path
import torch, torch.nn.functional as F
RAIZ = Path(os.environ.get("MG_RAIZ", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(RAIZ / "scripts"))
from medir_aceptacion import _corpus, _ventanas, flujo_final, _cabeza   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--modelo", required=True)
ap.add_argument("--ventana", type=int, default=512)
ap.add_argument("--ventanas", type=int, default=4)
ap.add_argument("--etiqueta", default="")
ap.add_argument("--salida", default="")
a = ap.parse_args()
torch.set_num_threads(os.cpu_count() or 8)
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained(a.modelo)
ids, etq = _ventanas(_corpus(RAIZ), tok, a.ventana, a.ventanas)
huella = json.loads((RAIZ / "registros" / "corpus-congelado.json").read_text())["huella"]
print(f"{a.etiqueta or a.modelo} · {ids.shape} · corpus {huella}")
t0 = time.time()
flujo, seg = flujo_final(Path(a.modelo), ids, torch.bfloat16, None)
W = _cabeza(Path(a.modelo), torch.bfloat16)
acc = {}
for w in range(ids.shape[0]):
    x = flujo[w][:-1]; obj = ids[w, 1:]; s = 0.0
    for i in range(0, x.shape[0], 64):
        j = min(i + 64, x.shape[0])
        lg = F.linear(x[i:j], W).float()
        s += F.cross_entropy(lg, obj[i:j], reduction="sum").item(); del lg
    g = etq[w]; d = acc.setdefault(g, [0.0, 0]); d[0] += s; d[1] += obj.numel()
res = {"modelo": a.modelo, "etiqueta": a.etiqueta, "corpus": huella,
       "ventana": a.ventana, "ventanas_por_dominio": a.ventanas,
       "por_dominio": {g: {"nll": round(v[0]/v[1], 5),
                           "ppl": round(float(torch.tensor(v[0]/v[1]).exp()), 4)}
                       for g, v in acc.items()},
       "segundos": round(time.time() - t0, 1)}
print(json.dumps(res, indent=2, ensure_ascii=False))
for g, d in res["por_dominio"].items(): print(f"CIFRA ppl_{g} {d['ppl']}")
dest = Path(a.salida) if a.salida else RAIZ / "registros" / f"{time.strftime('%Y-%m-%d_%H%M')}_ppl.json"
dest.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"registro: {dest}")
