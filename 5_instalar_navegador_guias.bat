@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute primeiro 1_instalar.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
 echo Falha ao instalar o navegador. Confira a mensagem acima.
 pause
 exit /b 1
)
echo Navegador instalado para o usuario atual do Windows.
pause
