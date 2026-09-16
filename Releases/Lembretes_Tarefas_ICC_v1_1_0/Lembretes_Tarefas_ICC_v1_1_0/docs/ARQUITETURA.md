# Arquitetura e regras da versão 1.0.0

## Integração conferida

Base analisada: `Portal_Apps.zip`, enviado em 10/09/2026. O catálogo real chama `importlib.import_module`, obtém o atributo `app` e monta aplicações Flask com `DispatcherMiddleware`. `configure_access` compartilha a chave/cookie de sessão, preenche `g.usuario`, confere permissões por rota e valida CSRF. O novo módulo utiliza exatamente essa interface e `url_for` para respeitar o prefixo da montagem.

O cadastro acrescentado é:

```json
{
  "nome": "Lembretes de Tarefas",
  "descricao": "Agendamento e envio de lembretes por e-mail",
  "rota": "/lembretes",
  "modulo": "apps.lembretes_tarefas.app",
  "ativo": true
}
```

O instalador preserva todas as outras entradas, não aplica o catálogo antigo do ZIP e não altera `servidor.py`, `portal/acesso.py`, Caddy, portas, usuários ou permissões existentes. Em reinstalações, preserva também nome, descrição, posição e estado ativo/inativo do cadastro deste aplicativo. Código anterior e catálogo são copiados para `Releases/lembretes_tarefas`.

Referência: [Application Dispatching, documentação do Flask](https://flask.palletsprojects.com/en/stable/patterns/appdispatch/).

## Separação de responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `app.py` | Rotas, autorização complementar, formulários, tokens de confirmação e templates |
| `validation.py` | Campos, e-mail, URLs/caminhos e validação de programação |
| `recurrence.py` | Cálculo de ocorrências a partir da data original |
| `store.py` | SQLite, transações, fila, histórico, auditoria e controle de revisão |
| `schema.sql` | Estrutura de dados com versão 2; migração aditiva da versão 1 |
| `mailer.py` | MIME HTML/texto, TLS e classificação de erros SMTP |
| `worker.py` | Lock de processo, retomada, consulta periódica e processamento da fila |
| `settings.py` | Configuração isolada, caminhos e precedência de variáveis de ambiente |
| `versao.py` | Versão do aplicativo |
| `templates/` e `static/` | Interface local, sem CDN ou bibliotecas externas no navegador |
| `ferramentas_lembretes/` | Instalação, credencial DPAPI e tarefa Windows |

A importação do aplicativo nunca cria thread de envio nem inicia scheduler. O processo web apenas cadastra dados e solicitações. Somente o worker transmite e-mails. A senha SMTP não precisa estar disponível para o processo do portal.

Foi escolhido um processo dedicado em vez de uma thread em cada aplicação Flask. Isso permite reiniciar o portal sem interromper o envio, observar o agendador separadamente e impedir que a importação de um módulo crie um novo scheduler. Não há dependência de APScheduler.

## Dados

O banco fica no disco local em `dados/apps/lembretes_tarefas/lembretes.sqlite3`.

| Tabela | Conteúdo |
|---|---|
| `collaborators` | Nome, e-mail único sem distinção de caixa, situação, autores, datas e revisão do cadastro compartilhado |
| `tasks` | Destinatário, título, descrição, links, data/hora inicial, fuso, regra JSON, próxima/última execução, proprietário, status, contadores, erro e revisão |
| `deliveries` | Uma linha por ocorrência solicitada, chave única, tipo, estado, tentativa, instante, destinatário/conteúdo imutáveis e Message-ID |
| `history` | Cada tentativa, com ENVIADO ou ERRO e detalhe sem credenciais |
| `audit` | Criação, edição, pausa, reativação, cancelamento, solicitações manuais, resolução e datas puladas |
| `worker_state` | Último sinal de vida, PID, disponibilidade da credencial e diagnóstico de configuração |

`send_count` conta envios agendados e manuais aceitos/confirmados. `scheduled_count` conta somente agendados aceitos/confirmados. `skipped_count` conta ocorrências puladas após paradas, pausas ou encerramento manual. O limite da repetição é aplicado ao índice de calendário da programação atual; alterar a regra inicia uma nova programação sem apagar contadores e histórico anteriores.

Tarefas nunca são removidas fisicamente pelas telas. O cancelamento preserva os registros. Cada envio guarda uma cópia do conteúdo, evitando que uma edição posterior modifique a descrição histórica.

A migração para a versão 2 cria somente a tabela de colaboradores e seus índices. DDL e `user_version` são confirmados na mesma transação; uma falha reverte a migração. O instalador usa a API de backup do SQLite antes de atualizar o código, incluindo dados confirmados ainda presentes no WAL.

O identificador do colaborador selecionado é usado apenas ao salvar o formulário. A aplicação relê o registro ativo dentro da transação e copia nome/e-mail para a tarefa. Não há atualização em cascata de destinatários. A edição/inativação no cadastro não altera tarefas anteriores, a fila ou o histórico. Revisões impedem sobrepor uma edição concorrente. O preenchimento no navegador trata nomes duplicados e não substitui o destinatário de uma tarefa existente sem uma nova seleção.

## Concorrência e entrega

1. O Agendador de Tarefas usa `MultipleInstances = IgnoreNew`.
2. O worker obtém um lock exclusivo do sistema operacional no arquivo `agendador.lock`. No Windows usa `msvcrt`; nos testes Linux usa `flock`. O lock permanece durante toda a vida do processo e é liberado pelo sistema operacional após encerramento/crash.
3. O SQLite usa WAL, `synchronous=FULL`, `foreign_keys=ON` e transações `BEGIN IMMEDIATE` nas escritas críticas.
4. A chave única da ocorrência automática combina ID da tarefa, revisão da programação e data prevista. A inserção é idempotente.
5. A reserva passa para `SENDING` em uma transação confirmada **antes** de qualquer conexão SMTP.
6. Após o aceite SMTP, uma única transação registra histórico, resultado, contadores e próxima ocorrência.

O lock de processo protege a recuperação. Registros `SENDING` só são reclassificados como `UNKNOWN` quando um novo worker obtém o lock, provando que o anterior não está mais ativo. Nunca há recuperação por mero vencimento de um timeout, porque o worker anterior ainda poderia transmitir.

Referência: [Transações SQLite e BEGIN IMMEDIATE](https://www.sqlite.org/lang_transaction.html).

## Estados da fila

| Estado | Comportamento |
|---|---|
| `WAITING` | Aguardando processamento ou uma tentativa temporária segura |
| `SENDING` | Reservado de forma durável; transmissão pode estar em andamento |
| `SENT` | Aceite SMTP ou confirmação manual documentada |
| `ERROR` | Recusa/falha definida; novas tentativas automáticas encerradas |
| `UNKNOWN` | Resultado ambíguo; proibido reenviar automaticamente |
| `CANCELED` | Solicitação cancelada por edição, pausa ou cancelamento da tarefa |
| `DISCARDED` | Ocorrência encerrada explicitamente sem nova transmissão |

Erros temporários seguros usam três tentativas no total, separadas por 60 e 300 segundos. Uma nova tentativa após `ERROR` exige ação do usuário. `UNKNOWN` exige confirmação do que ocorreu ou encerramento sem reenvio.

Depois de um aceite, eventual falha de fechamento da conexão não transforma sucesso em erro. Falha ao registrar o sucesso no SQLite encerra o worker, mantendo o registro como `SENDING`; na retomada será exigida conferência. O Message-ID é preservado nas tentativas, mas não é tratado como garantia de deduplicação pelo provedor.

SMTP e SQLite não participam de uma mesma transação distribuída. A janela entre aceite remoto e confirmação local impede prometer entrega exatamente uma vez com ambos simultaneamente garantidos. A implementação prioriza não repetir automaticamente mensagens cujo resultado é desconhecido. Referência: [RFC 1047, Duplicate messages and SMTP](https://www.rfc-editor.org/rfc/rfc1047.html).

## Regras de calendário

Os instantes ficam em UTC; cada tarefa preserva seu fuso IANA. A próxima ocorrência é encontrada por cálculo e busca binária no índice, sem criar centenas de linhas futuras. Os testes abrangem retorno ao dia 31, anos bissextos, intervalos, dias selecionados, limites e parada prolongada.

Horários inexistentes devido a avanço de horário de verão passam para o primeiro minuto local válido. Em horários ambíguos, usa-se a primeira ocorrência (`fold=0`). Para Sorriso o padrão é `America/Cuiaba`.

Após parada, o worker envia a ocorrência pendente mais antiga e calcula a próxima estritamente posterior à conclusão. As intermediárias são registradas como puladas. Isso reduz e-mails acumulados sem apagar a trilha de auditoria.

## Segurança e operação

- A identidade vem de `g.usuario`. Proprietários acessam suas tarefas; administradores acessam todas.
- O aplicativo falha fechado quando executado sem a autenticação central instalada. Não existe login de desenvolvimento no pacote.
- Todos os POSTs usam o CSRF central. Envios manuais/testes usam também tokens assinados, vinculados ao usuário, com validade de 15 minutos e chave única na fila.
- Conteúdo HTML é escapado. Links só aceitam HTTP/HTTPS ou caminhos de arquivo Windows; não executam código e não são acessados pelo servidor.
- A conexão SMTP sempre usa SSL ou STARTTLS e valida certificados. Nunca há autenticação SMTP em conexão sem criptografia.
- O launcher carrega usuário e senha juntos do XML DPAPI, quando existente, com prioridade sobre variáveis herdadas. Na ausência do XML, aceita as variáveis do processo. Logs e erros não registram senha, corpo da mensagem ou resposta SMTP bruta. `diagnosticar_smtp.py` executa somente TLS e AUTH, sem MAIL/RCPT/DATA.
- O cadastro de colaboradores é compartilhado entre usuários autorizados do aplicativo; alterações são exclusivas de administradores e registradas na auditoria. Ele não modifica os usuários de login do portal.
- O processo Windows usa a conta configurada com logon por senha, inicia no boot, não exige sessão interativa e tem `ExecutionTimeLimit=0`. O gatilho periódico tenta retomá-lo se estiver encerrado.

Referência: [Configurações do Agendador de Tarefas da Microsoft](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

Os arquivos Windows foram analisados sintaticamente, mas precisam ser executados no servidor de destino para confirmar permissões, DPAPI, credenciais e conectividade. O pacote não contém dados, contas, senhas, certificados ou bancos de produção.
