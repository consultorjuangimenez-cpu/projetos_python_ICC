[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^icc-cert://instalar/[A-Za-z0-9_-]{43}/?$')][string]$Uri)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Net.Http
$client = $null
$handler = $null
$payload = $null
$preview = $null
$persisted = $null
$store = $null
$bytes = $null
$securePassword = $null
$resultState = 'falhou'
$callback = ''
$message = ''
$title = 'Certificados digitais ICC'
function Send-Json([string]$Endpoint, [hashtable]$Body) {
    $content = New-Object System.Net.Http.StringContent(($Body | ConvertTo-Json -Compress), [Text.Encoding]::UTF8, 'application/json')
    $response = $null
    try {
        $response = $script:client.PostAsync($script:baseUrl + '/agente-api/' + $Endpoint, $content).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $detail = 'O portal recusou a solicitação. Volte ao painel e tente novamente.'
            try { $errorBody = $text | ConvertFrom-Json; if ($errorBody.erro) { $detail = [string]$errorBody.erro } } catch {}
            throw $detail
        }
        return ($text | ConvertFrom-Json)
    } finally {
        if ($response) { $response.Dispose() }
        $content.Dispose()
    }
}
try {
    if ($args.Count -gt 0) { throw 'Parâmetros extras não são aceitos.' }
    $configuration = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $script:baseUrl = ([string]$configuration.url).TrimEnd('/')
    $base = [System.Uri]$script:baseUrl
    if ($base.Scheme -ne 'https' -or -not $base.Host -or $base.UserInfo -or $base.Query -or $base.Fragment) {
        throw 'Endereço HTTPS do portal não configurado. Solicite a configuração à TI.'
    }
    # O URI recebido só contém um token. Servidor e caminho vêm da configuração feita pela TI.
    $token = $Uri.TrimEnd('/').Substring('icc-cert://instalar/'.Length)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $script:client = New-Object System.Net.Http.HttpClient($handler)
    $script:client.Timeout = [TimeSpan]::FromSeconds(30)
    $script:client.MaxResponseContentBufferSize = 16MB
    $payload = Send-Json 'resgatar' @{ token=$token; maquina=$env:COMPUTERNAME }
    $callback = [string]$payload.callback
    if ([string]$payload.pfx -eq '' -or ([string]$payload.pfx).Length -gt (14 * 1024 * 1024)) { throw 'Pacote de certificado inválido.' }
    if ([string]$payload.thumbprint -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Impressão digital inválida.' }
    $bytes = [Convert]::FromBase64String([string]$payload.pfx)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-','').ToLowerInvariant() } finally { $hasher.Dispose() }
    if ($hash -ne ([string]$payload.sha256).ToLowerInvariant()) { throw 'O arquivo recebido não corresponde ao certificado solicitado.' }
    $securePassword = New-Object Security.SecureString
    foreach ($character in ([string]$payload.senha).ToCharArray()) { $securePassword.AppendChar($character) }
    $securePassword.MakeReadOnly()
    $payload.senha = $null
    # Leitura temporária sem persistir a chave antes da confirmação.
    $preview = New-Object Security.Cryptography.X509Certificates.X509Certificate2
    $preview.Import($bytes, $securePassword, [Security.Cryptography.X509Certificates.X509KeyStorageFlags]::EphemeralKeySet)
    if (-not $preview.HasPrivateKey -or $preview.Thumbprint -ne [string]$payload.thumbprint) { throw 'Chave privada ou identificação do certificado inválida.' }
    if ($preview.NotAfter.ToUniversalTime() -lt [DateTime]::UtcNow -or $preview.NotBefore.ToUniversalTime() -gt [DateTime]::UtcNow) { throw 'Este certificado não está vigente.' }
    $store = New-Object Security.Cryptography.X509Certificates.X509Store('My','CurrentUser')
    $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $existing = $store.Certificates.Find([Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $preview.Thumbprint, $false)
    $hasExisting = @($existing | Where-Object { $_.HasPrivateKey }).Count -gt 0
    if ($hasExisting) {
        $resultState = 'ja_instalado'
        $message = 'Este certificado já está instalado no seu perfil do Windows.'
    } else {
        $prompt = "Instalar o certificado abaixo no seu perfil do Windows?`r`n`r`nCliente: $($payload.cliente)`r`nCPF/CNPJ: $($payload.documento)`r`nValidade: $($preview.NotAfter.ToString('dd/MM/yyyy HH:mm'))`r`n`r`nUsuário: $env:USERDOMAIN\$env:USERNAME`r`nComputador: $env:COMPUTERNAME"
        $answer = [Windows.Forms.MessageBox]::Show($prompt, $title, [Windows.Forms.MessageBoxButtons]::YesNo, [Windows.Forms.MessageBoxIcon]::Question, [Windows.Forms.MessageBoxDefaultButton]::Button2)
        if ($answer -ne [Windows.Forms.DialogResult]::Yes) {
            $resultState = 'cancelado'
            $message = 'Instalação cancelada. Nenhum certificado foi adicionado.'
        } else {
            # Só o certificado com chave privada é adicionado a Pessoal/Usuário Atual.
            # Não importa raízes de confiança. Não solicita chave exportável.
            $flags = [Security.Cryptography.X509Certificates.X509KeyStorageFlags]::UserKeySet -bor [Security.Cryptography.X509Certificates.X509KeyStorageFlags]::PersistKeySet
            $persisted = New-Object Security.Cryptography.X509Certificates.X509Certificate2
            $persisted.Import($bytes, $securePassword, $flags)
            if (-not $persisted.HasPrivateKey -or $persisted.Thumbprint -ne $preview.Thumbprint) { throw 'Falha na conferência antes de adicionar ao Windows.' }
            $store.Add($persisted)
            $check = $store.Certificates.Find([Security.Cryptography.X509Certificates.X509FindType]::FindByThumbprint, $preview.Thumbprint, $false)
            if (@($check | Where-Object { $_.HasPrivateKey }).Count -eq 0) { throw 'O Windows não confirmou a instalação da chave privada.' }
            $resultState = 'instalado'
            $message = "Certificado instalado com sucesso no seu perfil do Windows.`r`n`r`nCliente: $($payload.cliente)`r`nDestino: Usuário Atual > Pessoal > Certificados"
        }
    }
} catch {
    $message = "Não foi possível concluir a instalação.`r`n`r`n$($_.Exception.Message)`r`n`r`nVolte ao painel e solicite ajuda à TI se o problema continuar."
} finally {
    if ($callback -and $script:client) {
        try { $null = Send-Json 'resultado' @{ callback=$callback; estado=$resultState } }
        catch { $message += "`r`n`r`nO resultado não pôde ser enviado ao painel. Confira o certificado no Windows antes de repetir." }
    }
    if ($store) { $store.Close() }
    if ($preview) { $preview.Dispose() }
    if ($persisted) { $persisted.Dispose() }
    if ($securePassword) { $securePassword.Dispose() }
    if ($bytes) { [Array]::Clear($bytes,0,$bytes.Length) }
    $payload=$null
    if ($script:client) { $script:client.Dispose() }
    if ($handler) { $handler.Dispose() }
}
$icon = if ($resultState -in @('instalado','ja_instalado','cancelado')) { [Windows.Forms.MessageBoxIcon]::Information } else { [Windows.Forms.MessageBoxIcon]::Error }
[void][Windows.Forms.MessageBox]::Show($message,$title,[Windows.Forms.MessageBoxButtons]::OK,$icon)
