@echo off
setlocal
cd /d "%~dp0"
title Instalar Portal Python
if exist ".venv\Scripts\python.exe" goto dependencias
where py >nul 2>&1
if errorlevel 1 goto usar_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto versao
py -3 -m venv .venv
if errorlevel 1 goto erro
goto dependencias
:usar_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto versao
python -m venv .venv
if errorlevel 1 goto erro
:dependencias
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo.
echo Instalacao concluida. Confira config.ini e execute 2_iniciar_portal.bat.
pause
exit /b 0
:versao
echo Python 3.10 ou superior nao encontrado. Instale no notebook servidor.
:erro
echo Falha na instalacao. Confira a mensagem acima e a conexao com a internet.
pause
exit /b 1
