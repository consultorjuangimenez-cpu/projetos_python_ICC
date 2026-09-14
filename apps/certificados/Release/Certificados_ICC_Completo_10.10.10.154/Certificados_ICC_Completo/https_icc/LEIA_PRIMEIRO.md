# HTTPS interno do Portal ICC: 10.10.10.154

Este complemento prepara o portal em **https://10.10.10.154/** e o painel em **https://10.10.10.154/certificados/**. Não ativa acesso pela internet e não altera o roteador.

Pré-requisito: instale primeiro o módulo do pacote `Certificados_Portal_ICC.zip` enviado anteriormente. O complemento usa a mesma `.venv`, os mesmos aplicativos e o login existente.

## 1. Preparar a pasta e o Caddy

1. Extraia a pasta `https_icc` deste ZIP dentro de `C:\C\Projetos_Phyton\Portal_Apps`. O resultado deve ser `C:\C\Projetos_Phyton\Portal_Apps\https_icc\https_icc.py`.
2. Baixe o **Caddy para Windows amd64**, sem plugins adicionais, em [Download oficial do Caddy](https://caddyserver.com/download).
3. Salve o executável com o nome `caddy.exe` dentro de `Portal_Apps\https_icc`. O executável não está incluído neste ZIP.
4. Reserve o IP **10.10.10.154** para este computador no DHCP, ou confirme que já é fixo. Uma mudança do IP exigirá reconfiguração.

## 2. Fazer a mudança para HTTPS

Faça esta etapa em uma janela de manutenção do portal:

1. Encerre a instância atual do portal na porta 8080.
2. Execute `https_icc\1_CONFIGURAR_HTTPS.bat`. Ele valida a configuração com o Caddy, faz backup de `config.ini` e `config_apps.ini` e altera somente:
   - `[seguranca] cookie_https = true`, no `config.ini`;
   - `[certificados_painel] url_publica = https://10.10.10.154/certificados`, no `config_apps.ini`.
3. No PowerShell **como administrador do servidor**, crie a regra de entrada da rede interna, se ainda não existir:

```powershell
if (-not (Get-NetFirewallRule -Name 'ICC-Portal-HTTPS' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'ICC-Portal-HTTPS' `
        -DisplayName 'ICC Portal HTTPS - Rede interna' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 443 `
        -LocalAddress 10.10.10.154 -RemoteAddress LocalSubnet `
        -Profile Domain,Private
}
```

A regra atende à sub-rede local em perfil Domínio ou Privado. Se as estações estiverem em outra VLAN/sub-rede, a TI deve usar os CIDRs reais autorizados em `RemoteAddress`. Não é necessário abrir a porta 8081 para outras máquinas.

4. Execute `https_icc\2_INICIAR_HTTPS.bat`, usando a mesma conta que já acessa as pastas do portal. Mantenha a janela aberta.
5. Daqui em diante, use esse BAT para iniciar o portal. Ele inicia o Python em `127.0.0.1:8081` e o Caddy em `10.10.10.154:443`. Se um falhar, encerra o outro e informa a pasta de logs. Não execute simultaneamente o BAT antigo da porta 8080.

O complemento não cria serviço do Windows nem inicialização automática. Os arquivos originais `servidor.py` e `portal/servidor.py` são mantidos. CTRL+C na janela encerra os dois processos iniciados pelo complemento.

## 3. Preparar as estações com um BAT

1. Com o HTTPS executando, execute `3_EXPORTAR_CONFIANCA.bat` em outra janela do servidor.
2. Ele gera `https_icc\distribuir\Preparar_Estacao_ICC.zip`, contendo o certificado público HTTPS, sua identificação, o auxiliar e um BAT único.
3. Entregue esse ZIP aos usuários por um meio controlado pela TI. Não entregue a pasta do servidor.
4. Em cada estação, extraia o ZIP inteiro e execute **INSTALAR_NESTE_COMPUTADOR.bat** com o usuário que usará o portal. Faça também no usuário do servidor.
5. O BAT confere a identificação do certificado, importa a confiança para o usuário atual, registra o Auxiliar ICC e abre o painel.
6. Entre no portal e teste **INSTALAR** com um certificado A1 autorizado. Confira o resultado em `certmgr.msc`, na estação, em **Pessoal > Certificados**.

A configuração é feita uma vez por usuário do Windows, sem instalar Python. Não execute como outro administrador. Políticas do domínio podem exigir intervenção da TI.

O certificado real de confiança só pode ser gerado no servidor. Por isso, o ZIP das estações é produzido depois que o Caddy inicia, usando a autoridade efetivamente criada ali. O BAT verifica o SHA256 embutido; a TI deve conferir a impressão exibida no servidor e a procedência do pacote distribuído.

Importar a raiz significa confiar nessa autoridade HTTPS para o usuário. Proteja `Portal_Apps\dados\caddy_https`, que contém suas chaves privadas, com acesso restrito à conta do portal e à TI. Nunca distribua essa pasta nem arquivos `.key`. O exportador lê somente `root.crt` e exporta o certificado público.

Se o Windows bloquear os scripts baixados, a TI deve conferir a procedência do ZIP e a política de assinatura. Quando aplicável, use a opção **Desbloquear** nas propriedades do ZIP antes de extrair. Políticas que exigem assinatura precisam ser respeitadas.

O auxiliar instala os A1 em **Usuário Atual > Pessoal**; a confiança HTTPS fica em **Usuário Atual > Autoridades de Certificação Raiz Confiáveis**. São finalidades e repositórios diferentes.

## Problemas e reversão

| Sintoma | Verificação |
|---|---|
| “Falta arquivo” no BAT | A pasta precisa se chamar `https_icc` e estar diretamente dentro do portal. Instale primeiro o módulo de certificados. |
| Porta 8080 ocupada | Encerre o portal antigo antes de iniciar o novo. |
| Porta 443 ou 8081 indisponível | Confira se outro serviço ocupa a porta e se o computador ainda usa 10.10.10.154. O complemento não encerra serviços de terceiros. |
| Processo encerrou | Leia os arquivos mais recentes de `https_icc\logs`. Erros de outros módulos do portal precisam ser corrigidos nesses módulos. |
| HTTPS abre no servidor, mas não na estação | Confira firewall, perfil da rede e acesso entre as sub-redes. |
| Aviso de certificado ou auxiliar recusando conexão | Confira a raiz importada no usuário atual e o SHA256. Acesse pelo IP configurado, não por localhost ou outro nome. |
| INSTALAR segue desabilitado | Reinicie após a configuração e acesse exatamente `https://10.10.10.154/certificados/`. Confira a validade do certificado A1 selecionado. |

Para voltar ao modo anterior: encerre `2_INICIAR_HTTPS.bat`, restaure **os dois INIs** do backup `backups_atualizacao\https_DATA_HORA...` e reinicie pelo BAT antigo. Não basta reiniciar o BAT antigo mantendo `cookie_https=true`, pois o navegador não enviará o cookie de login por HTTP.

## Validação e fontes

O código Python foi conferido e a edição dos INIs e a exportação do certificado público foram testadas com dados artificiais. A configuração Caddy é baseada na documentação oficial e será validada por `caddy adapt` no próprio servidor antes de alterar os INIs. A execução dos binários Windows, a confiança TLS, o firewall e a instalação real dos certificados precisam do teste piloto na empresa.

- [Caddy: HTTPS local e confiança da autoridade](https://caddyserver.com/docs/automatic-https#local-https).
- [Caddy: opções globais, armazenamento e controle da instalação de confiança](https://caddyserver.com/docs/caddyfile/options).
- [Caddy: proxy reverso e cabeçalhos](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
- [Waitress: configuração de proxy reverso](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html).
