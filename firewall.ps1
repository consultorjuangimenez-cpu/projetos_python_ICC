param([switch]$Remover)
$ErrorActionPreference = 'Stop'
try {
    $admin = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Execute o BAT com o botao direito > Executar como administrador.'
    }
    $ruleName = 'ICC-Portal-Python-Piloto'
    if ($Remover) {
        Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Write-Host 'Regra do piloto removida.'
        exit 0
    }
    $pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $pythonPath)) { throw 'Execute primeiro 1_instalar.bat.' }
    Push-Location $PSScriptRoot
    try {
        $portalPort = & $pythonPath -c 'from portal.settings import PORT; print(PORT)'
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao ler config.ini.' }
        $portalPort = [int]$portalPort
    } finally { Pop-Location }
    $existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
    if ($existing) { $existing | Remove-NetFirewallRule }
    New-NetFirewallRule -Name $ruleName -DisplayName 'ICC Portal Python - Piloto interno' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $portalPort -RemoteAddress LocalSubnet -Profile Domain,Private | Out-Null
    Write-Host "Porta $portalPort liberada somente para a sub-rede local, nos perfis Dominio e Privado."
    Write-Host 'Perfis de rede atuais:'
    Get-NetConnectionProfile | Select-Object InterfaceAlias,NetworkCategory | Format-Table
    Write-Host 'Rede Publica nao foi liberada. Nao altere redes desconhecidas para Privada.'
} catch {
    Write-Host "ERRO: $_" -ForegroundColor Red
    exit 1
}
