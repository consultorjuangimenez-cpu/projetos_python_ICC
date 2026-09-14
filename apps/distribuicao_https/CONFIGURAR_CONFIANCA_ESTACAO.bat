@echo off
setlocal
set "PS1=%~dp0INSTALAR_CONFIANCA_ESTACAO.ps1"
if not exist "%PS1%" (
  echo ERRO: nao encontrei "%PS1%"
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%PS1%""'"
if errorlevel 1 (
  echo.
  echo A configuracao nao foi concluida.
  pause
  exit /b 1
)
echo.
echo Confianca HTTPS configurada. Feche e abra novamente o navegador.
pause
