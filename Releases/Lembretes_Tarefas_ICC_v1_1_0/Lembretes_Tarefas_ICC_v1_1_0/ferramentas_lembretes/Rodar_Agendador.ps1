param([switch]$Verificar, [switch]$Diagnosticar, [switch]$DigitarCredencial)
$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $portalRoot '.venv\Scripts\python.exe'
$credentialPath = Join-Path $portalRoot 'dados\apps\lembretes_tarefas\smtp_credencial.xml'
$workerExitCode = 1
$inheritedPasswordPresent = ![string]::IsNullOrEmpty($env:PORTAL_SMTP_SENHA)
$inheritedUserPresent = ![string]::IsNullOrEmpty($env:PORTAL_SMTP_USUARIO)
$passwordDiffers = $false
$userDiffers = $false
try {
    if (!(Test-Path -LiteralPath $pythonExe)) { throw 'Python do portal nao encontrado.' }
    if ($Verificar -and $Diagnosticar) { throw 'Selecione verificacao local ou diagnostico SMTP.' }
    if ($DigitarCredencial -and !$Diagnosticar) { throw 'Digitacao de credencial disponivel somente no diagnostico, sem envio de mensagem.' }
    $credentialSource = 'AMBIENTE'
    $credentialDate = 'Nao utilizado'
    if ($DigitarCredencial) {
        $smtpCredential = Get-Credential -UserName 'ti@icccontabilidade.com.br' -Message 'Teste de autenticacao SMTP. A senha nao sera salva e nenhum e-mail sera enviado.'
        if ($null -eq $smtpCredential) { throw 'Diagnostico cancelado.' }
        $credentialSource = 'DIGITADA_NESTE_TESTE'
    } elseif (Test-Path -LiteralPath $credentialPath) {
        # Correcao R1: o par usuario/senha do XML tem prioridade integral.
        # Uma variavel antiga usada por outro aplicativo nao pode substituir
        # apenas parte do par ou impedir a leitura da credencial configurada.
        try {
            $smtpCredential = Import-Clixml -LiteralPath $credentialPath
        } catch {
            throw 'Nao foi possivel abrir a credencial. Use a mesma conta Windows e o mesmo servidor que executaram CONFIGURAR_SMTP.bat.'
        }
        if ($smtpCredential -isnot [System.Management.Automation.PSCredential]) {
            throw 'O XML nao contem uma credencial valida. Execute CONFIGURAR_SMTP.bat novamente.'
        }
        $credentialSource = 'XML_CONFIGURAR_SMTP'
        $credentialDate = (Get-Item -LiteralPath $credentialPath).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    }
    if ($null -ne $smtpCredential) {
        $loadedPassword = $smtpCredential.GetNetworkCredential().Password
        $loadedUser = $smtpCredential.UserName.Trim()
        if ([string]::IsNullOrEmpty($loadedPassword) -or [string]::IsNullOrEmpty($loadedUser)) {
            throw 'A credencial esta sem usuario ou senha. Execute CONFIGURAR_SMTP.bat novamente.'
        }
        $passwordDiffers = $inheritedPasswordPresent -and ($env:PORTAL_SMTP_SENHA -cne $loadedPassword)
        $userDiffers = $inheritedUserPresent -and ($env:PORTAL_SMTP_USUARIO.Trim() -cne $loadedUser)
        # Modifica somente este processo e seu filho Python, sem escrever
        # variaveis persistentes de Usuario/Maquina ou alterar outros apps.
        $env:PORTAL_SMTP_USUARIO = $loadedUser
        $env:PORTAL_SMTP_SENHA = $loadedPassword
    }
    $env:PYTHONUTF8 = '1'
    Set-Location -LiteralPath $portalRoot
    if ($Diagnosticar) {
        $env:LEMBRETES_DIAG_ORIGEM = $credentialSource
        $env:LEMBRETES_DIAG_CONTA_WINDOWS = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $env:LEMBRETES_DIAG_DATA_XML = $credentialDate
        $env:LEMBRETES_DIAG_SENHA_AMBIENTE_PRESENTE = [string]$inheritedPasswordPresent
        $env:LEMBRETES_DIAG_USUARIO_AMBIENTE_PRESENTE = [string]$inheritedUserPresent
        $env:LEMBRETES_DIAG_SENHA_AMBIENTE_DIFERENTE = [string]$passwordDiffers
        $env:LEMBRETES_DIAG_USUARIO_AMBIENTE_DIFERENTE = [string]$userDiffers
        try {
            $task = Get-ScheduledTask -TaskName 'ICC_Lembretes_Tarefas' -ErrorAction Stop
            $env:LEMBRETES_DIAG_TAREFA_ESTADO = [string]$task.State
            $env:LEMBRETES_DIAG_TAREFA_CONTA = [string]$task.Principal.UserId
        } catch {
            $env:LEMBRETES_DIAG_TAREFA_ESTADO = 'Nao consultada ou nao instalada'
            $env:LEMBRETES_DIAG_TAREFA_CONTA = ''
        }
        & $pythonExe (Join-Path $PSScriptRoot 'diagnosticar_smtp.py')
    } elseif ($Verificar) {
        & $pythonExe -m apps.lembretes_tarefas.worker --check
    } else {
        Write-Host "Credencial SMTP carregada de: $credentialSource"
        & $pythonExe -m apps.lembretes_tarefas.worker
    }
    $workerExitCode = $LASTEXITCODE
} catch {
    # Nao imprimir o objeto PSCredential, a senha ou traceback de bibliotecas.
    Write-Host ('Falha: ' + $_.Exception.Message) -ForegroundColor Red
    $workerExitCode = 1
} finally {
    Remove-Item Env:\PORTAL_SMTP_SENHA -ErrorAction SilentlyContinue
    $smtpCredential = $null
    $loadedPassword = $null
}
exit $workerExitCode
