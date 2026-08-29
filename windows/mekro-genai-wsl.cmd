@echo off
REM Lanza la CLI de Mekro-Genai (genai) en WSL. PENSADO PARA UN CLIC:
REM windows\lanzar.sh (dentro de WSL) prepara un entorno propio (.venv) e
REM instala solo la primera vez, sin tocar el Python del sistema.
REM Sin argumentos abre una conversacion (genai chat); con argumentos, los
REM reenvia tal cual: mekro-genai-wsl.cmd tarea "arregla el bug" / ui / sesiones...
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=/mnt/e/Mekro-Genai"
wsl -d %DISTRO% -- bash %MEKROGENAI%/windows/lanzar.sh %*
if errorlevel 1 (
    echo.
    echo [Mekro-Genai] no se pudo lanzar ^(distro: %DISTRO%^). Si el mensaje de
    echo arriba no lo explica, comprueba que la distro existe:   wsl -l -v
    echo.
    pause
)
exit /b %ERRORLEVEL%
