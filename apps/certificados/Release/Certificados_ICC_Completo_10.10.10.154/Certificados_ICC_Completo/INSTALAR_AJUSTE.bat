@echo off
setlocal
cd /d "%~dp0"
echo Feche o portal antes de instalar o complemento.
set "CERT_PORTAL_DIR=C:\C\Projetos_Phyton\Portal_Apps"
set /p "CERT_PORTAL_DIR=Pasta do portal [C:\C\Projetos_Phyton\Portal_Apps]: "
if not exist "%CERT_PORTAL_DIR%\.venv\Scripts\python.exe" (
 echo Python da .venv nao encontrado. Confira a pasta.
 pause
 exit /b 1
)
"%CERT_PORTAL_DIR%\.venv\Scripts\python.exe" "%~dp0instalar_ajuste.py" "%CERT_PORTAL_DIR%"
pause
