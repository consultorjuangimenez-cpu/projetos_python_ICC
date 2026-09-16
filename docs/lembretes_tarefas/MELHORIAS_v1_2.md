# Lembretes de Tarefas — versão 1.2.0

Implementação de 16/09/2026. Mantém Flask, SQLite, autenticação do portal, fila SMTP e Agendador de Tarefas do Windows. Não adiciona bibliotecas nem altera outros aplicativos.

## Funcionalidades

### Dias úteis e feriados

- Campo por tarefa: **Manter**, **Antecipar para dia útil** ou **Postergar para dia útil**.
- Calendário nacional calculado por ano, incluindo a Paixão de Cristo; feriados de Sorriso/MT em **13 de maio** e **29 de junho**.
- Tela **Feriados** para consulta do calendário e inclusão/remoção de datas adicionais pela administração. Datas adicionais são específicas do ano informado.
- Carnaval, Corpus Christi e outros pontos facultativos não são tratados automaticamente como feriados. Podem ser adicionados se adotados pelo escritório.
- O ajuste preserva horário, fuso e âncora original da repetição: um lembrete mensal deslocado não muda o dia-base dos meses seguintes.
- O término e o limite de ocorrências são avaliados nas datas originais, antes do ajuste. O envio postergado pode cair após a data nominal de término.
- Ocorrências da mesma tarefa que convergem para o mesmo horário útil são agrupadas pelo avanço da programação: há um envio, e as demais entram no contador de ocorrências puladas. Não são enviados vários e-mails iguais no mesmo instante.
- A primeira ocorrência ajustada não pode estar no passado. Alterar feriados recalcula próximas ocorrências de tarefas ativas/pausadas que usam ajuste e cancela seus lembretes ainda pendentes, preservando histórico e tarefas configuradas com **Manter**. Se uma próxima ocorrência for deslocada para o passado, será tratada como atrasada na próxima rodada do worker.
- Mudanças de calendário que afetariam um envio em andamento ou com resultado incerto são revertidas: é necessário resolver a ocorrência antes.

Referências conferidas: [Prefeitura de Sorriso — Decreto 1.450/2026](https://site.sorriso.mt.gov.br/noticia/prefeitura-divulga-calendario-de-feriados-e-pontos-facultativos-para-2026-6970d539ef140) e [calendário federal de 2026](https://agenciagov.ebc.com.br/noticias/202512/confira-o-calendario-oficial-de-feriados-nacionais-e-pontos-facultativos-em-2026). As regras são locais e não consultam a internet durante o processamento; mudanças futuras do calendário oficial exigem revisão do cadastro/código.

### Prioridade, prazo e conclusão

- Prioridades: **Normal**, **Alta** e **Crítica**.
- **Prazo final** é uma data/hora independente da programação dos lembretes. É obrigatório para tarefas críticas e não é deslocado por fins de semana/feriados.
- Conforme confirmado pelo solicitante, o alerta vai ao **dono da tarefa**, definido como o colaborador e e-mail informados no cadastro. Não é enviado a um gestor separado nem à conta de quem cadastrou a tarefa no portal (essa conta não possui campo de e-mail).
- O worker coloca o alerta na fila quando `agora >= prazo_final - 24 horas`, desde que a tarefa seja crítica, não esteja cancelada e não tenha sido concluída manualmente.
- O envio ocorre na primeira verificação elegível, sujeito à disponibilidade do worker/SMTP. Se houver parada ou cadastro dentro das últimas 24 horas, o alerta entra na fila na próxima verificação, inclusive se o prazo já tiver passado.
- Um alerta por tarefa, prazo e destinatário. Reinícios, múltiplas verificações ou edição do título não repetem um alerta aceito. Alterar prazo ou destinatário define uma nova combinação elegível.
- O alerta usa a fila e o tratamento SMTP existentes, com prioridade na reserva dos envios. Erros explícitos podem ter as tentativas já previstas; resultado incerto nunca provoca reenvio automático.
- **Concluir tarefa** grava a conclusão manual e cancela os lembretes/alertas ainda aguardando. Envios já aceitos não são revertidos. Envios em andamento ou incertos devem ser resolvidos antes da conclusão.
- O término automático da repetição passa a ser apresentado como **Programação encerrada**; isso não significa conclusão do trabalho. A conclusão real é registrada pelo novo botão.
- Pausar os lembretes não desativa o alerta de prazo crítico. Concluir ou cancelar a tarefa impede novos alertas.
- Tarefas concluídas manualmente não podem ser editadas, reativadas ou reenviadas. Para novo trabalho, cadastre outra tarefa.
- Alertas aparecem separadamente no histórico como **Alerta crítico ao dono** e não alteram a recorrência nem os contadores de lembretes agendados/manuais.

### Departamento e cliente

- Campos disponíveis no cadastro, edição, detalhes e filtros do dashboard.
- O cliente aceita seleção ou preenchimento manual. Sugestões são lidas do inventário SQLite existente de certificados, usando apenas nome e documento dos registros vistos no último inventário.
- A consulta ao inventário é somente de leitura e não importa nem inicia o módulo de certificados. Não lê a chave de criptografia nem as colunas de senhas.
- Indisponibilidade do inventário não impede cadastrar uma tarefa manualmente.
- O nome/documento selecionado é copiado para a tarefa; alterações posteriores do inventário não mudam o histórico das tarefas.
- Filtros seguem as permissões existentes: usuário comum vê suas próprias tarefas; administrador vê todas. Indicadores mantêm o escopo original; os filtros se aplicam à tabela.

### Modelos

- Tela **Modelos** com criação, edição e inativação pela administração; usuários autorizados podem selecionar modelos ativos.
- Selecionar um modelo no cadastro preenche automaticamente **Título**, **Descrição**, **Links** e **Regra de repetição**, incluindo modo personalizado, dias da semana e limites.
- Responsável, data inicial, horário, prioridade, prazo, departamento e cliente continuam sendo definidos na tarefa.
- O preenchimento cria uma cópia editável no formulário. Alterar/inativar o modelo não modifica tarefas existentes.
- Formulários mantêm validação de links, escape de conteúdo, CSRF e controle de revisão contra edição concorrente.

## Impactos no SQLite

Migração automática e transacional de `user_version` 1/2 para **3**. O código da aplicação passa a **1.2.0**. A migração usa adição de colunas, sem recriar tabelas operacionais, renumerar IDs ou apagar registros.

| Tabela | Alteração |
|---|---|
| `tasks` | `business_day_policy TEXT DEFAULT 'keep'`, `priority TEXT DEFAULT 'NORMAL'`, `department TEXT DEFAULT ''`, `client TEXT DEFAULT ''`, `deadline_ts INTEGER NULL`, `completed_at INTEGER NULL` |
| `deliveries` | `purpose TEXT DEFAULT 'REMINDER'`; aceita `REMINDER` e `ESCALATION` |
| `holidays` | Nova tabela: data, nome, autor e criação dos complementos do calendário |
| `task_models` | Nova tabela: nome, título, descrição, links JSON, regra JSON, ativo, autores, datas e revisão |
| Índices | Prazo/prioridade/conclusão, categorias e modelos ativos |

O campo `kind` da fila é preservado para evitar reconstrução da tabela e seus vínculos históricos: alertas são operações adicionais com `kind='MANUAL'` e `purpose='ESCALATION'`. As decisões e a apresentação usam `purpose` para separar alertas dos lembretes manuais.

Antes de atualizar um banco antigo, a API de backup do SQLite cria uma cópia completa (incluindo transações confirmadas em WAL) em `dados/apps/lembretes_tarefas/backups_migracao/antes_v3_*.sqlite3` e confere sua integridade. Falha no backup interrompe a migração. Falha na alteração do esquema reverte a transação.

Tarefas anteriores mantêm datas, próximas execuções, responsáveis, regras, estados e histórico. Recebem **Normal**, **Manter**, categorias vazias e prazo/conclusão manual nulos. O encerramento antigo de uma programação não é convertido em conclusão manual do trabalho. As tabelas de usuários e o banco de certificados não são alterados.

## Ativação no ambiente atual

O código foi aplicado na pasta do projeto. O banco operacional não foi migrado durante a implementação, e os processos existentes não foram reiniciados.

1. Encerre o portal e o worker de lembretes antes de carregar a nova versão; não mantenha versões diferentes atendendo o mesmo banco.
2. Inicie o portal e o agendador pelos procedimentos já utilizados. Não é necessário reinstalar a tarefa Windows nem instalar novas bibliotecas.
3. O primeiro acesso ao banco pela nova versão cria o backup e aplica a migração.
4. Confira o indicador do agendador, o calendário de Sorriso e o e-mail do dono das novas tarefas críticas.
5. Cadastre os modelos compartilhados e, se necessário, as datas adicionais do escritório.

Retorno à versão anterior exige parar os dois processos, restaurar em conjunto o código anterior e o banco do backup pré-migração. Não use código antigo com banco v3. Alterações feitas depois do backup não estarão na cópia antiga.

## Validação

Testes em bancos temporários e SMTP simulado: recorrência anterior, concorrência, migração v1/v2, preservação de histórico, rollback, backup, alertas, idempotência, conclusão, autorização, CSRF, categorias, modelos e inventário somente de leitura.

Teste adicional em Chromium, com servidor local e usuários fictícios: aplicar modelo com múltiplos links/dias, cadastrar tarefa crítica, conferir edição, filtrar dashboard e concluir tarefa; layout do formulário em 1440 e 390 pixels e ausência de erros JavaScript.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s apps/lembretes_tarefas/tests -v

# Inclui teste de navegador, se o Chromium do Playwright estiver instalado:
$env:LEMBRETES_TEST_BROWSER='1'
.\.venv\Scripts\python.exe -B -m unittest discover -s apps/lembretes_tarefas/tests -v
```

Não houve envio real de e-mail, alteração de tarefa operacional, reinicialização de serviço ou modificação de outro aplicativo durante a validação.
