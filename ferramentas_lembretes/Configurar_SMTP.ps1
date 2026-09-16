$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = Join-Path $portalRoot 'dados\apps\lembretes_tarefas'
try {
    if (!(Test-Path -LiteralPath (Join-Path $portalRoot 'portal\acesso.py'))) { throw 'Execute esta ferramenta na pasta do portal, depois da instalacao do modulo.' }
    New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
    $currentAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    Write-Host "A credencial SMTP sera protegida para a conta Windows: $currentAccount"
    Write-Host 'Use esta mesma conta ao instalar o agendador. Nao e a senha de login do Windows.'
    $smtpCredential = Get-Credential -UserName 'ti@icccontabilidade.com.br' -Message 'Informe a conta e a senha do e-mail de envio.'
    if ($null -eq $smtpCredential) { throw 'Configuracao cancelada.' }
    $credentialPath = Join-Path $dataRoot 'smtp_credencial.xml'
    $smtpCredential | Export-Clixml -LiteralPath $credentialPath
    # DPAPI vincula o segredo ao usuario e a esta maquina; ACL restringe o arquivo.
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $ownerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    foreach ($sid in @($ownerSid, (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-18')), (New-Object System.Security.Principal.SecurityIdentifier('S-1-5-32-544')))) {
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $credentialPath -AclObject $acl
    [System.IO.File]::WriteAllText((Join-Path $dataRoot 'conta_agendador.txt'), $currentAccount, [System.Text.Encoding]::UTF8)
    Write-Host 'Credencial SMTP salva com criptografia do Windows.' -ForegroundColor Green
    Write-Host 'Servidor, porta e SSL/STARTTLS podem ser ajustados em:'
    Write-Host (Join-Path $dataRoot 'config.ini')
    Write-Host 'Apos alterar a credencial, reinicie o agendador. Nenhum e-mail foi enviado nesta configuracao.'
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
