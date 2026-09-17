# Checklist de preparação e futura migração

Data: 16/09/2026. Um item marcado indica somente trabalho concluído na Etapa 1. Os demais são critérios futuros, não comandos executados nem autorização para implantação.

## Etapa 1 — análise e documentação

- [x] Ler o enunciado e limitar execução a análise/documentação.
- [x] Identificar entrada, núcleo, catálogo, autenticação, administração e permissões pelo código.
- [x] Inventariar os 12 apps cadastrados e distinguir 11 ativos do módulo legado inativo.
- [x] Mapear cinco bancos operacionais e consultar somente metadados por conexão SQLite explicitamente somente leitura.
- [x] Identificar caminhos, unidades, servidores, SMTP, URLs, identidade e dados da ICC, sem copiar valores de segredos para documentos.
- [x] Classificar núcleo, configuração, apps ICC, dados não distribuíveis e componentes a adaptar.
- [x] Identificar material sensível rastreado e cópias históricas fora do fluxo ativo.
- [x] Documentar arquitetura proposta e plano da Etapa 2, sem implementá-la.
- [x] Gerar `DIAGNOSTICO_PORTAL.md`, `ARQUITETURA_ATUAL.md`, `PLANO_PORTAL_BASE.md`, `ARQUIVOS_MODIFICAR.md` e este checklist.
- [x] Registrar verificações pendentes e distinguir observação local de validação em produção.

## Preparar a Etapa 2 em ambiente separado

- [ ] Conciliar a proposta com o enunciado da Etapa 2 a ser fornecido.
- [ ] Definir versão de origem e área isolada para extração do núcleo.
- [ ] Montar pacote por lista permitida de código comum e exemplos neutros.
- [ ] Excluir bancos, logs, chaves, PFX/P12, credenciais, resultados, backups, releases históricos, atalhos locais e ambiente Python.
- [ ] Conferir arquivos ignorados **e** rastreados; `.gitignore` sozinho não é evidência de pacote limpo.
- [ ] Examinar histórico/acesso ao repositório em trabalho específico e planejar tratamento de segredos encontrados, sem interromper a ICC de forma improvisada.
- [ ] Documentar a precedência de configuração e a origem de todos os valores obrigatórios.
- [ ] Fazer o núcleo aceitar catálogo vazio sem exigir caminhos de apps ausentes.
- [ ] Separar montagem da aplicação e preparação persistente para que diagnósticos não migrem bancos.
- [ ] Parametrizar marca, sessão, servidor, caminhos e infraestrutura HTTPS.
- [ ] Selecionar dependências mínimas e opcionais; registrar versões efetivamente homologadas.

## Homologar Portal_Base e duas instalações independentes

- [ ] Instalar A e B em diretórios e ambientes independentes, com dados sintéticos.
- [ ] Usar identificadores, cookies, portas/hosts e tarefas Windows distintos.
- [ ] Criar novos administradores pelo procedimento local, sem conta ou senha padrão.
- [ ] Confirmar que login/sessão de A não autentica em B e que dados/arquivos não se cruzam.
- [ ] Confirmar portal funcional sem apps e adicionar um app de teste pelo catálogo.
- [ ] Validar módulos/rotas inválidos, duplicatas e prefixos reservados.
- [ ] Validar CSRF em login, administração, apps e APIs; autorização em URLs diretas e downloads.
- [ ] Verificar que alteração de permissão/desativação/troca de senha produz o efeito esperado.
- [ ] Validar prefixos em `url_for`, estáticos, formulários e iframe.
- [ ] Validar dono dos resultados e comportamento após reinício de execução em andamento.
- [ ] Confirmar que imports/verificações não criam estado fora da instalação selecionada.
- [ ] Verificar pacotes contra uma lista de exclusão de dados e uma lista permitida de arquivos, sem imprimir segredos no relatório.

## Homologar aplicativos selecionados

- [ ] Confirmar regras/layouts de planilhas e relatórios com o cliente destinatário.
- [ ] Configurar caminhos sem defaults ICC, com teste pela conta real de execução e não apenas pelo usuário interativo.
- [ ] Validar propriedade de arquivos e acesso a compartilhamentos; distinguir unidade local de mapeamento por sessão.
- [ ] Para Lembretes: configurar remetente, conta SMTP, fuso e calendário municipal; iniciar com fila vazia e transporte de teste.
- [ ] Para Lembretes: definir conta/tarefa Windows exclusiva e reconfigurar credencial protegida na máquina de destino.
- [ ] Para Certificados: gerar chave/inventário próprios; validar HTTPS, tickets, revogação e callback do auxiliar com certificados de teste.
- [ ] Para Certificados: verificar coexistência do protocolo do auxiliar entre instalações e efeito de mudanças nos caminhos/IDs.
- [ ] Para buscadores: gerar índices apenas do cliente de destino e validar isolamento de raízes/resultados.
- [ ] Para Emitir Guias: validar navegador e fluxo com ambiente/dados de teste, sem emissão real indevida.
- [ ] Executar os testes existentes pertinentes somente após garantir diretórios temporários e ausência de acesso aos dados/serviços ICC.

## Antes de futura alteração da própria ICC

- [ ] Confirmar processo em uso, forma real de inicialização, versão, portas, serviços/tarefas e conta Windows.
- [ ] Validar que o endereço público, proxy, cookie Secure, certificados e confiança das estações são coerentes.
- [ ] Inventariar configurações reais, catálogo, segredos e dependências externas sem incluí-los no pacote comum.
- [ ] Definir janela, responsável, critérios de interrupção e retorno.
- [ ] Parar/controlar writers e worker de forma planejada para backup consistente, incluindo WAL quando houver.
- [ ] Fazer backup restaurável de código, configuração, bancos, chaves e dados externos pertinentes; ensaiar restauração em ambiente restrito.
- [ ] Preservar usuários e IDs, rotas de permissão, chaves, histórico, fila e estado de envios incertos.
- [ ] Preservar caminho de instalação e raízes de certificados até haver plano explícito para mudança.
- [ ] Não reutilizar nem distribuir a CA/chaves ICC a outro cliente.
- [ ] Manter worker de homologação impedido de enviar a destinatários reais.
- [ ] Homologar compatibilidade de esquema e de apps antes de liberar versão de núcleo.

## Implantação e retorno — somente na etapa que os autorizar

- [ ] Aplicar apenas arquivos de código autorizados, preservando dados/configurações.
- [ ] Validar login, administração, permissões, catálogo, apps essenciais e logs após mudança.
- [ ] Validar proxy/TLS e fluxos de auxiliares nas estações de teste.
- [ ] Liberar worker SMTP com controle para não duplicar envios da fila.
- [ ] Registrar versão efetivamente instalada e evidências de aceite.
- [ ] Se houver falha, retornar ao par código/configuração compatível; se houver mudança de esquema, usar plano próprio de restauração e reconciliar dados posteriores ao backup.
- [ ] Não considerar rollback concluído sem conferir filas, resultados e dados produzidos após a mudança.

## Verificações que permanecem abertas

Nenhum dos itens abaixo foi executado nesta Etapa 1:

- [ ] Operação real no endereço `https://10.10.10.154`, certificados e confiança TLS das estações.
- [ ] Firewall ativo, tarefas/serviços registrados, ACLs e acessibilidade de rede sob a conta de serviço.
- [ ] Validade de credenciais e entrega SMTP, integrações externas e emissão de guias.
- [ ] Integridade de registros dos bancos, consistência transacional completa ou capacidade de restauração dos backups.
- [ ] Conteúdo completo de ZIPs/releases e histórico de exposição de segredos no Git.
- [ ] Testes funcionais, carga, comportamento com dois clientes e compatibilidade de todos os apps fora da ICC.

Esta lista não define o conteúdo das etapas 3, 4 e 5; elas dependem dos enunciados futuros. A conclusão da Etapa 1 encerra-se com o diagnóstico e os cinco documentos, sem executar os itens pendentes.
