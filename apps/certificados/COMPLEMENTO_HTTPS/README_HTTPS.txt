PORTAL ICC - COMPLEMENTO HTTPS / CADDY
=====================================

OBJETIVO
- Portal público interno: https://10.10.10.154/
- Backend Python: somente em 127.0.0.1:8080 / protegido da rede privada
- Módulo de certificados: URL detectada automaticamente no aplicativos.json
- Botão INSTALAR: habilitado apenas pelo HTTPS esperado
- Confiança nas estações: somente o certificado PÚBLICO da CA interna é distribuído

ANTES DE EXECUTAR
1. Substitua a pasta do módulo "certificados" pela versão deste pacote.
2. Confirme que o módulo está cadastrado no aplicativos.json, por exemplo:
   rota: /certificados
   modulo: apps.certificados.app
3. Baixe o caddy.exe oficial para Windows em:
   https://caddyserver.com/download
4. Coloque caddy.exe dentro da pasta COMPLEMENTO_HTTPS.
5. Abra PowerShell COMO ADMINISTRADOR.

INSTALAÇÃO NO SERVIDOR
Execute:

  Set-ExecutionPolicy -Scope Process Bypass
  .\INSTALAR_HTTPS_PORTAL.ps1 -PortalRoot "C:\C\Projetos_Phyton\Portal_Apps"

Se a sua pasta for diferente, informe o caminho real.
Se o módulo ainda não estiver no catalogo, é possível informar a rota explicitamente:

  .\INSTALAR_HTTPS_PORTAL.ps1 -PortalRoot "C:\caminho\Portal_Apps" -RotaCertificados "/certificados"

O SCRIPT FAZ
1. Cria backup_https_AAAAMMDD_HHMMSS antes de alterar arquivos.
2. Detecta a rota do módulo no aplicativos.json.
3. Grava em config_apps.ini:
   [certificados_painel]
   url_publica = https://10.10.10.154/<rota>
4. Tenta restringir o host do backend para 127.0.0.1 quando reconhece a inicialização.
5. Cria regra de firewall bloqueando acesso privado direto à porta 8080.
6. Libera 80/443 para o Caddy.
7. Valida o Caddyfile antes de registrar a tarefa.
8. Registra o Caddy como tarefa SYSTEM iniciada com o Windows.
9. Exporta SOMENTE root.crt, o certificado público da CA interna.
10. Calcula a impressão digital SHA256 do certificado público.
11. Gera a pasta "distribuicao_https" na raiz do Portal.

IMPORTANTE
- REINICIE o processo Python do Portal depois da instalação.
- NÃO distribua a pasta C:\ProgramData\ICC\Caddy.
- NÃO copie root.key, intermediate.key ou qualquer arquivo de chave privada.
- Para as estações, copie SOMENTE a pasta "distribuicao_https".

CONFIGURAÇÃO EM CADA ESTAÇÃO
1. Copie a pasta "distribuicao_https" para a estação.
2. Execute CONFIGURAR_CONFIANCA_ESTACAO.bat.
3. O instalador verifica:
   - que o arquivo não contém chave privada;
   - que é uma autoridade certificadora;
   - que o SHA256 coincide com IMPRESSAO_DIGITAL_SHA256.txt.
4. Feche e abra o navegador.
5. Execute TESTAR_ESTACAO.ps1.
6. O resultado esperado é:
   HTTPS 443 acessível: True
   Python 8080 direto bloqueado: True
   HTTPS confiável: SIM

AUXILIAR DO BOTÃO INSTALAR
Depois do HTTPS estar funcionando:
1. Entre no Portal como administrador.
2. Abra o módulo Certificados digitais.
3. Clique em "Como instalar".
4. Baixe "Auxiliar configurado".
5. Na estação do usuário, execute CONFIGURAR_AUXILIAR.bat uma vez no perfil dele.
6. Depois disso o botão INSTALAR abre o protocolo icc-cert:// e o certificado A1 é instalado em:
   Usuário Atual > Pessoal

O auxiliar NÃO instala certificado do cliente em Autoridades Raiz Confiáveis.
A única confiança em Root é a CA PÚBLICA do Portal, instalada pela TI uma vez na estação.

REVERTER
Execute como administrador:
  .\REVERTER_ULTIMA_IMPLANTACAO.ps1 -PortalRoot "C:\C\Projetos_Phyton\Portal_Apps"

O script restaura os arquivos do backup mais recente e remove a tarefa/regras criadas por este complemento.
Reinicie o Portal Python depois da reversão.

DOCUMENTAÇÃO OFICIAL CADDY
- HTTPS automático: https://caddyserver.com/docs/automatic-https
- Reverse proxy: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- Instalação: https://caddyserver.com/docs/install
