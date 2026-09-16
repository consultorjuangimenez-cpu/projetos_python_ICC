@echo off
setlocal
title Instalar Agendador de Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Instalar_Agendador.ps1"
echo.
pause
endlocal
