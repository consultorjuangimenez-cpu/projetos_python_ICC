# Layout dos e-mails de Lembretes de Tarefas

Atualizado em 16/09/2026. Código completo: `apps/lembretes_tarefas/mailer.py`.

## Alteração

Cabeçalho ICC em azul escuro com detalhe verde, título em destaque, bloco de data e horário, descrição com espaçamento e botões para os acessos da tarefa. Alertas críticos incluem um bloco de prazo em âmbar e as categorias disponíveis. O mesmo padrão é aplicado aos e-mails de teste.

O HTML usa tabelas de apresentação, estilos inline, fontes do sistema e estrutura condicional para Outlook. Não depende de imagens, fontes remotas ou JavaScript. Telas estreitas recebem ajustes de espaçamento e os campos de data/horário são empilhados. Clientes sem suporte a cantos arredondados apresentam cantos retos.

Os acessos são apresentados em botões compactos de largura uniforme, definida pelo maior texto de cada e-mail e limitada ao espaço disponível. O grupo fica alinhado à esquerda, com os textos centralizados, sem repetir o endereço abaixo dos botões. Para caminhos de rede bloqueados pelo cliente de e-mail, a orientação é consultar o endereço no cadastro da tarefa e abrir pelo Explorador de Arquivos. Conteúdo informado pelo usuário permanece escapado. A alternativa em texto simples é preservada com os endereços, pois não possui botões.

## Impactos e ativação

Não há migração nem alteração do banco, das regras de agendamento, dos destinatários, dos assuntos ou do transporte SMTP. Somente o gerador de HTML foi alterado. A tarefa Windows `ICC_Lembretes_Tarefas` foi reiniciada para carregar o código atualizado; o portal não precisou ser reiniciado. E-mails já recebidos mantêm a aparência anterior.

## Verificação

- Suíte existente: 88 testes identificados, 87 passaram e 1 teste opcional de navegador não foi executado nessa rodada.
- Conferência adicional em Chromium: lembrete, alerta crítico, teste sem links e conteúdo longo com caminho de rede, em larguras de 900 e 390 pixels, sem rolagem horizontal.
- Prévias visuais conferidas; arquivos HTML, PNG e EML em `previa_email/`. Os exemplos usam destinatário fictício e não foram enviados.
- Agendador verificado após a reinicialização, com novo processo, heartbeat atualizado e credencial SMTP disponível.

A renderização em Outlook/Gmail reais não foi testada nesta etapa; a conferência visual foi feita no navegador. Os arquivos EML permitem abrir a amostra localmente em um cliente de e-mail.
