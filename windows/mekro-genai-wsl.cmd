@echo off
REM Lanza la CLI de Mekro-Genai (genai) en WSL. PENSADO PARA UN CLIC:
REM la primera vez se instala solo (pip install -e .) si genai no esta todavia.
REM Sin argumentos abre una conversacion (genai chat); con argumentos, los
REM reenvia tal cual: mekro-genai-wsl.cmd tarea "arregla el bug" / ui / sesiones...
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=/mnt/e/Mekro-Genai"
set "ORDEN=%*"
if "%ORDEN%"=="" set "ORDEN=chat"
wsl -d %DISTRO% -- bash -lc "cd %MEKROGENAI% || { echo [Mekro-Genai] no encuentro el proyecto en %MEKROGENAI% dentro de WSL.; exit 1; }; command -v python3 >/dev/null 2>&1 || { echo [Mekro-Genai] falta python3 en esta distro. Instala con:; echo   sudo apt update && sudo apt install -y python3 python3-pip python3-venv; exit 1; }; command -v genai >/dev/null 2>&1 || { echo [Mekro-Genai] primera vez aqui: instalando \(pip install -e .\)...; pip install -e . 2>/dev/null || pip3 install -e . 2>/dev/null || python3 -m pip install -e . || { echo [Mekro-Genai] no se pudo instalar solo. Prueba a mano: sudo apt install -y python3-pip; exit 1; }; echo [Mekro-Genai] instalado.; }; genai %ORDEN%"
if errorlevel 1 (
    echo.
    echo [Mekro-Genai] no se pudo lanzar ^(distro: %DISTRO%^). Si el mensaje de
    echo arriba no lo explica, comprueba que la distro existe:   wsl -l -v
    echo.
    pause
)
exit /b %ERRORLEVEL%
