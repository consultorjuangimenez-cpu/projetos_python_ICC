# Arquivos a adaptar e preservar

Inventário técnico de 16/09/2026. As alterações abaixo são **futuras**, propostas para a construção da base e para apps opcionais. Nesta Etapa 1 foram criados somente os cinco documentos de diagnóstico.

## Núcleo e distribuição comum

| Arquivo existente | Motivo concreto | Alteração proposta | Preservação/validação |
|---|---|---|---|
| `servidor.py` | Delega ao bootstrap atual | Manter entrada simples, ajustando somente integração com factory/configuração se necessária | Compatibilidade do comando de início |
| `portal/servidor.py` | Importa catálogo/instancia persistência no escopo global; mistura WSGI, console e navegador | Separar montagem, preparação de instalação e execução; parametrizar servidor | Rotas `/`, `/saude`, login e `application` WSGI compatíveis |
| `portal/settings.py` | Exige pasta de documentos global; lê só um INI | Configuração de instalação neutra e paths comuns; opções de app não obrigatórias no núcleo | Interpretação do `config.ini` ICC durante transição |
| `portal/integracao.py` | Loader global separado e caminhos de apps | Resolver opções por instalação com precedência documentada | Manter `caminho()` ou adaptador para os apps atuais |
| `portal/catalogo.py` | Rejeita catálogo sem ativos | Aceitar `[]` mantendo validação de rota/módulo/duplicidade | Não ampliar importação arbitrária nem liberar apps sem permissão |
| `portal/acesso.py` | Cookie tem nome ICC; contratos usados por todos os apps | Parametrizar identidade de sessão e manter hooks | `g.usuario`, CSRF, revogação e autorização por rota |
| `portal/usuarios.py` | Inicialização escreve chave/esquema; dados compartilhados logicamente com apps | Preparação explícita e diretório configurável; avaliar política de senha | Não recriar usuários/IDs nem trocar esquema/chave ICC sem plano |
| `portal/primeiro_admin.py` | Bootstrap de console usa política atual | Alinhar política e mensagens ao núcleo genérico | Sem credencial padrão e sem cadastro público |
| `portal/tarefas.py` | Usa `BASE_DIR/dados` e limites fixos locais ao processo | Consumir caminhos/limites da instalação; preservar protocolo worker | Posse de resultados, timeout, locks e confinamento de downloads |
| `portal/verificar.py` | Lista fixa de caminhos/apps ICC | Verificar núcleo e apenas integrações selecionadas, sem efeitos persistentes | Não iniciar apps/worker nem expor valores sensíveis |
| `portal/atualizar_pacote.py` | Mesclagem ligada a arquivos específicos de atualização | Tornar pacote versionado e preservação explícita de configuração/estado | Backups, idempotência e conflito de rotas; não incluir banco em pacote |
| `portal/templates/portal.html` | Marca ICC fixa e layout próprio | Receber identidade da configuração | Menu, iframe, links administrativos e saída CSRF |
| `portal/templates/conta_base.html`, `login.html`, `senha.html`, `usuarios.html`, `usuario_editar.html`, `acesso_negado.html` | Interface do núcleo e contexto de autenticação | Revisar marca e padronizar integração visual conforme necessidade | Campos, mensagens e tokens de segurança |
| `aplicativos.json` | Catálogo da instalação, com 12 apps | Exemplo/base vazio; catálogo real independente por cliente | Arquivo atual ICC e flags ativo/inativo preservados |
| `config.ini`, `config_apps.ini` | Caminhos, SMTP e URL específicos | Criar exemplos neutros, documentar opções; reais ficam na instalação | Não sobrescrever os atuais ao atualizar código |
| `requirements.txt`, `requirements-lembretes.txt` | Núcleo e dependências de negócios parcialmente misturados | Separar conjunto mínimo e opcionais, fixar versões homologadas | Reproduzir versão ICC antes de alterar ambiente |
| `.gitignore` | Exclusões não impedem conteúdo já rastreado; `Release/` não cobre tudo | Revisar exclusões e acrescentar auditoria de distribuição por lista permitida | Nenhum `git rm`, reset ou alteração de histórico executado nesta etapa |

## Scripts e infraestrutura

| Arquivo/pasta | Adaptação necessária |
|---|---|
| `1_instalar.bat` | Instalação da base e dependências opcionais; validar versão suportada de Python |
| `2_iniciar_portal.bat` | Remover credenciais literais na versão futura; selecionar inicialização coerente com HTTPS/configuração |
| `3_liberar_firewall.bat`, `4_remover_regra_firewall.bat`, `firewall.ps1` | Parametrizar regra/porta; contemplar entrada HTTPS conforme perfil, mantendo escopo de rede restrito |
| `5_instalar_navegador_guias.bat` | Pertencer ao pacote opcional Emitir Guias; vincular instalação do navegador à conta de execução |
| `6_verificar_configuracao.bat` | Chamar verificação genérica somente leitura |
| `ATUALIZAR_PORTAL.bat` | Definir pacote/versão e sequência de atualização sem sobrescrever configuração/dados |
| `https_icc/backend.py`, `https_icc/https_icc.py`, `https_icc/Caddyfile`, BATs associados | Remover IP/porta/storage fixos e dependência obrigatória de Certificados; produzir infraestrutura genérica com compatibilidade ICC |
| `apps/certificados/COMPLEMENTO_HTTPS/` | Consolidar modelos/instaladores com a solução HTTPS escolhida; preservar fontes históricas fora da base |
| `apps/distribuicao_https/`, `https_icc/distribuir/`, `https_icc/estacao/` | Gerar confiança/auxiliar para cada instalação; não reaproveitar pacotes da ICC |
| `ferramentas_lembretes/Instalar_Agendador.ps1`, `Rodar_Agendador.ps1`, `Configurar_SMTP.ps1`, BATs e `instalar.py` | Parametrizar tarefa, conta, remetente e caminhos; credencial Windows deve ser configurada novamente no destino |
| `README.md`, `LEIA-ME.txt`, `LEIA-ME_ATUALIZACAO.txt`, documentos operacionais | Atualizar após implementação, distinguindo instalação limpa, atualização ICC e apps opcionais |

## Aplicativos: mudanças condicionadas à reutilização

Nenhum app de negócio precisa entrar no núcleo para concluir sua extração. Os arquivos abaixo exigem análise/adaptação antes de distribuir o respectivo app a outro cliente.

| App e arquivos | Adaptação principal |
|---|---|
| `apps/aberturas/app.py` | Planilha e destinatários locais; variável de segredo específica da conta; revisar escrita na planilha e relatórios |
| `apps/analise_emails/app.py`, `worker.py`, `processamento.py` | Configuração de origem, formato dos logs e caminhos/saída através do contrato da instalação |
| `apps/buscar_nfe/app.py`, `worker.py` | Raiz/organização HUB SIEG e ano; dados de entrada e resultados exclusivos do cliente |
| `apps/buscar_pdf/app.py` | Receber raiz opcional de documentos e logger sem depender de configuração obrigatória do núcleo |
| `apps/buscar_pdf_cnpj/app.py`, `config.json`, `src/configuracao.py`, `src/indice_pdf.py`, `src/logs.py` | Eliminar fallback ICC, controlar preparação do índice e usar dados/logs da instalação |
| `apps/carta_frete/app.py`, templates/estáticos | Validar compatibilidade do formato de relatório e empacotar dependências próprias; sem acoplamento ICC obrigatório identificado na entrada principal |
| `apps/emite_guia/app.py`, `worker.py`, `processamento.py` | Contrato de arquivos/execuções, navegador e endpoints SEFAZ/MT; homologar sem emissão real no teste |
| `apps/monitora_sieg/app.py`, `confronto.py` | Caminhos e semântica do relatório ICC; validar layouts com o cliente destinatário |
| `apps/planilha_amanda/app.py`, `leitura_rcf.py` | Remover caminho absoluto de fallback e validar arquivos RCF/regras contábeis do destinatário |
| `apps/monitora_certificados/app.py`, `worker.py`, `processamento.py` | Manter inativo na ICC conforme catálogo; decidir necessidade do módulo legado antes de distribuir |
| `apps/certificados/core.py`, `app.py`, `conexao_https.py`, templates/estáticos e `auxiliar/` | Identidade ICC, caminhos, chave, URL, protocolo auxiliar, contratos com usuários e efeito da troca de raiz nos IDs |
| `apps/lembretes_tarefas/settings.py`, `mailer.py`, `calendar.py`, `app.py`, `clients.py`, templates | Remetente/marca, calendário municipal, dados/logs, integração opcional de clientes e nomes internos |
| `apps/lembretes_tarefas/store.py`, `schema.sql`, `migrations.py`, `worker.py` | Preservar esquema/filas; controlar preparação/migração explícita e limites da instalação; não mudar modelo de dados apenas para separar clientes |

## Preservar na ICC e excluir da distribuição base

| Item | Por que preservar | Regra de distribuição |
|---|---|---|
| `dados/usuarios.sqlite3` | Contas, IDs, permissões e sessões | Novo cliente começa com banco novo |
| `dados/chave_sessao.txt` | Assinatura de sessões existentes | Gerar chave exclusiva no novo cliente |
| `dados/apps/certificados/inventario.sqlite3` + `segredo.key` | Inventário e capacidade de decifrar senhas; auditoria/tickets | Preservar como conjunto restrito ICC; nunca copiar para cliente distinto |
| `dados/apps/lembretes_tarefas/` | Tarefas, fila, histórico, configuração, backups e credenciais de operação | Não levar registros, fila ou credenciais ao novo cliente |
| `dados/apps/buscar_pdf_cnpj/` | Índice e resultados com informações dos documentos | Gerar novo índice no destino, somente de documentos desse cliente |
| `dados/apps/aberturas/`, `dados/execucoes/` e demais dados | Relatórios, entradas, resultados e vínculos com usuários | Excluir do pacote base |
| `dados/caddy_https/` | Identidade TLS/CA da ICC | Nunca distribuir chaves privadas; nova identidade no destino |
| `config.ini`, `config_apps.ini`, `aplicativos.json`, `config.old` | Estado operacional e referência histórica | Somente exemplos sanitizados na base; histórico fica restrito |
| `logs/`, `https_icc/logs/` | Diagnóstico e histórico operacional | Excluir do pacote base; tratar conteúdo como dado do cliente |
| Pastas externas configuradas, documentos, planilhas, RCF, PFX/P12 e estado legado | Dados não contidos integralmente no repositório | Não mover nem substituir; backup/retenção próprios da ICC |
| `Releases/`, `apps/certificados/Release/`, `portal/Certificados_Portal_ICC/` | Referências e versões anteriores, potencialmente com dados | Preservar sob controle local; não usar como fonte automática do pacote |
| `.venv/`, caches Python e `Portal APPs.lnk` | Ambiente/atalho da instalação atual | Recriar ambiente e atalhos no cliente destinatário |

As chaves expostas ao rastreamento Git podem exigir rotação após avaliação. “Preservar” aqui significa evitar perda de acesso e alteração fora do escopo, não recomendar reutilização indefinida de segredo potencialmente exposto.

## Arquivos novos previstos, ainda não criados

Exemplos neutros de configuração, modelos HTTPS, manifesto de arquivos/versão e testes do núcleo/isolamento deverão surgir na Etapa 2 proposta. Os nomes da árvore em PLANO_PORTAL_BASE são sugestões. Não criar um instalador baseado em cópia recursiva da instalação ICC.

Os documentos internos desta Etapa 1 contêm topologia e referências da ICC. Devem apoiar a execução do projeto, mas não ser enviados automaticamente em um pacote comercial para outro cliente.
