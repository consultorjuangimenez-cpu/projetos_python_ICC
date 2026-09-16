# Lembretes de Tarefas | ICC Contabilidade

Versão 1.1.0, 15/09/2026.

Novo aplicativo para o Portal_Apps existente. A integração foi conferida com os arquivos `portal/acesso.py`, `portal/usuarios.py` e `portal/catalogo.py` do portal enviado em 10/09/2026. O instalador adiciona somente o módulo e seu cadastro, preservando os demais aplicativos e as alterações posteriores no servidor, HTTPS e proxy.

## Atualizar a versão já instalada

Esta entrega reúne a correção no carregamento da credencial SMTP e o cadastro de colaboradores com preenchimento automático do e-mail. O banco, o histórico e a credencial já configurada são preservados.

1. Extraia o ZIP em uma pasta separada do portal, por exemplo, Downloads.
2. No Agendador de Tarefas do Windows, **desabilite** temporariamente `ICC_Lembretes_Tarefas` para impedir o gatilho de retomada a cada dois minutos. Aguarde terminar qualquer envio em andamento e use **Encerrar**. Se usa o agendador manual, encerre sua janela com Ctrl+C. Pare também o processo do portal pelo procedimento habitual.
3. Execute `INSTALAR_LEMBRETES.bat` na pasta extraída e informe a pasta atual do portal. O instalador salva os arquivos anteriores e um backup consistente do banco em `Releases\lembretes_tarefas\DATA_HORA_IDENTIFICADOR`. Não substitua a pasta inteira do portal.
4. Na pasta **do portal instalado**, execute `ferramentas_lembretes\DIAGNOSTICAR_SMTP.bat` com a mesma conta Windows que configurou a credencial. O resultado esperado é `autenticacao: OK`, código `235`. Se aparecer `535`, siga a seção de diagnóstico abaixo antes de retomar os envios.
5. Reinicie o portal. No Agendador de Tarefas, **habilite** e **execute** a tarefa existente `ICC_Lembretes_Tarefas`. Não é necessário instalar a tarefa novamente. O cadastro de colaboradores é criado automaticamente no primeiro acesso ou início do agendador.
6. Abra **Teste de e-mail** no aplicativo e confira o histórico e o recebimento. Testes antigos com erro `535` não são reenviados sozinhos; após corrigir a autenticação, use **Tentar novamente** no histórico ou solicite um novo teste.
7. Abra **Colaboradores**, cadastre nome e e-mail e use o nome ao criar uma tarefa.

O reinício do agendador é necessário: um processo já aberto mantém a credencial anterior em memória. Uma interrupção durante transmissão pode produzir uma pendência de conferência no histórico; ela não é reenviada automaticamente.

## Primeira instalação no servidor

1. Extraia este ZIP em uma pasta separada, por exemplo, Downloads. Não copie o conteúdo sobre o portal inteiro.
2. Pare o processo do portal durante a instalação. Se o módulo já existe, siga a seção de atualização acima.
3. Execute `INSTALAR_LEMBRETES.bat`. Confirme o caminho que o próprio instalador apresenta. O padrão é `C:\C\Projetos_Phyton\Portal_Apps`. Ele usa o Python da `.venv` do portal e instala somente `tzdata`, sem alterar as versões de Flask e Waitress.
4. Reinicie o portal pelo procedimento que você já utiliza. No gerenciamento de usuários, conceda **Lembretes de Tarefas** aos usuários autorizados. Administradores já terão acesso.
5. Na pasta **do portal instalado**, abra `ferramentas_lembretes\CONFIGURAR_SMTP.bat`. Informe a senha de `ti@icccontabilidade.com.br` na janela do Windows. A senha é criptografada para a conta Windows atual e este servidor, usando DPAPI.
6. Execute `ferramentas_lembretes\INSTALAR_AGENDADOR.bat` com o botão direito, **Executar como administrador**. Use a mesma conta Windows que configurou a credencial SMTP. Aqui será solicitada a senha de login dessa conta Windows, para a tarefa executar mesmo sem usuário conectado. Não é a senha do e-mail.
7. Acesse **Lembretes de Tarefas** no menu do portal. Confira o indicador do agendador, abra **Teste de e-mail**, informe uma caixa de teste e confirme o envio. Confira o histórico e a caixa de entrada antes de cadastrar as tarefas reais.

Endereço esperado no ambiente atual: `https://10.10.10.154/lembretes/`. A montagem no menu não exige nova porta ou alteração no Caddy. O aplicativo não inicia um servidor Flask separado.

O cadastro não exige Python ou instalação nas estações. Apenas o servidor executa os processos.

## Configuração SMTP

Arquivo: `dados\apps\lembretes_tarefas\config.ini` dentro do portal.

| Parâmetro | Padrão |
|---|---|
| Remetente | ti@icccontabilidade.com.br |
| `smtp_servidor` | smtp.kinghost.net |
| `smtp_porta` | 465 |
| `smtp_seguranca` | SSL |
| `smtp_usuario` | ti@icccontabilidade.com.br |
| `smtp_timeout` | 30 segundos |
| `intervalo_verificacao` | 15 segundos |
| `fuso` | America/Cuiaba |

SSL conecta com TLS desde o início. Para um provedor que use STARTTLS, configure `smtp_seguranca = STARTTLS` e a porta informada por ele, normalmente 587. A validação do certificado TLS permanece habilitada.

Os padrões KingHost seguem a [orientação oficial para SMTP com SSL na porta 465](https://king.host/wiki/artigo/email-no-android/). Confirme se a conta contratada usa KingHost ou um servidor de revenda antes de alterar os parâmetros.

A senha **não deve ser inserida no INI, BAT ou Python**. A credencial criada pelo assistente fica em `smtp_credencial.xml`, criptografada pelo Windows e com permissões de arquivo restritas. O launcher a carrega em memória somente para o processo do agendador.

Na versão 1.1.0, se `smtp_credencial.xml` existir, **o usuário e a senha desse arquivo são carregados juntos e têm prioridade sobre credenciais herdadas do ambiente**. Um XML inválido interrompe a inicialização, sem tentar uma senha alternativa. O launcher altera somente seu processo e o processo Python filho; não altera variáveis persistentes do Windows nem os outros aplicativos.

Na ausência do XML, continuam aceitas as variáveis `PORTAL_SMTP_USUARIO` e `PORTAL_SMTP_SENHA`. Para servidor, porta e segurança, `PORTAL_SMTP_SERVIDOR`, `PORTAL_SMTP_PORTA` e `PORTAL_SMTP_SEGURANCA` mantêm prioridade sobre o INI. Uma variável definida apenas em uma janela de terminal não estará automaticamente disponível no Agendador de Tarefas. Prefira o assistente criptografado para este servidor.

Depois de mudar credenciais ou configurações, reinicie o agendador e o portal. Ao mudar o usuário Windows ou migrar para outro servidor, configure novamente a credencial SMTP nessa conta/máquina. A documentação da Microsoft explica o vínculo do [Export-Clixml com DPAPI no Windows](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/export-clixml).

### Diagnosticar o erro 535

Foi corrigida uma falha em `Rodar_Agendador.ps1`: variáveis antigas podiam impedir a leitura da senha recém-configurada ou misturar usuário e senha de fontes diferentes. É necessário testar no servidor para confirmar se essa falha causou a recusa observada.

1. Execute `ferramentas_lembretes\DIAGNOSTICAR_SMTP.bat` na pasta instalada. Confira `origem: XML_CONFIGURAR_SMTP`, o usuário, servidor, porta e resultado de autenticação.
2. Se o XML resultar em `535`, execute `TESTAR_SENHA_DIGITADA.bat`. A janela usa a credencial digitada apenas para esse diagnóstico e não a salva.
3. Se a senha digitada funcionar, salve-a novamente com `CONFIGURAR_SMTP.bat`, repita o diagnóstico do XML e reinicie o agendador.
4. Se ambos recusarem a autenticação, compare o servidor SMTP de saída com o configurado para essa conta no Outlook e consulte o provedor com o horário do diagnóstico. O código `535` sozinho não comprova que a senha digitada esteja errada.

Esses dois assistentes fazem somente conexão TLS e autenticação. Não enviam mensagens nem alteram a fila. O resultado `235` confirma a autenticação; o envio e o recebimento devem ser conferidos em **Teste de e-mail**. Consulte a [definição dos códigos SMTP AUTH na RFC 4954](https://www.rfc-editor.org/rfc/rfc4954.html#section-6).

O relatório fica em `logs\lembretes_tarefas\diagnostico_smtp_DATA_HORA.txt`. Ele não contém a senha nem o conteúdo criptografado do XML. A credencial `SSO_POP_User` do Gerenciador de Credenciais é separada da credencial criada para este aplicativo; o agendador utiliza o XML do configurador.

## Cadastro de colaboradores e e-mail automático

1. Entre no portal como administrador e abra **Lembretes de Tarefas → Colaboradores → Novo colaborador**.
2. Informe o nome que será usado na tarefa e o e-mail, deixe **Ativo** e salve.
3. Ao criar ou editar uma tarefa, digite o nome no campo **Nome do colaborador**. Ao completar um nome único ou selecionar uma sugestão, o e-mail será preenchido automaticamente.

Todos os usuários autorizados do aplicativo podem consultar e utilizar o cadastro. Administradores podem cadastrar, editar e inativar. Esse cadastro não cria contas ou senhas de acesso ao portal.

Cada e-mail tem um único cadastro. Nomes iguais são permitidos e exigem selecionar a sugestão com o e-mail correto. Ao trocar o nome, o e-mail anterior é limpo para evitar usar o destinatário errado. Ainda é possível preencher nome e e-mail manualmente somente para aquela tarefa.

Alterar ou inativar um colaborador **não modifica tarefas já salvas, solicitações na fila ou o histórico**. Para atualizar o destinatário de uma tarefa existente, edite essa tarefa e selecione novamente o cadastro desejado. Inativar um colaborador retira seu nome das novas seleções; para interromper lembretes existentes, pause ou cancele as tarefas correspondentes.

## Agendamento e repetição

- **Não repetir:** um envio agendado; depois a tarefa fica concluída.
- **Diariamente:** todos os dias no horário informado.
- **Semanalmente:** a cada sete dias a partir da data inicial.
- **Mensalmente:** no dia da data inicial. Uma tarefa iniciada no dia 31 usa o último dia de meses menores e volta ao dia 31 quando existir.
- **Anualmente:** no mesmo mês/dia. Uma tarefa de 29/02 usa 28/02 nos anos comuns e volta a 29/02 nos anos bissextos.
- **Personalizado:** intervalo de dias, seleção de dias da semana ou um dia específico do mês. Essas são alternativas; não são combinadas simultaneamente.
- **Término e limite:** podem ser aplicados também às repetições comuns. O limite inclui a primeira ocorrência e considera as posições do calendário, inclusive datas puladas. Envios manuais não consomem esse limite. Vale o limite que ocorrer primeiro.

No personalizado, a data inicial é a primeira data permitida. A primeira execução efetiva será a primeira data compatível com a regra. Exemplo: data inicial 15/09 e dia mensal 10 resulta em primeira execução em 10/10.

Novas tarefas e novas programações não aceitam data/horário inicial no passado. Editar apenas título, descrição, colaborador ou links permite preservar uma programação existente, mesmo se estiver atrasada. Ao alterar a programação, é necessário informar uma nova data inicial futura. Tarefas canceladas ficam preservadas e não são reativadas; crie outra tarefa.

Todos os horários são exibidos no fuso `America/Cuiaba`, apropriado para Sorriso. O banco armazena instantes em UTC e preserva o fuso de cada tarefa. Alterar o padrão de fuso afeta novas tarefas; as existentes conservam seu fuso original.

## Comportamento após parada ou falha

O processo de agendamento é independente do navegador e do Waitress. A tarefa Windows `ICC_Lembretes_Tarefas` inicia no boot e tem uma verificação de retomada a cada dois minutos. Instâncias simultâneas são bloqueadas pelo Windows, por um lock do sistema operacional e pela reserva transacional no SQLite.

Após uma parada, é enviado **um lembrete referente à ocorrência pendente mais antiga** de cada tarefa. Em seguida, o sistema pula as datas intermediárias já passadas, registra a quantidade e calcula a próxima ocorrência futura. Isso evita uma sequência de e-mails antigos. Se o término ou o limite já tiver sido atingido, a tarefa será concluída após tratar a ocorrência pendente.

Ao reativar uma tarefa pausada, a próxima ocorrência será a primeira futura. Não são enviados lembretes referentes ao período da pausa.

Falhas temporárias comprovadamente anteriores ao aceite da mensagem têm até três tentativas, com espera de 1 minuto e depois 5 minutos. Falhas definitivas exigem correção e a ação **Tentar novamente**. O histórico preserva cada tentativa.

Se a conexão cair durante a transmissão ou o processo terminar sem registrar a confirmação, o envio fica como **Conferência necessária**. Ele não é reenviado automaticamente. Confira com o destinatário e use **Confirmar como enviado** ou **Encerrar sem reenviar**. Se confirmar que não chegou e quiser enviá-lo, encerre a ocorrência e utilize **Enviar agora** como uma nova ação explícita.

Essa política impede reenvio automático em situações ambíguas. SMTP não fornece garantia absoluta de entrega exatamente uma vez; a [RFC 1047](https://www.rfc-editor.org/rfc/rfc1047.html) documenta a janela entre entrega e confirmação. **ENVIADO** significa aceite pelo servidor SMTP ou confirmação manual explicitamente registrada. Não confirma leitura nem chegada à caixa de entrada.

## Uso e permissões

Usuários com permissão para o aplicativo podem cadastrar lembretes para colaboradores e gerenciar as tarefas que criaram. Administradores veem e gerenciam todas. O campo “criado por” usa a identidade autenticada do portal, nunca um nome digitado no formulário. Somente administradores podem executar o teste de e-mail.

O dashboard mostra programações ativas, pendentes de hoje, atrasadas, envios aceitos e tarefas com erro. Os indicadores usam o universo permitido ao usuário; os filtros se aplicam à tabela. A listagem e o histórico têm paginação de 50 registros. O painel de pendências exibe as 100 ocorrências mais recentes; também é possível tratá-las dentro de cada tarefa.

**Enviar agora** pede confirmação, cria uma solicitação na fila e mantém a programação futura. Clicar duas vezes ou reenviar o mesmo formulário de confirmação não cria dois e-mails. Se existir um lembrete agendado para o mesmo momento, ele continua sendo uma ocorrência separada.

Editar, pausar ou cancelar cancela solicitações ainda na fila daquela tarefa. Um envio já em transmissão não pode ser alterado ou cancelado. A interface orienta aguardar ou conferir o resultado.

Links web ficam clicáveis. Caminhos UNC, como `\\servidor\pasta\arquivo.xlsx`, e caminhos Windows são aceitos, preservados no e-mail e podem ser copiados na tela. O navegador/Outlook pode impedir a abertura direta de um link de arquivo; nesse caso, copie o caminho para o Explorador de Arquivos. O sistema não executa arquivos nem acessa esses caminhos por conta própria.

## Dados, logs e manutenção

| Local dentro do portal | Finalidade |
|---|---|
| `apps\lembretes_tarefas` | Código, templates e arquivos estáticos do módulo |
| `dados\apps\lembretes_tarefas\lembretes.sqlite3` | Colaboradores, tarefas, fila, histórico e auditoria |
| `dados\apps\lembretes_tarefas\config.ini` | Configuração sem senha |
| `dados\apps\lembretes_tarefas\smtp_credencial.xml` | Credencial criptografada pelo Windows |
| `logs\lembretes_tarefas\agendador.log` | Diagnóstico de envio, com rotação |
| `Releases\lembretes_tarefas` | Cópias dos arquivos anteriores e backup do banco antes da atualização |
| `ferramentas_lembretes` | Assistentes de instalação, credenciais e agendamento |

O banco deve permanecer no disco local do servidor. A conta do portal e a conta do agendador precisam de leitura/escrita na pasta de dados; o agendador também precisa escrever nos logs. Nenhuma unidade de rede mapeada é necessária para enviar os links.

Para backup, copie a pasta de dados completa com o portal e o agendador **encerrados**. Alternativamente, sua rotina de backup pode usar a API de backup do SQLite. Não copie apenas o arquivo `.sqlite3` enquanto houver escrita, porque o banco usa WAL. O arquivo de lock não deve ser apagado para tentar liberar um processo em execução.

O backup da credencial DPAPI funciona com a mesma conta e máquina. Ao restaurar em outra máquina, use novamente `CONFIGURAR_SMTP.bat`. Uma restauração de banco antigo também pode recolocar ocorrências já enviadas como pendentes; confira o histórico e mantenha o agendador parado até ajustar essas ocorrências.

O `INICIAR_AGENDADOR_MANUAL.bat` serve para diagnóstico, mantendo sua janela aberta. Para operação contínua, use a tarefa Windows instalada. `VERIFICAR_CONFIGURACAO.bat` valida banco, fuso e disponibilidade da credencial no processo, sem conectar ao SMTP e sem enviar mensagens.

## Diagnóstico rápido

| Sintoma | Causa provável | Como confirmar |
|---|---|---|
| Aplicativo não aparece no menu | Portal ainda usa catálogo anterior ou usuário sem permissão | Reinicie o portal e confira as permissões do usuário |
| Agendador sem sinal recente | Tarefa Windows parada, conta inválida ou erro de inicialização | Consulte `ICC_Lembretes_Tarefas` no Agendador de Tarefas, seu último resultado e o log |
| SMTP pendente | Senha ausente no processo | Execute a configuração na mesma conta Windows e reinicie o agendador |
| Autenticação SMTP recusada | Credencial carregada, servidor da conta ou restrição do provedor | Execute `DIAGNOSTICAR_SMTP.bat` e compare com `TESTAR_SENHA_DIGITADA.bat` |
| Erro TLS | Host incorreto, certificado não confiável ou relógio incorreto | Confira o servidor oficial, o relógio e os certificados confiáveis |
| Aceito pelo SMTP, mas não recebido | Spam, rejeição posterior ou regra do destinatário | Confira spam, caixa de retorno e logs do provedor |
| Conferência necessária | Interrupção durante o envio | Confira com o destinatário e resolva pela tela de histórico |
| Caminho de rede não abre | Restrição de links de arquivo ou falta de acesso | Copie o caminho e abra pelo Explorador de Arquivos |

## Validação entregue

O pacote foi testado em Linux com Python 3.12, Flask 3.1.3, Waitress 3.0.2 e tzdata 2026.4, usando os módulos reais de autenticação e catálogo do portal. Os scripts PowerShell passaram por análise de sintaxe. A execução nativa das tarefas Windows, a descriptografia DPAPI e o envio real pela conta da ICC precisam ser confirmados no servidor durante os passos de instalação. Nenhum e-mail real foi enviado durante o desenvolvimento.

Veja `docs/VALIDACAO.md` para os testes e `docs/ARQUITETURA.md` para detalhes técnicos.
