[CmdletBinding()]
param(
    [string]$PortalRoot = "",
    [string]$PortalIP = "10.10.10.154",
    [int]$BackendPort = 8080,
    [string]$RotaCertificados = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$TaskName = "ICC Portal HTTPS - Caddy"
$InstallRoot = "C:\ProgramData\ICC\Caddy"
$CaddyFile = Join-Path $InstallRoot "Caddyfile"
$StartScript = Join-Path $InstallRoot "Iniciar-Caddy.ps1"
$Firewall443 = "ICC Portal HTTPS - 443"
$Firewall80 = "ICC Portal HTTPS - 80"
$FirewallBackend = "ICC Portal Python - bloquear 8080 rede privada"

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Execute este script em um PowerShell aberto como Administrador."
    }
}

function Resolve-PortalRoot([string]$Requested) {
    if ($Requested) {
        $resolved = (Resolve-Path -LiteralPath $Requested).Path
        if ((Test-Path (Join-Path $resolved "aplicativos.json")) -and
            (Test-Path (Join-Path $resolved "config_apps.ini"))) {
            return $resolved
        }
        throw "PortalRoot inválido: não encontrei aplicativos.json e config_apps.ini em '$resolved'."
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    $cursor = $PSScriptRoot
    for ($i = 0; $i -lt 5; $i++) {
        if ($cursor) { [void]$candidates.Add($cursor) }
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    [void]$candidates.Add("C:\C\Projetos_Phyton\Portal_Apps")
    [void]$candidates.Add("C:\C\Projetos Python\Portal de APPS")

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ((Test-Path (Join-Path $candidate "aplicativos.json")) -and
            (Test-Path (Join-Path $candidate "config_apps.ini"))) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Não localizei a raiz do Portal. Execute novamente informando -PortalRoot 'C:\caminho\do\Portal_Apps'."
}

function Normalize-Route([string]$Route) {
    $r = $Route.Trim()
    if (-not $r) { throw "A rota do módulo de certificados está vazia." }
    if (-not $r.StartsWith('/')) { $r = '/' + $r }
    if ($r.Length -gt 1) { $r = $r.TrimEnd('/') }
    return $r
}

function Resolve-CertRoute([string]$Root, [string]$Requested) {
    if ($Requested) { return (Normalize-Route $Requested) }

    $catalog = Get-Content -LiteralPath (Join-Path $Root "aplicativos.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $entry = @($catalog) | Where-Object {
        $_.modulo -and ([string]$_.modulo -match '(^|\.)certificados\.app$')
    } | Select-Object -First 1

    if (-not $entry) {
        throw @"
Não encontrei no aplicativos.json um módulo com nome Python terminando em 'certificados.app'.
Cadastre o módulo no portal ou execute novamente informando, por exemplo:
  -RotaCertificados '/certificados'
"@
    }
    return (Normalize-Route ([string]$entry.rota))
}

function Backup-File([string]$Root, [string]$BackupRoot, [string]$RelativePath) {
    $source = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $source)) { return }
    $target = Join-Path $BackupRoot $RelativePath
    $parent = Split-Path -Parent $target
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item -LiteralPath $source -Destination $target -Force
}

function Set-IniValue([string]$Path, [string]$Section, [string]$Key, [string]$Value) {
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) { [void]$lines.Add([string]$line) }
    }

    $sectionPattern = '^\s*\[' + [regex]::Escape($Section) + '\]\s*$'
    $keyPattern = '^\s*' + [regex]::Escape($Key) + '\s*='
    $sectionIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $sectionPattern) { $sectionIndex = $i; break }
    }

    if ($sectionIndex -lt 0) {
        if ($lines.Count -gt 0 -and $lines[$lines.Count - 1].Trim()) { [void]$lines.Add("") }
        [void]$lines.Add("[$Section]")
        [void]$lines.Add("$Key = $Value")
    } else {
        $nextSection = $lines.Count
        for ($i = $sectionIndex + 1; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '^\s*\[.+\]\s*$') { $nextSection = $i; break }
        }
        $keyIndex = -1
        for ($i = $sectionIndex + 1; $i -lt $nextSection; $i++) {
            if ($lines[$i] -match $keyPattern) { $keyIndex = $i; break }
        }
        if ($keyIndex -ge 0) {
            $lines[$keyIndex] = "$Key = $Value"
        } else {
            $lines.Insert($nextSection, "$Key = $Value")
        }
    }

    [IO.File]::WriteAllLines($Path, $lines, (New-Object Text.UTF8Encoding($true)))
}

function Patch-BackendBinding([string]$Root, [string]$IP, [int]$Port) {
    $changed = $false
    $escapedIP = [regex]::Escape($IP)
    $pattern = "host\s*=\s*(['`"])(?:0\.0\.0\.0|$escapedIP)\1"
    foreach ($relative in @("servidor.py", "portal\servidor.py")) {
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path)) { continue }
        $text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
        if ($text -notmatch [regex]::Escape([string]$Port)) { continue }
        $updated = [regex]::Replace($text, $pattern, "host='127.0.0.1'", [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($updated -ne $text) {
            [IO.File]::WriteAllText($path, $updated, (New-Object Text.UTF8Encoding($false)))
            Write-Host "Backend ajustado para loopback em: $relative"
            $changed = $true
        }
    }
    return $changed
}

function Resolve-CaddyBinary {
    $local = Join-Path $PSScriptRoot "caddy.exe"
    if (Test-Path -LiteralPath $local) { return (Resolve-Path $local).Path }
    $cmd = Get-Command caddy.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw @"
Não encontrei caddy.exe.
Baixe o binário oficial do Caddy para Windows e coloque caddy.exe na mesma pasta deste script.
Página oficial: https://caddyserver.com/download
"@
}

function Ensure-FirewallRule([string]$Name, [int]$Port, [string]$Action, [string[]]$RemoteAddress) {
    Get-NetFirewallRule -DisplayName $Name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    $params = @{
        DisplayName = $Name
        Direction = 'Inbound'
        Action = $Action
        Protocol = 'TCP'
        LocalPort = $Port
        Profile = 'Any'
    }
    if ($RemoteAddress -and $RemoteAddress.Count -gt 0) { $params.RemoteAddress = $RemoteAddress }
    New-NetFirewallRule @params | Out-Null
}

function Get-CertificateSha256([string]$Path) {
    $cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2($Path)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            return ([BitConverter]::ToString($sha.ComputeHash($cert.RawData))).Replace('-', '')
        } finally { $sha.Dispose() }
    } finally { $cert.Dispose() }
}

Assert-Administrator
$PortalRoot = Resolve-PortalRoot $PortalRoot
$RotaCertificados = Resolve-CertRoute $PortalRoot $RotaCertificados
$PublicUrl = "https://$PortalIP$RotaCertificados"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $PortalRoot "backup_https_$timestamp"
$DistribRoot = Join-Path $PortalRoot "distribuicao_https"

Write-Step "Configuração identificada"
Write-Host "Portal:        $PortalRoot"
Write-Host "Backend:       http://127.0.0.1:$BackendPort"
Write-Host "HTTPS público: https://$PortalIP/"
Write-Host "Módulo:        $PublicUrl"
Write-Host "Backup:        $BackupRoot"

Write-Step "Criando backup antes das alterações"
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
foreach ($relative in @("config.ini", "config_apps.ini", "aplicativos.json", "servidor.py", "portal\servidor.py")) {
    Backup-File $PortalRoot $BackupRoot $relative
}
@{
    criado_em = (Get-Date).ToString('o')
    portal_root = $PortalRoot
    portal_ip = $PortalIP
    backend_port = $BackendPort
    rota_certificados = $RotaCertificados
    url_publica = $PublicUrl
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BackupRoot "MANIFESTO.json") -Encoding UTF8

Write-Step "Configurando URL pública do módulo"
Set-IniValue (Join-Path $PortalRoot "config_apps.ini") "certificados_painel" "url_publica" $PublicUrl
Write-Host "url_publica = $PublicUrl"

Write-Step "Restringindo o backend Python"
$bindingChanged = Patch-BackendBinding $PortalRoot $PortalIP $BackendPort
if (-not $bindingChanged) {
    Write-Warning "Não encontrei um host=0.0.0.0/10.10.10.154 conhecido nos arquivos de inicialização. A regra de firewall abaixo continuará bloqueando a porta $BackendPort para redes privadas."
}

# A regra de bloqueio funciona também como segunda barreira mesmo quando o Python já está em 127.0.0.1.
Ensure-FirewallRule $FirewallBackend $BackendPort 'Block' @('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')
Ensure-FirewallRule $Firewall443 443 'Allow' @()
Ensure-FirewallRule $Firewall80 80 'Allow' @()

Write-Step "Instalando a configuração do Caddy"
$caddySource = Resolve-CaddyBinary
New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$caddyExe = Join-Path $InstallRoot "caddy.exe"
if ((Resolve-Path -LiteralPath $caddySource).Path -ne $caddyExe) {
    Copy-Item -LiteralPath $caddySource -Destination $caddyExe -Force
}

$caddyConfig = @"
{
    admin 127.0.0.1:2019
}

$PortalIP {
    tls internal

    reverse_proxy 127.0.0.1:$BackendPort {
        header_up X-ICC-HTTPS-Proxy "1"
    }

    header {
        X-Content-Type-Options "nosniff"
        Referrer-Policy "no-referrer"
        X-Frame-Options "SAMEORIGIN"
    }
}
"@
[IO.File]::WriteAllText($CaddyFile, $caddyConfig, (New-Object Text.UTF8Encoding($false)))

$dataHome = Join-Path $InstallRoot "data"
$configHome = Join-Path $InstallRoot "config"
New-Item -ItemType Directory -Path $dataHome,$configHome -Force | Out-Null
$env:XDG_DATA_HOME = $dataHome
$env:XDG_CONFIG_HOME = $configHome
& $caddyExe validate --config $CaddyFile --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw "O Caddy rejeitou a configuração. Nada será iniciado." }

$startBody = @"
`$ErrorActionPreference = 'Stop'
`$env:XDG_DATA_HOME = '$dataHome'
`$env:XDG_CONFIG_HOME = '$configHome'
& '$caddyExe' run --config '$CaddyFile' --adapter caddyfile
exit `$LASTEXITCODE
"@
[IO.File]::WriteAllText($StartScript, $startBody, (New-Object Text.UTF8Encoding($false)))

Write-Step "Registrando o Caddy para iniciar com o Windows"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Get-Process -Name caddy -ErrorAction SilentlyContinue | Where-Object {
    try { $_.Path -and ([IO.Path]::GetFullPath($_.Path) -eq [IO.Path]::GetFullPath($caddyExe)) } catch { $false }
} | Stop-Process -Force -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Proxy HTTPS interno do Portal ICC" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Step "Aguardando a autoridade HTTPS ser criada"
$rootCert = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $rootCert = Get-ChildItem -LiteralPath $dataHome -Filter "root.crt" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '[\\/]pki[\\/]authorities[\\/]local[\\/]root\.crt$' } |
        Select-Object -First 1
    if ($rootCert) { break }
}
if (-not $rootCert) {
    throw "O Caddy foi iniciado, mas o certificado público root.crt ainda não foi localizado em '$dataHome'. Consulte o Agendador de Tarefas e execute novamente após corrigir o Caddy."
}

Write-Step "Gerando o pacote PÚBLICO de confiança para as estações"
if (Test-Path -LiteralPath $DistribRoot) { Remove-Item -LiteralPath $DistribRoot -Recurse -Force }
New-Item -ItemType Directory -Path $DistribRoot -Force | Out-Null
$publicRoot = Join-Path $DistribRoot "ICC_Portal_ROOT_CA.crt"
Copy-Item -LiteralPath $rootCert.FullName -Destination $publicRoot -Force
$sha256 = Get-CertificateSha256 $publicRoot
@(
    "Autoridade HTTPS pública do Portal ICC",
    "Servidor: https://$PortalIP/",
    "SHA256 do certificado (DER): $sha256",
    "Gerado em: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))",
    "IMPORTANTE: este pacote contém somente o certificado público. Nunca copie root.key ou qualquer chave privada do Caddy."
) | Set-Content -LiteralPath (Join-Path $DistribRoot "IMPRESSAO_DIGITAL_SHA256.txt") -Encoding UTF8

foreach ($name in @("INSTALAR_CONFIANCA_ESTACAO.ps1", "CONFIGURAR_CONFIANCA_ESTACAO.bat", "TESTAR_ESTACAO.ps1")) {
    $source = Join-Path $PSScriptRoot $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination (Join-Path $DistribRoot $name) -Force }
}

Write-Step "Conferência final"
$httpsListening = (Test-NetConnection -ComputerName 127.0.0.1 -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded
$backendLocal = (Test-NetConnection -ComputerName 127.0.0.1 -Port $BackendPort -WarningAction SilentlyContinue).TcpTestSucceeded
Write-Host "Caddy/443 local: $httpsListening"
Write-Host "Python/$BackendPort local: $backendLocal"
Write-Host "SHA256 da CA: $sha256"
Write-Host "Pacote para as estações: $DistribRoot"

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "CONFIGURAÇÃO PREPARADA" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "1. REINICIE o processo do Portal Python para aplicar eventual bind em 127.0.0.1."
Write-Host "2. No servidor, abra: https://$PortalIP/"
Write-Host "3. Copie SOMENTE a pasta '$DistribRoot' para cada estação."
Write-Host "4. Em cada estação, execute CONFIGURAR_CONFIANCA_ESTACAO.bat e depois TESTAR_ESTACAO.ps1."
Write-Host "5. Entre no módulo $PublicUrl e, como administrador, baixe/configure o Auxiliar ICC."
Write-Host "`nBackup para reversão: $BackupRoot"
