# Aplicativos e configurações

Os arquivos `config.ini` e `dados/` atuais devem ser preservados na migração.
`config_apps.ini` configura os projetos novos. Alterações exigem reiniciar o portal.

| Aplicativo | Configuração | Funcionamento |
|---|---|---|
| Buscar PDFs | `config.ini`, seção `documentos` | Mantido sem alteração. |
| Planilha Amanda | `config.ini`, seção `amanda` | Mantidos o processamento RCF e o download corrigido. |
| PDFs por CNPJ | `config_apps.ini`, seção `pdf_cnpj` | Busca no texto dos PDFs; o índice é reconstruído na primeira busca e reaproveitado depois. PDFs escaneados sem texto precisam de OCR fora desta versão. |
| Carta Frete | Sem pasta fixa | Envie o PDF pelo navegador. O arquivo Excel é gerado em memória. Há download automático e link manual. |
| Buscar NF-es | Seção `sieg` | A pasta raiz contém subpastas de CPF/CNPJ. A busca reconhece ano e Entrada/Saida em qualquer ordem abaixo da pasta do documento. |
| Emitir Guias | Sem Excel fixo | Envie um XLSX, aba `Plan1`, colunas `CHAVE DE ACESSO` e `VALOR`. Chaves devem ser texto de 44 dígitos. |
| Aberturas e Alterações | Seção `aberturas` | Usa a planilha compartilhada configurada. Configure o remetente e destinos de e-mail antes de enviar. |
| Análise de E-mails | Seção `analise_emails` | Envie os logs CSV. A lista `emails_liberados.csv` e o histórico `Bloqueados/Historico` continuam na pasta configurada. |
| Inventário de Certificados | Seção `analisa_certificados` | Pastas CPF e CNPJ precisam estar acessíveis. Mantém o relatório original e suas regras por data do arquivo. |
| Validade dos Certificados | Seção `monitora_certificados` | Lê PFX/P12, preserva senhas corrigidas e estado, gera dashboard. |

## Emissão de guias

O núcleo de navegação da SEFAZ e as tentativas de recuperação foram mantidos.
O caminho literal `*.xlsx` do app enviado foi substituído por uma planilha enviada
para cada execução. Não há gravação na pasta fixa `F:\Documentos\Marcos\Guias`:
os PDFs ficam na execução e são entregues em ZIP. Baixe-os para a pasta desejada.

O código enviado sempre selecionava CNPJ na SEFAZ, mesmo oferecendo CPF e IE na
tela. A tela integrada oferece somente a modalidade implementada: CNPJ.
Não é correto afirmar que CPF/IE estão implementados sem adaptar o processamento.

São verificados os PDFs que começam com `%PDF`. O resumo indica linhas sem PDF.
Uma falha de captura não comprova que a SEFAZ deixou de emitir a guia. Confira
antes de repetir a execução. Não houve emissão real durante os testes deste pacote.

Instale o Chromium com `5_instalar_navegador_guias.bat`. Se alterar a conta do
Windows que executa o servidor, instale também nessa conta.

## Aberturas e Alterações

A regra do `app.py` enviado foi preservada: gerar o relatório marca `Sim` na
coluna I (Vitória) ou J (Escritório), antes do envio por e-mail. Apenas uma geração
pode atualizar a planilha de cada vez pelo portal. Mantenha o arquivo fechado no
Excel; edição externa simultânea não é um uso suportado.

Antes de atualizar, o portal cria uma cópia em `dados/apps/aberturas/backups/`.
O relatório é exclusivo do usuário, com nome único. A tela permite recuperar os
relatórios anteriores desse usuário. O envio usa um botão de confirmação.

Configure em `config_apps.ini` o servidor SMTP, a porta SSL, o remetente e os
destinatários padrão. A senha é lida da variável `PORTAL_SMTP_SENHA` do ambiente
da conta do Windows que inicia o portal. Configure-a localmente nas Variáveis de
Ambiente do Windows e abra uma nova janela do terminal/portal para carregar.
A senha do código original não foi reproduzida neste pacote.

Destinatários devem ser conferidos pelo operador antes de confirmar o envio.
Cliques repetidos após sucesso não reenviam o mesmo relatório. Um envio iniciado
sem confirmação de sucesso fica marcado para revisão pela TI: confira o recebimento
antes de liberar outra tentativa. Não houve conexão SMTP nos testes.

## Certificados

Inventário por data de modificação não equivale à leitura de validade do certificado.
Use Validade dos Certificados para o vencimento real.

O monitor do portal NÃO executa o Robocopy contido no BAT original. Mantenha sua
rotina de cópia atual separadamente, ou configure as pastas de origem diretamente
em `config_apps.ini` se a intenção for consultar os arquivos existentes na origem.

Para preservar a memória anterior do monitor, copie `estado_certificados.json` e
`Relatorio_Certificados.xlsx` atuais para `dados/apps/monitora_certificados/`, com o
portal parado. Os caminhos dos certificados devem continuar iguais para reutilizar
os registros pelo caminho. A leitura será refeita quando não houver registro.

Também é possível enviar o relatório com a coluna `SENHA CORRIGIDA` na tela de
Validade dos Certificados. O relatório com dashboard ou o formato antigo é aceito.
Esse envio atualiza a base de correções do aplicativo; libere apenas aos responsáveis.
O arquivo `estado_certificados.json` recebido no ZIP é histórico operacional e não
foi embutido no pacote de instalação. Os relatórios contêm senhas e devem permanecer
sob controle dos usuários autorizados.

## Análise de e-mails

Foram preservadas as regras e pontuações do `app.py` chamado pelo BAT recebido,
incluindo os cortes 25 para spam e 50 para domínio. Não foram adotadas as regras de
`app_chat.py`. A lista de liberados deve existir para não produzir uma análise sem
as exceções do escritório; se indisponível, a execução apresenta erro.

A análise move somente as cópias enviadas para a pasta daquela execução.
Não move os CSVs da pasta original, não modifica a lista de liberados nem o histórico
e não aplica bloqueio no KingHost. O resultado é entregue para revisão/importação.
Para manter o histórico usado pelo app original, continue o arquivamento habitual
das listas aprovadas na pasta `Bloqueados/Historico` configurada.

## Busca de NF-es

A interface Streamlit foi substituída por uma tela Flask integrada ao login.
Os XMLs podem ter nome igual ao número da nota ou à chave de 44 dígitos.
O conteúdo do XML precisa confirmar a chave. O comportamento antigo aceitava
candidatos sem chave legível; isso podia entregar uma nota incorreta com o mesmo
número. Agora esses arquivos são recusados e informados no resumo.

A pesquisa é identificada pela chave completa, evitando que notas com o mesmo
número se sobrescrevam. O ZIP usa a chave como nome de arquivo. A versão mais recente
por data de modificação é selecionada quando existe mais de um XML da mesma chave.
Os PDFs são procurados junto ao XML pelo mesmo nome base.
