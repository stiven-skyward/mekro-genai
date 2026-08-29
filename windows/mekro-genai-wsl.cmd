@echo off
REM Lanza la CLI de Mekro-Genai (genai) en WSL.
REM Sin argumentos abre una conversacion (genai chat); con argumentos, los
REM reenvia tal cual: mekro-genai-wsl.cmd tarea "arregla el bug" / ui / sesiones...
REM Requiere haber corrido antes, DENTRO de WSL: pip install -e .  (ver README.md)
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=/mnt/e/Mekro-Genai"
set "ORDEN=%*"
if "%ORDEN%"=="" set "ORDEN=chat"
wsl -d %DISTRO% -- bash -lc "cd %MEKROGENAI% && genai %ORDEN%"
if errorlevel 1 (
    echo.
    echo [Mekro-Genai] fallo al lanzar genai dentro de WSL ^(distro: %DISTRO%^).
    echo   - Comprueba que esa distro existe:   wsl -l -v
    echo   - Dentro de esa distro, en %MEKROGENAI%:   pip install -e .
    echo.
    pause
)
exit /b %ERRORLEVEL%
