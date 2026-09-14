[CmdletBinding()]
param(
    [string]$PortalIP = "10.10.10.154",
    [int]$BackendPort = 8080
)

$ErrorActionPreference = 'Continue'
Write-Host "Teste da estação para o Portal ICC" -ForegroundColor Cyan
Write-Host "==================================="

$https = Test-NetConnection -ComputerName $PortalIP -Port 443 -WarningAction SilentlyContinue
$backend = Test-NetConnection -ComputerName $PortalIP -Port $BackendPort -WarningAction SilentlyContinue

Write-Host "HTTPS 443 acessível: $($https.TcpTestSucceeded)"
Write-Host "Python $BackendPort direto bloqueado: $(-not $backend.TcpTestSucceeded)"

try {
    $response = Invoke-WebRequest -Uri "https://$PortalIP/" -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 15 -ErrorAction Stop
    Write-Host "HTTPS confiável: SIM | HTTP $($response.StatusCode)" -ForegroundColor Green
} catch {
    $status = $null
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    if ($status -in 301,302,303,307,308,401,403) {
        Write-Host "HTTPS confiável: SIM | resposta HTTP $status (esperada dependendo do login)." -ForegroundColor Green
    } else {
        Write-Host "HTTPS confiável: NÃO confirmado." -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
}

if ($https.TcpTestSucceeded -and -not $backend.TcpTestSucceeded) {
    Write-Host "`nCamada de rede: OK. A estação chega somente ao proxy HTTPS." -ForegroundColor Green
} else {
    Write-Warning "Revise firewall/Caddy. O esperado é 443=True e $BackendPort=False."
}
