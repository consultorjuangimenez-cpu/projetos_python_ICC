@echo off
setlocal
cd /d "%~dp0"


set "PORTAL_SMTP_SENHA=Estefany!113"
set "PORTAL_SMTP_SENHA_VIVIANEZ=Icc@123"

title Portal Python - Servidor Interno


REM ==================================================
REM VERIFICAR CADDY
REM ==================================================

echo Verificando Caddy...

powershell -NoProfile -Command "$c = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue | Where-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName -eq 'caddy' }; if ($c) { exit 0 } else { exit 1 }"

if errorlevel 1 (
    echo Caddy nao encontrado. Acionando tarefa do Windows...
    schtasks /run /tn "\ICC Portal HTTPS - Caddy"
)

REM ==================================================
REM AGUARDAR CADDY FICAR DISPONIVEL
REM ==================================================

echo Aguardando Caddy...

powershell -NoProfile -Command "$ok = $false; for ($i=0; $i -lt 30; $i++) { $c = Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue | Where-Object { (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName -eq 'caddy' }; if ($c) { $ok = $true; break }; Start-Sleep -Seconds 1 }; if (-not $ok) { exit 1 }"

if errorlevel 1 (
    echo ERRO: Caddy nao ficou disponivel na porta 443.
    pause
    exit /b 1
)

echo Caddy OK.
echo Iniciando Portal Python...

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