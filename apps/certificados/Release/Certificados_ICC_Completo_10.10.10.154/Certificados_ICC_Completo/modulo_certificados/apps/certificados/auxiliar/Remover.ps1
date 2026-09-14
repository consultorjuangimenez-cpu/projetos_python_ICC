$ErrorActionPreference='Stop'
$key='HKCU:\Software\Classes\icc-cert'
if (Test-Path -LiteralPath $key) { Remove-Item -LiteralPath $key -Recurse -Force }
Write-Host 'Associação do Auxiliar ICC removida deste usuário. Os certificados instalados foram mantidos.'
Write-Host 'A pasta %LOCALAPPDATA%\ICC\AuxiliarCertificados pode ser removida após fechar esta janela.'
