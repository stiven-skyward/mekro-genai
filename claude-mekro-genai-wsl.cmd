@echo off
REM Lanza Claude Code en WSL con proxy Headroom auto + RTK
setlocal
set "DISTRO=Ubuntu-22.04"
set "MEKROGENAI=%~1"
if "%MEKROGENAI%"=="" set "MEKROGENAI=/mnt/e/Mekro-Genai"
wsl -d %DISTRO% -- bash -lc "sed -i 's/\r$//' /mnt/e/cursor_context/ice/wsl/*.sh ~/.local/bin/claude-wsl 2>/dev/null; cp -f /mnt/e/cursor_context/ice/wsl/claude-wsl-launcher.sh ~/.local/bin/claude-wsl 2>/dev/null; chmod +x ~/.local/bin/claude-wsl /mnt/e/cursor_context/ice/wsl/*.sh; cd %MEKROGENAI% && ~/.local/bin/claude-wsl %MEKROGENAI% %*"
exit /b %ERRORLEVEL%