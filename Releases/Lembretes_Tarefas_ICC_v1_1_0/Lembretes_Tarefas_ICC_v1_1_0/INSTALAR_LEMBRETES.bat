@echo off
setlocal
title Instalar Lembretes de Tarefas ICC
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0ferramentas_lembretes\Instalar.ps1"
if errorlevel 1 (
  echo.
  echo A instalacao nao foi concluida. Confira a mensagem acima.
)
echo.
pause
endlocal
