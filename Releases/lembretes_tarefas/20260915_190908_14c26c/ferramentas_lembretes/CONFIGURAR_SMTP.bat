@echo off
setlocal
title Configurar SMTP dos Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Configurar_SMTP.ps1"
echo.
pause
endlocal
