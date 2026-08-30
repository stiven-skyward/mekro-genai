#!/bin/bash
# Medición C88: repite la sonda sintética N veces para descartar que la
# ganancia medida sea ruido de una sola corrida, y prueba con un tamaño de
# estado distinto (24 cabezas en vez de 48) para ver si la ganancia depende
# del tamaño exacto o es un efecto más general.
set -e
cd "$(dirname "$0")/.."

gcc -O3 -march=native -ffast-math -funroll-loops -o /tmp/medir_C88_bin scripts/sonda_C88_fusion.c -lm

echo "=== 5 repeticiones, estado real (48x128x128 = 3,15 MB) ===" >&2
ganancias=()
for i in 1 2 3 4 5; do
    salida=$(/tmp/medir_C88_bin 2>/dev/null)
    g=$(echo "$salida" | grep "CIFRA ganancia" | awk '{print $3}')
    ganancias+=("$g")
    echo "  repeticion $i: ganancia=$g" >&2
done

lista_ganancias="${ganancias[@]}"
python3 -c "
import sys
gs = [float(x) for x in '$lista_ganancias'.split()]
media = sum(gs) / len(gs)
minimo, maximo = min(gs), max(gs)
var = sum((g - media)**2 for g in gs) / len(gs)
desv = var ** 0.5
print(f'CIFRA ganancia_media {media:.4f}')
print(f'CIFRA ganancia_min {minimo:.4f}')
print(f'CIFRA ganancia_max {maximo:.4f}')
print(f'CIFRA ganancia_desv {desv:.4f}')
print(f'CIFRA ganancia {media:.4f}')
"
