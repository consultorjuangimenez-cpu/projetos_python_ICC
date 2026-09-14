[CmdletBinding()]
param(
    [string]$Certificado = (Join-Path $PSScriptRoot "ICC_Portal_ROOT_CA.crt"),
    [string]$ArquivoImpressao = (Join-Path $PSScriptRoot "IMPRESSAO_DIGITAL_SHA256.txt")
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Esta etapa precisa ser executada como Administrador porque a confiança HTTPS será instalada para o computador."
    }
}

function Get-Sha256([Security.Cryptography.X509Certificates.X509Certificate2]$Cert) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Cert.RawData))).Replace('-', '') }
    finally { $sha.Dispose() }
}

Assert-Administrator
if (-not (Test-Path -LiteralPath $Certificado)) { throw "Certificado público não encontrado: $Certificado" }
if (-not (Test-Path -LiteralPath $ArquivoImpressao)) { throw "Arquivo de impressão digital não encontrado: $ArquivoImpressao" }

$expectedText = Get-Content -LiteralPath $ArquivoImpressao -Raw -Encoding UTF8
$match = [regex]::Match($expectedText, 'SHA256 do certificado \(DER\):\s*([A-Fa-f0-9]{64})')
if (-not $match.Success) { throw "Não foi possível obter o SHA256 esperado em IMPRESSAO_DIGITAL_SHA256.txt." }
$expected = $match.Groups[1].Value.ToUpperInvariant()

$cert = New-Object Security.Cryptography.X509Certificates.X509Certificate2($Certificado)
try {
    if ($cert.HasPrivateKey) { throw "RECUSADO: o arquivo recebido contém chave privada. Use somente o root.crt público exportado pelo servidor." }

    $basic = $null
    foreach ($extension in $cert.Extensions) {
        if ($extension.Oid.Value -eq '2.5.29.19') {
            $basic = New-Object Security.Cryptography.X509Certificates.X509BasicConstraintsExtension($extension, $extension.Critical)
            break
        }
    }
    if (-not $basic -or -not $basic.CertificateAuthority) { throw "RECUSADO: o certificado não está identificado como autoridade certificadora (CA)." }

    $actual = Get-Sha256 $cert
    if ($actual -ne $expected) {
        throw "RECUSADO: impressão digital SHA256 diferente. Esperado: $expected | Recebido: $actual"
    }

    Write-Host "Autoridade HTTPS conferida:" -ForegroundColor Green
    Write-Host "  Subject:  $($cert.Subject)"
    Write-Host "  Emissor:   $($cert.Issuer)"
    Write-Host "  Validade:  $($cert.NotBefore) até $($cert.NotAfter)"
    Write-Host "  SHA256:    $actual"

    Import-Certificate -FilePath $Certificado -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
    Write-Host "`nConfiança HTTPS instalada em Cert:\LocalMachine\Root." -ForegroundColor Green
    Write-Host "Feche e abra novamente o navegador antes de testar o portal."
} finally {
    $cert.Dispose()
}
