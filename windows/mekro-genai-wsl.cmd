@echo off
REM Lanza la CLI de Mekro-Genai (genai) en WSL. PENSADO PARA UN CLIC:
REM la primera vez se prepara un entorno propio (.venv) e instala solo, sin
REM tocar el Python del sistema -- evita el fallo de permisos de site-packages
REM que algunas distros de WSL traen de fabrica.
REM Sin argumentos abre una conversacion (genai chat); con argumentos, los
REM reenvia tal cual: mekro-genai-wsl.cmd tarea "arregla el bug" / ui / sesiones...
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=/mnt/e/Mekro-Genai"
set "ORDEN=%*"
if "%ORDEN%"=="" set "ORDEN=chat"
wsl -d %DISTRO% -- bash -lc "cd %MEKROGENAI% || { echo [Mekro-Genai] no encuentro el proyecto en %MEKROGENAI% dentro de WSL.; exit 1; }; command -v python3 >/dev/null 2>&1 || { echo [Mekro-Genai] falta python3 en esta distro. Instala con:; echo   sudo apt update && sudo apt install -y python3 python3-pip python3-venv; exit 1; }; if command -v genai >/dev/null 2>&1; then GENAI=genai; elif [ -x %MEKROGENAI%/.venv/bin/genai ]; then GENAI=%MEKROGENAI%/.venv/bin/genai; else echo [Mekro-Genai] primera vez aqui: preparando un entorno propio en .venv \(evita el Python del sistema y sus permisos\)...; python3 -m venv %MEKROGENAI%/.venv || { echo [Mekro-Genai] no se pudo crear el entorno virtual. Prueba: sudo apt install -y python3-venv; exit 1; }; %MEKROGENAI%/.venv/bin/pip install -e %MEKROGENAI% || { echo [Mekro-Genai] fallo instalando dentro del entorno virtual.; exit 1; }; echo [Mekro-Genai] listo.; GENAI=%MEKROGENAI%/.venv/bin/genai; fi; $GENAI %ORDEN%"
if errorlevel 1 (
    echo.
    echo [Mekro-Genai] no se pudo lanzar ^(distro: %DISTRO%^). Si el mensaje de
    echo arriba no lo explica, comprueba que la distro existe:   wsl -l -v
    echo.
    pause
)
exit /b %ERRORLEVEL%
