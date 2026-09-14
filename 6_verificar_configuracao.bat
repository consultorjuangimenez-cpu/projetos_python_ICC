@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Execute primeiro 1_instalar.bat.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m portal.verificar
pause
