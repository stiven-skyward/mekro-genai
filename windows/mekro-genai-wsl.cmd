@echo off
REM Lanza la CLI de Mekro-Genai (genai) en WSL: tarea, chat, ui, sesiones, mcp...
REM Requiere haber corrido antes, DENTRO de WSL: pip install -e .  (ver README.md)
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=/mnt/e/Mekro-Genai"
wsl -d %DISTRO% -- bash -lc "cd %MEKROGENAI% && genai %*"
exit /b %ERRORLEVEL%
