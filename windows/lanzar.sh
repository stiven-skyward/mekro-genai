#!/usr/bin/env bash
# Arranca `genai` dentro de WSL para quien invoca windows/mekro-genai-wsl.cmd.
#
# La razón de ser de este fichero: la lógica de arranque (instalar solo la
# primera vez, en un entorno propio) es demasiado para vivir dentro de una
# línea de un .cmd de Windows — cmd.exe la mutila de formas distintas según
# cuántos `;`, `{`, `$`, comillas y paréntesis lleve la línea, y cada intento
# de arreglarlo a base de escapes fue un fallo nuevo. Un script de bash de
# verdad, con líneas de verdad, no tiene ese problema.
set -e
cd "$(dirname "$0")/.."   # windows/ está siempre un nivel por debajo de la raíz

if ! command -v python3 >/dev/null 2>&1; then
    echo "[Mekro-Genai] falta python3 en esta distro. Instala con:"
    echo "  sudo apt update && sudo apt install -y python3 python3-pip python3-venv"
    exit 1
fi

if command -v genai >/dev/null 2>&1; then
    GENAI=genai
elif [ -x .venv/bin/genai ]; then
    GENAI=.venv/bin/genai
else
    echo "[Mekro-Genai] primera vez aquí: preparando un entorno propio en .venv"
    echo "(evita el Python del sistema y sus permisos)..."
    python3 -m venv .venv || {
        echo "[Mekro-Genai] no se pudo crear el entorno virtual. Prueba:"
        echo "  sudo apt install -y python3-venv"
        exit 1
    }
    .venv/bin/pip install -e . || {
        echo "[Mekro-Genai] falló instalando dentro del entorno virtual."
        exit 1
    }
    echo "[Mekro-Genai] listo."
    GENAI=.venv/bin/genai
fi

if [ "$#" -eq 0 ]; then
    set -- chat
fi
exec "$GENAI" "$@"
