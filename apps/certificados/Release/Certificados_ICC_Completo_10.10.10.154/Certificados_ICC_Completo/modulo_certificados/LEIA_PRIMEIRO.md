# Certificados digitais ICC

Módulo para o Portal_Apps existente. Entrada no menu: **Certificados digitais**. Rota: `/certificados/`.

Inclui painel HTML, indicadores, gráficos, filtros, exportação Excel e auxiliar para instalar certificados A1 no usuário do Windows que acessou o painel. Não exige Python nas estações. O código de leitura de nome, senha e documento foi adaptado do `monitora.py` enviado.

## 1. Adicionar ao portal

1. Extraia este ZIP em uma pasta separada do portal, por exemplo `C:\C\Atualizacoes\Certificados_Portal_ICC`.
2. Feche a janela que executa `servidor.py`. Confirme que não há outra instância do portal em execução.
3. Execute `INSTALAR_NO_PORTAL.bat` e informe a pasta do portal. O padrão é `C:\C\Projetos_Phyton\Portal_Apps`.
4. Reinicie o portal pelo BAT habitual. Não execute o `app.py` do módulo isoladamente.
5. Entre como administrador, abra **Gerenciar usuários** e libere **Certificados digitais** para os responsáveis.
6. Abra a nova entrada no menu ou acesse `http://IP_DO_SERVIDOR:8080/certificados/` usando o IP real do servidor.

O instalador copia somente `apps\certificados`, acrescenta a entrada no `aplicativos.json` e cria a seção `[certificados_painel]` em `config_apps.ini`. Não substitui os módulos anteriores. A entrada antiga “Validade dos Certificados” é mantida. Antes de cada alteração, cria backup em `backups_atualizacao\certificados_DATA_HORA`.

O instalador usa `.venv\Scripts\python.exe` do próprio portal. Se não houver `.venv`, execute `instalar_no_portal.py` com o mesmo Python que executa o portal:

```powershell
python "C:\C\Atualizacoes\Certificados_Portal_ICC\instalar_no_portal.py" "C:\C\Projetos_Phyton\Portal_Apps"
```

As bibliotecas já constam no pacote de referência do portal. Se o BAT informar falta de dependências, use o Python do portal para instalar `requirements_certificados.txt`. O instalador não atualiza outras bibliotecas automaticamente.

## 2. Conferir os caminhos

A configuração lê `config.ini` e depois `config_apps.ini`, com preferência pelo segundo. Por padrão, herda `pasta_cpf` e `pasta_cnpj` da seção `[monitora_certificados]`. Para definir caminhos próprios, edite a seção criada em `config_apps.ini`:

```ini
[certificados_painel]
pasta_cpf = A:\CERTIFICADOS\Certificados CPF
pasta_cnpj = A:\CERTIFICADOS\Certificados CNPJ
estado_legado = C:\C\Projetos_Phyton\Certificados Digitais\Monitora Certificados\estado_certificados.json
planilha_correcoes = \\srvprosoft\g\programas\Relatorio_Certificados.xlsx
dias_proximo = 30
intervalo_segundos = 300
recursivo = false
url_publica =
```

Edite a seção existente. Não cole uma segunda seção com o mesmo nome. Reinicie o portal depois de mudar a configuração.

- Os caminhos são vistos pela conta do Windows que executa o portal. Uma unidade `A:` disponível no seu Explorer pode estar ausente para uma conta de serviço. Nesse caso, use o compartilhamento UNC real e conceda acesso à conta do portal.
- `estado_legado`: usa as senhas conhecidas no JSON original. O JSON não é tratado como uma lista de arquivos existentes e não é alterado.
- `planilha_correcoes`: lê a coluna `SENHA CORRIGIDA`, localizando o cabeçalho nas primeiras 15 linhas. Não altera essa planilha.
- `recursivo = false`: lê os arquivos diretamente nas duas pastas, como o script original. Use `true` para incluir subpastas.
- O arquivo JSON anexado contém senhas. Ele não foi embutido neste pacote. Use o arquivo existente no servidor ou aponte `estado_legado` para a cópia correta.

## 3. O que o painel faz

| Recurso | Comportamento |
|---|---|
| Indicadores | Total, válidos, próximos do vencimento e vencidos, além das falhas de leitura. Certificados ainda não vigentes aparecem na legenda e no filtro. |
| Gráficos | Distribuição por situação e vencimentos nos próximos seis meses. Clique na legenda ou em um mês para filtrar. |
| Filtros | Cliente, CPF/CNPJ, tipo, situação, intervalo de vencimento, origem da senha e prazo restante. Aceita documento com ou sem pontuação e busca de nome sem acentos. |
| Listagem | Paginação, ordenação e detalhes. Cada linha corresponde a um arquivo encontrado. Arquivos diferentes com o mesmo certificado continuam sendo arquivos distintos. |
| Excel | Exporta somente os registros filtrados, com resumo, cores, largura de colunas, filtro e cabeçalho fixo. Não inclui senhas. |
| Correção de senha | A TI informa a senha nos detalhes. O certificado é aberto e validado antes de salvar. Exige HTTPS. |
| Atualização | Ao abrir o painel e, enquanto estiver em uso, em intervalos de cinco minutos. Também há atualização manual. A primeira leitura abre cada PFX; as seguintes reaproveitam os arquivos válidos sem alteração. |
| Pastas indisponíveis | Mostra aviso. Registros não encontrados na leitura atual não são publicados como se estivessem presentes. Durante a varredura, a lista pode estar parcial e isso é indicado na tela. |

Prioridade das senhas: correção salva no painel, correção da planilha/legado, senha manual previamente validada, senha extraída do nome e, quando o nome não informa senha, a senha de sucesso do estado legado. Uma alteração manual deve ser feita nos detalhes se o arquivo tiver sido renovado com outra senha. A senha do painel não é sobrescrita pelo relatório antigo.

A validade é comparada com a hora UTC real do certificado. “Próximo do vencimento” inclui o prazo de até 30 dias, configurável. “Válido” corresponde aos certificados acima desse prazo. Certificados ainda não vigentes, vencidos ou sem chave privada válida não podem ser instalados. A consulta não verifica revogação via CRL/OCSP.

As datas do painel usam o fuso do computador do usuário. O Excel identifica suas datas como UTC. A quantidade de dias usa arredondamento para cima enquanto o certificado está vigente.

## 4. Habilitar o botão INSTALAR

**O servidor sozinho não pode instalar no computador de quem abriu a página.** O botão aciona o **Auxiliar ICC** no Windows do usuário por meio do protocolo `icc-cert://`.

O painel funciona em HTTP para consulta. A instalação, a entrega do auxiliar configurado e o envio de senha corrigida exigem HTTPS, com certificado TLS confiável nas estações. O certificado TLS do portal é diferente dos certificados A1 dos clientes.

### No servidor, uma vez

1. Disponibilize o portal por um endereço HTTPS com nome e certificado TLS válidos, usando o proxy da empresa ou configurando um proxy local.
2. Em `config_apps.ini`, preencha `url_publica` com o endereço completo **deste módulo**, por exemplo `https://portal.icccontabilidade.com.br/certificados`. O domínio é apenas exemplo; não foi configurado por este pacote.
3. O Python deve reconhecer que a requisição veio por HTTPS. Não basta escrever `https` no INI. Se o proxy for local, o arquivo opcional `iniciar_atras_proxy_https.py` fornece a inicialização do Waitress em `127.0.0.1:8081`, aceitando os cabeçalhos HTTPS somente do proxy em `127.0.0.1`.
4. Quando todos passarem a usar HTTPS, configure `[seguranca]` com `cookie_https = true` no `config.ini`. Se a seção já existir, altere somente essa opção.
5. Acesse o módulo pelo endereço HTTPS configurado. Abra **Como instalar** com um administrador e baixe **Auxiliar_Certificados_ICC.zip**.

Veja `HTTPS_E_VALIDACAO.md` para os detalhes do proxy e do teste em uma estação.

### Nas estações, uma vez por usuário do Windows

1. A TI entrega o ZIP do auxiliar configurado pelo próprio painel.
2. Se o Windows mostrar “Desbloquear” nas propriedades do ZIP baixado, a TI deve conferir a procedência, desbloquear o arquivo e então extraí-lo. Scripts sujeitos a assinatura obrigatória pela política da empresa precisam ser assinados pela TI; o pacote não altera essa política.
3. Com o usuário que realmente utilizará os certificados conectado, execute `CONFIGURAR_AUXILIAR.bat`. Não execute como outro usuário/administrador.
4. O auxiliar fica em `%LOCALAPPDATA%\ICC\AuxiliarCertificados`. Não permanece executando em segundo plano nem abre uma porta local.

### Em cada instalação

1. Usuário autenticado clica em **INSTALAR**.
2. O navegador solicita abrir o Auxiliar ICC, conforme sua configuração.
3. O auxiliar recebe somente o certificado solicitado, confere sua identificação, validade e chave privada, e mostra o cliente para confirmação.
4. Após a confirmação, instala no repositório **Usuário Atual > Pessoal > Certificados**.
5. O auxiliar confere a presença da chave privada no repositório e devolve o resultado ao painel. Se o certificado já estiver instalado nesse perfil, informa isso sem duplicá-lo.

O auxiliar usa Windows PowerShell 5.1 e .NET Framework com suporte a `EphemeralKeySet` (4.7.2 ou superior). Não use PowerShell 7 para executar diretamente este auxiliar. A cadeia da autoridade certificadora deve estar confiável no Windows; o auxiliar não instala raízes de confiança. Compatibilidade com certificados A1 reais, políticas do domínio e sistemas que usarão a chave deve ser validada no piloto.

A3 em token/cartão está fora deste módulo: não existe um PFX transferível para instalar dessa forma.

## 5. Acesso e dados

A permissão **Certificados digitais** permite consultar e solicitar a instalação de todos os certificados das pastas configuradas. Não há divisão por cliente dentro do módulo. Conceda essa permissão somente a usuários autorizados a usar esses certificados.

O módulo mantém a autenticação e o CSRF do portal. Os caminhos e nomes originais de arquivo ficam nos detalhes exclusivos da TI, pois os nomes podem conter senhas. Usuários comuns veem um identificador seguro do arquivo. Senhas não são mostradas no painel nem na exportação.

As senhas conhecidas e corrigidas são cifradas no índice local. A chave `segredo.key` fica junto do banco. Proteja `dados\apps\certificados` com ACL NTFS para a conta do portal e a TI; copiar banco e chave juntos permite decifrar as senhas. A criptografia não substitui permissões de pasta. Não exponha `dados` como pasta estática na web.

O canal `/certificados/agente-api` aceita apenas solicitações de uso único emitidas após login e CSRF. A entrega exige HTTPS e revalida a sessão e a permissão atuais. O token vence em três minutos e o retorno do auxiliar em dez minutos. O banco registra solicitação, usuário, identificação do certificado, resultado informado pelo auxiliar e computador informado por ele. O nome do computador é um dado informado pelo cliente, não uma autenticação do equipamento.

O auxiliar importa a chave sem solicitar que seja exportável. Não cria uma cópia temporária do PFX em disco. Quem está autorizado a usar uma chave no próprio perfil do Windows deve ser tratado como usuário autorizado do certificado.

## 6. Arquivos e manutenção

| Caminho | Função |
|---|---|
| `INSTALAR_NO_PORTAL.bat` | Instala o módulo usando o Python do portal. |
| `instalar_no_portal.py` | Copia módulo, faz backup, preserva cadastro e configuração. |
| `apps/certificados/app.py` | Rotas HTML, API, exportação e solicitações de instalação. |
| `apps/certificados/core.py` | Varredura, cache, criptografia de senha e leitura de PFX/P12. |
| `apps/certificados/leitura_original.py` | Funções de extração preservadas do script fornecido. |
| `apps/certificados/templates` e `static` | Tela, estilos, JavaScript e gráficos sem dependências externas. |
| `apps/certificados/auxiliar` | Código completo do auxiliar Windows. O ZIP pronto é gerado pelo painel após a configuração HTTPS. |
| `dados/apps/certificados` no portal | Banco `inventario.sqlite3` e `segredo.key`, criados na instalação/execução. Não excluir a chave. |
| `iniciar_atras_proxy_https.py` | Inicialização opcional do portal atrás de proxy HTTPS local. Não é copiada automaticamente. |
| `tests` | Testes com certificados artificiais, sem dados de clientes. |

A aplicação original e seu JSON não são modificados. O relatório em rede continua sob responsabilidade do script original; este módulo fornece a exportação filtrada por download.

Para desfazer a inclusão: pare o portal, restaure `aplicativos.json` e `config_apps.ini` do backup feito pelo instalador e remova somente `apps\certificados` se era uma nova instalação. Se o módulo já existia, restaure também a pasta `certificados` do backup. Mantenha os dados até confirmar que não serão necessários. Nas estações, execute `Remover.ps1` para remover a associação do auxiliar; os certificados já instalados são mantidos.
