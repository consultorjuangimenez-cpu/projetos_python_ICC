$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
try {
    $defaultRoot = 'C:\C\Projetos_Phyton\Portal_Apps'
    $portalRoot = Read-Host "Pasta do portal existente [Enter = $defaultRoot]"
    if ([string]::IsNullOrWhiteSpace($portalRoot)) { $portalRoot = $defaultRoot }
    $portalRoot = $portalRoot.Trim().Trim('"')
    $pythonExe = Join-Path $portalRoot '.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $pythonExe)) { throw "Python do portal nao encontrado: $pythonExe" }
    if (!(Test-Path -LiteralPath (Join-Path $portalRoot 'portal\acesso.py'))) { throw 'Esta pasta nao contem o portal com login centralizado.' }
    Write-Host 'Validando dependencias do portal...'
    & $pythonExe -c 'import flask, waitress, sys; assert sys.version_info >= (3, 10), "Python 3.10 ou superior necessario"'
    if ($LASTEXITCODE -ne 0) { throw 'O ambiente Python do portal precisa ser corrigido antes da instalacao.' }
    & $pythonExe -m pip install -r (Join-Path $packageRoot 'requirements-lembretes.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar tzdata.' }
    & $pythonExe (Join-Path $PSScriptRoot 'instalar.py') --portal $portalRoot
    if ($LASTEXITCODE -ne 0) { throw 'O instalador interrompeu a integracao. Confira o diagnostico acima.' }
    Write-Host ''
    Write-Host 'Modulo instalado. Reinicie o portal e libere Lembretes de Tarefas nas permissoes dos usuarios.' -ForegroundColor Green
    Write-Host "Proximo passo: $portalRoot\ferramentas_lembretes\CONFIGURAR_SMTP.bat"
    Write-Host "Depois: $portalRoot\ferramentas_lembretes\INSTALAR_AGENDADOR.bat (executar como administrador)."
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
