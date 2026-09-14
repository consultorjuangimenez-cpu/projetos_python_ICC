[CmdletBinding()]
param([string]$PortalRoot = "")
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Execute como Administrador."
}

if (-not $PortalRoot) {
    foreach ($candidate in @("C:\C\Projetos_Phyton\Portal_Apps", "C:\C\Projetos Python\Portal de APPS", (Split-Path $PSScriptRoot -Parent))) {
        if ($candidate -and (Test-Path (Join-Path $candidate "aplicativos.json"))) { $PortalRoot = $candidate; break }
    }
}
if (-not $PortalRoot) { throw "Informe -PortalRoot com a raiz do portal." }
$PortalRoot = (Resolve-Path -LiteralPath $PortalRoot).Path

$backup = Get-ChildItem -LiteralPath $PortalRoot -Directory -Filter 'backup_https_*' | Sort-Object Name -Descending | Select-Object -First 1
if (-not $backup) { throw "Nenhum backup_https_* foi encontrado em $PortalRoot." }

foreach ($relative in @("config.ini", "config_apps.ini", "aplicativos.json", "servidor.py", "portal\servidor.py")) {
    $source = Join-Path $backup.FullName $relative
    if (Test-Path -LiteralPath $source) {
        $target = Join-Path $PortalRoot $relative
        $parent = Split-Path -Parent $target
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $source -Destination $target -Force
        Write-Host "Restaurado: $relative"
    }
}

Unregister-ScheduledTask -TaskName 'ICC Portal HTTPS - Caddy' -Confirm:$false -ErrorAction SilentlyContinue
foreach ($name in @('ICC Portal HTTPS - 443','ICC Portal HTTPS - 80','ICC Portal Python - bloquear 8080 rede privada')) {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
}
Write-Host "`nReversão concluída a partir de: $($backup.FullName)" -ForegroundColor Green
Write-Host "Reinicie o processo do Portal Python. O diretório C:\ProgramData\ICC\Caddy foi preservado para auditoria e pode ser removido manualmente depois da conferência."
