@echo off
setlocal
title Diagnostico SMTP - Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rodar_Agendador.ps1" -Diagnosticar
echo.
pause
endlocal
