#!/usr/bin/env bash
# La foto al retomar: qué corre, qué hay, qué sigue. Nada aquí tarda más de un segundo.
cd "$(dirname "$0")/.." || exit 1

echo "== Mekro-Genai · $(date '+%Y-%m-%d %H:%M') =="
echo
echo "-- procesos propios (por fichero de PID, nunca por patrón) --"
# Por fichero y no por `pgrep python`: matar por patrón mata también la sesión que mira.
encontrado=0
for f in logs/*.pid; do
  [ -e "$f" ] || continue
  pid=$(cat "$f")
  if kill -0 "$pid" 2>/dev/null; then
    echo "  VIVO   $f (pid $pid)"
  else
    echo "  muerto $f (pid $pid) — revisar su log"
  fi
  encontrado=1
done
[ "$encontrado" = 0 ] && echo "  nada corre (y puede ser correcto: mira ESTADO_VIVO.md)"

echo
echo "-- el cerebro --"
CAMPEON="${MG_CAMPEON:-/mnt/e/QuantModels/modelos/qwen38-h13b}"
if [ -d "$CAMPEON" ]; then
  echo "  campeón v13: $CAMPEON ($(du -sh "$CAMPEON" 2>/dev/null | cut -f1), bf16 DESHECHO)"
else
  echo "  ⚠ no se ve el campeón en $CAMPEON — ¿está montada E:?"
fi
if [ -f genai/cerebro/local_packed.py ]; then
  echo "  empaquetado 2 bits: PRESENTE"
else
  echo "  empaquetado 2 bits: NO EXISTE → M1 bloqueado (holograma H1)"
fi

echo
echo "-- máquina (GPU vetada en este proyecto por decisión del autor) --"
echo "  $(nproc) hilos · RAM $(free -g | awk '/^Mem:/{print $7" GB disponibles de "$2}')"
df -h /mnt/e | tail -1 | awk '{print "  disco E: "$4" libres de "$2}'

echo
echo "-- hologramas --"
python3 holograma.py listar

echo
echo "-- ciclo de investigación --"
python3 ciclo.py estado

echo
echo "-- últimos registros (no se borran nunca) --"
ls -t registros/*.json 2>/dev/null | head -3 | sed 's/^/  /' || echo "  ninguno todavía"

echo
echo "Siguiente paso: ESTADO_VIVO.md → sección «LO SIGUIENTE»"
