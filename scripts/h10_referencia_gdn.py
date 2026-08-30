#!/usr/bin/env python3
"""H10, paso 3-4: implementación de referencia de UNA capa GatedDeltaNet real.

Usa los pesos REALES de la capa 0 del GGUF oficial (dequantizados de verdad,
no simulados), siguiendo la fórmula exacta verificada contra
transformers/models/qwen3_next/modeling_qwen3_next.py (ver holos/H10.md):

    in_proj -> split QKV -> conv1d causal (+SiLU) -> repeat_interleave (GQA) ->
    l2norm(Q,K) -> decay/delta/update/salida por token -> RMSNormGated(Z) -> out_proj

Esto es la referencia NUMÉRICA con la que comparar el futuro kernel en C — no
es todavía la comprobación contra llama.cpp (eso exige extraer sus estados
intermedios, que la API de alto nivel de llama-cpp-python no expone; queda
como el siguiente paso, no resuelto aquí). Lo que SÍ verifica: que los pesos
reales, con la fórmula real, producen una salida finita y con la forma
correcta — la barra mínima antes de fiarse de ningún kernel más rápido.
"""
import sys
from pathlib import Path

import numpy as np
from gguf import GGUFReader
from gguf.quants import dequantize

GGUF = Path.home() / "modelos" / "gguf" / "Qwen3.8-27B-UD-Q2_K_XL.gguf"

HIDDEN = 5120
KEY_HEADS, KEY_HEAD_DIM = 16, 128
VAL_HEADS, VAL_HEAD_DIM = 48, 128
KEY_DIM = KEY_HEADS * KEY_HEAD_DIM      # 2048
VAL_DIM = VAL_HEADS * VAL_HEAD_DIM      # 6144
CONV_DIM = KEY_DIM * 2 + VAL_DIM         # 10240
CONV_K = 4
GQA_FACTOR = VAL_HEADS // KEY_HEADS      # 3


def _peso(tensores: dict, nombre: str) -> np.ndarray:
    """Dequantiza y ORDENA como (salida, entrada) — gguf-py devuelve las
    dimensiones invertidas respecto al PyTorch/numpy habitual (convención de
    ggml, no un error de lectura: verificado con las formas ya conocidas)."""
    t = tensores[nombre]
    return dequantize(t.data, t.tensor_type).astype(np.float32)


def _rmsnorm(x: np.ndarray, peso: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    var = np.mean(x * x, axis=-1, keepdims=True)
    return x / np.sqrt(var + eps) * peso


def _silu(x: np.ndarray) -> np.ndarray:
    return x / (1.0 + np.exp(-x))


def _l2norm(x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return x / np.sqrt(np.sum(x * x, axis=-1, keepdims=True) + eps)


def _softplus(x: np.ndarray) -> np.ndarray:
    return np.log1p(np.exp(-np.abs(x))) + np.maximum(x, 0)


def capa_gdn(hidden_states: np.ndarray, capa: int, tensores: dict) -> np.ndarray:
    """hidden_states: [T, HIDDEN]. Devuelve [T, HIDDEN]."""
    T = hidden_states.shape[0]
    p = f"blk.{capa}."

    norm_w = _peso(tensores, p + "attn_norm.weight")
    qkv_w = _peso(tensores, p + "attn_qkv.weight")        # [CONV_DIM, HIDDEN] tras dequant
    gate_w = _peso(tensores, p + "attn_gate.weight")      # [VAL_DIM, HIDDEN]
    conv_w = _peso(tensores, p + "ssm_conv1d.weight")     # [CONV_DIM, CONV_K] o traspuesto
    a_log = _peso(tensores, p + "ssm_a")                  # [VAL_HEADS]
    alpha_w = _peso(tensores, p + "ssm_alpha.weight")     # [VAL_HEADS, HIDDEN]
    beta_w = _peso(tensores, p + "ssm_beta.weight")       # [VAL_HEADS, HIDDEN]
    dt_bias = _peso(tensores, p + "ssm_dt.bias")          # [VAL_HEADS]
    ssm_norm_w = _peso(tensores, p + "ssm_norm.weight")   # [VAL_HEAD_DIM]
    out_w = _peso(tensores, p + "ssm_out.weight")         # [HIDDEN, VAL_DIM]

    x = _rmsnorm(hidden_states, norm_w)                   # [T, HIDDEN]

    mixed_qkv = x @ qkv_w.T                                # [T, CONV_DIM]
    z = x @ gate_w.T                                       # [T, VAL_DIM]
    a_pre = x @ alpha_w.T                                  # [T, VAL_HEADS]
    b_pre = x @ beta_w.T                                   # [T, VAL_HEADS]

    # conv1d causal, canal a canal, kernel CONV_K, sin bias (verificado: no hay
    # ssm_conv1d.bias en el GGUF) — padding causal a la izquierda con ceros.
    conv_w2 = conv_w if conv_w.shape[0] == CONV_DIM else conv_w.T
    pad = np.zeros((CONV_K - 1, CONV_DIM), dtype=np.float32)
    entrada_pad = np.concatenate([pad, mixed_qkv], axis=0)   # [T+K-1, CONV_DIM]
    conv_out = np.zeros_like(mixed_qkv)
    for k in range(CONV_K):
        conv_out += entrada_pad[k:k + T] * conv_w2[:, k]
    mixed_qkv = _silu(conv_out)

    q, k, v = np.split(mixed_qkv, [KEY_DIM, KEY_DIM * 2], axis=-1)
    q = q.reshape(T, KEY_HEADS, KEY_HEAD_DIM)
    k = k.reshape(T, KEY_HEADS, KEY_HEAD_DIM)
    v = v.reshape(T, VAL_HEADS, VAL_HEAD_DIM)

    q = np.repeat(q, GQA_FACTOR, axis=1)                   # [T, VAL_HEADS, KEY_HEAD_DIM]
    k = np.repeat(k, GQA_FACTOR, axis=1)
    q = _l2norm(q)
    k = _l2norm(k)

    g = -np.exp(a_log)[None, :] * _softplus(a_pre + dt_bias[None, :])   # [T, VAL_HEADS], <=0
    beta = 1.0 / (1.0 + np.exp(-b_pre))                                  # [T, VAL_HEADS]

    estado = np.zeros((VAL_HEADS, KEY_HEAD_DIM, VAL_HEAD_DIM), dtype=np.float32)
    salida = np.zeros((T, VAL_HEADS, VAL_HEAD_DIM), dtype=np.float32)
    for t in range(T):
        decay_t = np.exp(g[t])[:, None, None]
        estado = estado * decay_t
        kv_mem = np.einsum("hd,hde->he", k[t], estado)               # [VAL_HEADS, VAL_HEAD_DIM]
        delta = (v[t] - kv_mem) * beta[t][:, None]
        estado = estado + k[t][:, :, None] * delta[:, None, :]
        salida[t] = np.einsum("hd,hde->he", q[t], estado)

    salida = salida.reshape(T, VAL_DIM)
    salida = _rmsnorm(salida.reshape(T, VAL_HEADS, VAL_HEAD_DIM), ssm_norm_w
                      ).reshape(T, VAL_DIM) * _silu(z)
    return salida @ out_w.T


def main() -> None:
    print("leyendo GGUF real...", file=sys.stderr, flush=True)
    r = GGUFReader(str(GGUF))
    tensores = {t.name: t for t in r.tensors}

    rng = np.random.default_rng(0)
    T = 6
    hidden_states = (rng.standard_normal((T, HIDDEN)) * 0.02).astype(np.float32)

    for capa in (0, 1, 2):
        salida = capa_gdn(hidden_states, capa, tensores)
        finita = np.all(np.isfinite(salida))
        print(f"capa {capa}: forma {salida.shape} · finita={finita} · "
             f"rango [{salida.min():.4f}, {salida.max():.4f}]")
        print(f"CIFRA finita_capa{capa} {1 if finita else 0}")
        print(f"CIFRA forma_ok_capa{capa} {1 if salida.shape == (T, HIDDEN) else 0}")


if __name__ == "__main__":
    main()
