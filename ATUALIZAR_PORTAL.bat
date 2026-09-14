@echo off
setlocal
cd /d "%~dp0"
title Atualizar aplicativos do portal
if not exist ".venv\Scripts\python.exe" (
 echo Ambiente Python do portal nao encontrado.
 echo Copie o conteudo deste pacote para a pasta do portal atual.
 echo Se necessario, execute o 1_instalar.bat do portal antes desta atualizacao.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" portal\atualizar_pacote.py
if errorlevel 1 goto erro
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo.
echo Atualizacao concluida. Confira config_apps.ini.
echo Para Emitir Guias, execute 5_instalar_navegador_guias.bat.
echo Depois execute 2_iniciar_portal.bat e libere os apps para os usuarios.
pause
exit /b 0
:erro
echo.
echo A atualizacao nao foi concluida. Confira a mensagem acima.
echo Corrija o problema e execute este BAT novamente. O cadastro nao sera duplicado.
pause
exit /b 1
