@echo off
setlocal
cd /d "%~dp0"
echo Feche o portal antes de instalar este modulo.
echo.
set "CERT_PORTAL_DIR=C:\C\Projetos_Phyton\Portal_Apps"
set /p "CERT_PORTAL_DIR=Pasta do portal [C:\C\Projetos_Phyton\Portal_Apps]: "
if not exist "%CERT_PORTAL_DIR%\.venv\Scripts\python.exe" (
 echo ERRO: Python da .venv nao encontrado na pasta informada.
 echo Execute instalar_no_portal.py com o mesmo Python utilizado pelo portal.
 pause
 exit /b 1
)
"%CERT_PORTAL_DIR%\.venv\Scripts\python.exe" -c "import flask, openpyxl, cryptography; from cryptography.fernet import Fernet; from cryptography import x509; assert hasattr(x509.Certificate, 'not_valid_after_utc')"
if errorlevel 1 (
 echo ERRO: Confira as dependencias em requirements_certificados.txt.
 pause
 exit /b 1
)
"%CERT_PORTAL_DIR%\.venv\Scripts\python.exe" "%~dp0instalar_no_portal.py" "%CERT_PORTAL_DIR%"
if errorlevel 1 (
 echo Nao foi possivel instalar. Leia a mensagem acima.
 pause
 exit /b 1
)
echo.
echo Modulo instalado. Reinicie o servidor pelo BAT habitual.
pause
