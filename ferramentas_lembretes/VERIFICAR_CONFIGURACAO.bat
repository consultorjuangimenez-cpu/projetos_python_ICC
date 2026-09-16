@echo off
setlocal
title Diagnostico de Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rodar_Agendador.ps1" -Verificar
echo.
pause
endlocal
