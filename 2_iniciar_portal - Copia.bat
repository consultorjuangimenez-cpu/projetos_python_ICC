@echo off
setlocal
cd /d "%~dp0"
set "PORTAL_SMTP_SENHA=Estefany!113"
set "PORTAL_SMTP_SENHA_VIVIANEZ=Icc@123"
title Portal Python - Servidor Interno
if not exist ".venv\Scripts\python.exe" (
 echo Execute primeiro 1_instalar.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" servidor.py
if errorlevel 1 (
 echo.
 echo Falha ao iniciar. Confira a mensagem acima.
 pause
)
