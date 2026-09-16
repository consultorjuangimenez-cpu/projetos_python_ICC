# Validação da entrega

Data: 15/09/2026. Versão 1.1.0. Resultado: **71 testes Python e 6 testes JavaScript aprovados, sem falhas**.

Ambiente executado: Linux, Python 3.12.14, Flask 3.1.3, Waitress 3.0.2 e tzdata 2026.4. Testes de integração utilizaram os arquivos reais de autenticação, usuários e catálogo do `Portal_Apps.zip` enviado em 10/09/2026, sem carregar dados ou credenciais de produção.

## Cobertura

| Área | Casos conferidos |
|---|---|
| Colaboradores | Cadastro exclusivo de administrador, consulta por usuários autorizados, e-mail único, homônimos, pesquisa sem acento, edição concorrente, inativação e reativação |
| Preenchimento automático | Nome único, escolha explícita entre homônimos, limpeza de destinatário ao trocar nome, e-mail manual e preservação de destinatário histórico ao focar/sair do campo |
| Identidade do destinatário | Seleção relida no servidor e na transação, bloqueio de cadastro inativo/inexistente e conteúdo escapado nas opções/JSON |
| Migração | Atualização da versão 1 para 2 sem alterar registros anteriores, reexecução idempotente, rollback de esquema/versão quando ocorre falha e ausência de alterações em cascata nas tarefas/envios |
| Calendário | Dia 31 sem desvio nos meses seguintes, 29/02, dias da semana, dia mensal personalizado, intervalo de 15 dias, limites, término, horário de verão e salto de vinte anos |
| Validação | Campos obrigatórios, data/horário no passado, injeção de cabeçalhos no e-mail, links inseguros, UNC, múltiplos links e limites inválidos |
| Concorrência | 16 solicitações concorrentes e 16 reservas concorrentes geram uma única ocorrência/reserva; lock do processo exclui outra abertura |
| Retomada | Reinício não duplica ocorrência concluída; interrupção em SENDING exige conferência; fila persiste sem senha SMTP |
| Recorrência | Avanço mensal, envio único de pendência após parada, contagem de datas puladas e limite sem consumo por envio manual |
| Envio manual | Chave idempotente, confirmação, reapresentação do formulário sem duplicação e preservação da próxima execução |
| Erros | Até três tentativas temporárias; recusa definitiva; falha durante DATA sem reenvio automático; sucesso manual não esconde erro agendado |
| SMTP | HTML escapado, parte texto, Message-ID, STARTTLS, erro de autenticação/destinatário, falha de rede e erro de fechamento após aceite |
| Diagnóstico SMTP | Somente TLS/AUTH sem enviar mensagens, TLS antes da senha, ausência de credencial sem conexão, erro 535 sem resposta bruta, aceitação somente de 235, falha TLS e falha de fechamento |
| Histórico | Preservação após cancelamento, conteúdo histórico imutável, resolução explícita e teste de e-mail registrado |
| Permissões | Login e CSRF reais do portal, bloqueio por rota, isolamento do proprietário, teste SMTP exclusivo para administrador e falha fechada sem portal |
| Telas HTTP | Dashboard, formulário, detalhe, edição, confirmação, histórico, teste e cadastro de colaboradores com o prefixo de montagem correto |
| Instalação | Inclusão sem alterar outros cadastros, preservação do código central/banco/configuração/credencial fictícia, backup com transações confirmadas ainda no WAL, reinstalação idempotente e recusa de rota conflitante |

Os 15 arquivos Python passaram por análise de sintaxe. Os quatro arquivos PowerShell passaram por análise sintática com a gramática PowerShell do Tree-sitter. Essa verificação não equivale a executar os comandos nativos do Windows. Os testes JavaScript executaram a lógica de seleção com eventos simulados no Node.js.

## Limites da verificação

- Nenhuma mensagem foi transmitida a destinatários reais. Os testes SMTP usam simuladores de respostas e falhas.
- O Agendador de Tarefas, DPAPI, permissões Windows e autenticação na KingHost dependem do servidor de destino e precisam ser validados durante a instalação.
- A tentativa de inspeção visual em navegador foi bloqueada pelo ambiente de testes ao abrir o endereço local. Os templates renderizados, rotas e submissões foram testados por HTTP, mas não houve validação visual completa no navegador.
- A integração foi verificada com a versão disponibilizada em 10/09. O instalador preserva os arquivos atuais do portal e interrompe caso não reconheça sua interface de acesso/catálogo.

## Critérios de aceite no servidor

1. Executar `DIAGNOSTICAR_SMTP.bat` no servidor com a conta Windows do agendador. Conferir origem XML, usuário/servidor e autenticação OK, código 235. Reiniciar o agendador após a atualização.
2. Entrar como administrador, cadastrar um colaborador e digitar/selecionar seu nome em uma nova tarefa. Conferir o e-mail preenchido e salvar com horário alguns minutos à frente.
3. Conferir “Agendador ativo” e executar “Teste de e-mail”. Confirmar ENVIADO no histórico e recebimento na caixa de entrada.
4. Fechar o navegador e confirmar que a tarefa programada é enviada no horário previsto, considerando o intervalo de consulta de 15 segundos, a fila e a resposta do provedor.
5. Criar uma tarefa recorrente e conferir a próxima data após o primeiro aceite.
6. Executar “Enviar agora” e confirmar que a programação futura permanece igual.
7. Entrar com um usuário sem permissão e confirmar que o aplicativo permanece bloqueado. Usuários comuns devem ver somente as tarefas que criaram e consultar os colaboradores sem editar o cadastro.
8. Em uma janela de manutenção, reiniciar o servidor, confirmar a retomada do agendador sem login interativo e conferir os registros pendentes.

## Reexecutar os testes

Na pasta extraída do pacote, use o Python do portal. Em PowerShell:

```powershell
$env:LEMBRETES_PORTAL_REFERENCIA = 'C:\C\Projetos_Phyton\Portal_Apps'
& 'C:\C\Projetos_Phyton\Portal_Apps\.venv\Scripts\python.exe' -m unittest discover -s testes_lembretes -v
```

Os testes criam bancos, usuários e instalações fictícias somente em diretórios temporários. A referência do portal é lida para utilizar os módulos reais. O código central e os dados do portal de referência não são alterados.

Para reexecutar somente os testes JavaScript, com Node.js disponível:

```powershell
node --test testes_lembretes/test_colaboradores.cjs
```

Node.js é necessário apenas para essa verificação de desenvolvimento. O aplicativo instalado no portal não depende dele.
