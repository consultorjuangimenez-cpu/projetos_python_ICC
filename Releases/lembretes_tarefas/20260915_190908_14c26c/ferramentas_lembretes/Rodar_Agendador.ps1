param([switch]$Verificar)
$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $portalRoot '.venv\Scripts\python.exe'
$credentialPath = Join-Path $portalRoot 'dados\apps\lembretes_tarefas\smtp_credencial.xml'
$workerExitCode = 1
try {
    if (!(Test-Path -LiteralPath $pythonExe)) { throw 'Python do portal nao encontrado.' }
    if ([string]::IsNullOrEmpty($env:PORTAL_SMTP_SENHA) -and (Test-Path -LiteralPath $credentialPath)) {
        $smtpCredential = Import-Clixml -LiteralPath $credentialPath
        $env:PORTAL_SMTP_SENHA = $smtpCredential.GetNetworkCredential().Password
        if ([string]::IsNullOrEmpty($env:PORTAL_SMTP_USUARIO)) { $env:PORTAL_SMTP_USUARIO = $smtpCredential.UserName }
    }
    $env:PYTHONUTF8 = '1'
    Set-Location -LiteralPath $portalRoot
    if ($Verificar) {
        & $pythonExe -m apps.lembretes_tarefas.worker --check
    } else {
        & $pythonExe -m apps.lembretes_tarefas.worker
    }
    $workerExitCode = $LASTEXITCODE
} catch {
    # Nao imprimir a credencial ou o conteudo retornado pelo Import-Clixml.
    Write-Host 'Falha ao iniciar o agendador. Confira o caminho do portal e a conta Windows que protegeu a credencial SMTP.' -ForegroundColor Red
    $workerExitCode = 1
} finally {
    Remove-Item Env:\PORTAL_SMTP_SENHA -ErrorAction SilentlyContinue
    $smtpCredential = $null
}
exit $workerExitCode
