@echo off
setlocal
title Teste de senha SMTP digitada - Lembretes ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Rodar_Agendador.ps1" -Diagnosticar -DigitarCredencial
echo.
pause
endlocal
