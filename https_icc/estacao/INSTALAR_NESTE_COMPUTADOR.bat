@echo off
setlocal
cd /d "%~dp0"
title Preparar acesso ao Portal ICC
echo Preparando HTTPS e Auxiliar ICC para o usuario atual do Windows.
echo Execute somente o pacote entregue pela TI da ICC.
echo.
set "CERT_ICC_ROOT=%~dp0ICC-HTTPS.cer"
powershell.exe -NoLogo -NoProfile -Command "$ErrorActionPreference='Stop'; try { $h=(Get-FileHash -LiteralPath $env:CERT_ICC_ROOT -Algorithm SHA256).Hash; if ($h -ne '__SHA256__') { throw 'O certificado nao corresponde ao pacote da TI. Instalacao cancelada.' }; Import-Certificate -FilePath $env:CERT_ICC_ROOT -CertStoreLocation 'Cert:\CurrentUser\Root' -ErrorAction Stop | Out-Null; Write-Host 'Confianca HTTPS instalada.' -ForegroundColor Green } catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
 echo Nao foi possivel instalar a confianca HTTPS. Envie a mensagem para a TI.
 pause
 exit /b 1
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0Configurar.ps1"
if errorlevel 1 (
 echo HTTPS preparado, mas o auxiliar nao foi configurado. Envie a mensagem para a TI.
 pause
 exit /b 1
)
echo.
echo Configuracao concluida. O portal sera aberto.
start "" "https://10.10.10.154/certificados/"
pause
