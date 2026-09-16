$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$taskName = 'ICC_Lembretes_Tarefas'
try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    if (!$principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Feche esta janela e execute INSTALAR_AGENDADOR.bat com o botao direito > Executar como administrador. O Windows exige esse direito para registrar o inicio automatico.'
    }
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        throw 'A tarefa ICC_Lembretes_Tarefas ja existe. Consulte ou ajuste pelo Agendador de Tarefas do Windows; ela nao sera substituida automaticamente.'
    }
    $accountFile = Join-Path $portalRoot 'dados\apps\lembretes_tarefas\conta_agendador.txt'
    $credentialPath = Join-Path $portalRoot 'dados\apps\lembretes_tarefas\smtp_credencial.xml'
    $windowsAccount = $identity.Name
    if (Test-Path -LiteralPath $accountFile) {
        $windowsAccount = (Get-Content -LiteralPath $accountFile -Raw).Trim()
    }
    if ((Test-Path -LiteralPath $credentialPath) -and $windowsAccount -ne $identity.Name) {
        throw "A credencial SMTP pertence a $windowsAccount. Execute esta ferramenta como essa mesma conta Windows."
    }
    Write-Host 'Informe agora a senha de login do Windows da conta que executara o agendador.'
    Write-Host 'A tarefa funcionara mesmo sem usuario conectado. A senha nao sera gravada nos scripts.'
    $windowsCredential = Get-Credential -UserName $windowsAccount -Message 'Conta Windows do agendador (nao e o e-mail SMTP).'
    if ($null -eq $windowsCredential) { throw 'Configuracao cancelada.' }
    if ($windowsCredential.UserName -ne $windowsAccount) { throw 'Use exatamente a conta Windows indicada, para preservar o acesso a credencial SMTP.' }
    $runner = Join-Path $PSScriptRoot 'Rodar_Agendador.ps1'
    $powershellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $runner + '"'
    $action = New-ScheduledTaskAction -Execute $powershellExe -Argument $arguments -WorkingDirectory $portalRoot
    $boot = New-ScheduledTaskTrigger -AtStartup
    $watchdog = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 2)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $windowsPassword = $windowsCredential.GetNetworkCredential().Password
    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($boot, $watchdog) -Settings $settings -User $windowsCredential.UserName -Password $windowsPassword -RunLevel Limited -Description 'Lembretes ICC: worker independente, inicio automatico, fila SQLite e controle de concorrencia.' | Out-Null
    } finally {
        $windowsPassword = $null
        $windowsCredential = $null
    }
    Start-ScheduledTask -TaskName $taskName
    Write-Host 'Agendador registrado e inicio solicitado.' -ForegroundColor Green
    Write-Host 'Abra Lembretes no portal e confira o indicador Agendador ativo. Depois use Teste de e-mail.'
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
