@echo off
setlocal
cd /d "%~dp0"
if not exist "..\.venv\Scripts\python.exe" (
 echo ERRO: coloque esta pasta como Portal_Apps\https_icc.
 pause
 exit /b 1
)
"..\.venv\Scripts\python.exe" "%~dp0https_icc.py" configurar
pause
