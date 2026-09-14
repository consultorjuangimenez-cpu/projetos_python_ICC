@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Configurar.ps1"
if errorlevel 1 echo Falha ao configurar. Leia a mensagem acima.
pause
