@echo off
setlocal
title Agendador de Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rodar_Agendador.ps1"
echo.
pause
endlocal
