[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
try {
    $sourceConfig = Join-Path $PSScriptRoot 'config.json'
    if (-not (Test-Path -LiteralPath $sourceConfig)) { throw 'Baixe o auxiliar configurado pelo botão Como instalar no painel, usando a conta da TI e HTTPS.' }
    $config = Get-Content -LiteralPath $sourceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $url = [Uri]([string]$config.url)
    if ($url.Scheme -ne 'https' -or -not $url.Host -or $url.UserInfo -or $url.Query -or $url.Fragment) { throw 'O endereço precisa ser HTTPS, sem usuário, senha ou parâmetros.' }
    $destination = Join-Path $env:LOCALAPPDATA 'ICC\AuxiliarCertificados'
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    foreach ($name in @('Auxiliar.ps1','config.json','Remover.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $destination $name) -Force
    }
    $key = 'HKCU:\Software\Classes\icc-cert'
    New-Item -Path $key -Force | Out-Null
    Set-Item -Path $key -Value 'URL:Auxiliar de Certificados ICC'
    New-ItemProperty -Path $key -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
    New-Item -Path "$key\shell\open\command" -Force | Out-Null
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $script = Join-Path $destination 'Auxiliar.ps1'
    $command = '"{0}" -NoLogo -NoProfile -ExecutionPolicy RemoteSigned -File "{1}" "%1"' -f $powershell,$script
    Set-Item -Path "$key\shell\open\command" -Value $command
    Write-Host "Auxiliar configurado para $env:USERDOMAIN\$env:USERNAME." -ForegroundColor Green
    Write-Host "Portal: $($config.url)"
    Write-Host 'Volte ao painel e clique em INSTALAR. O navegador pode pedir para abrir o Auxiliar ICC.'
    exit 0
} catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
