# Diagnóstico técnico do Portal de Aplicações — Etapa 1

Data: 16/09/2026. Projeto analisado: `C:\C\Projetos_Phyton\Portal_Apps`.

## Resultado

O portal pode evoluir para uma base reutilizável sem reescrita completa. Já existem catálogo declarativo, montagem de aplicações Flask, autenticação central, permissões por rota e processamento isolado por execução. A principal mudança necessária é separar código comum de configurações, aplicativos e dados de cada instalação.

O diretório atual **não é um pacote adequado para distribuição a outro cliente**: contém configurações da ICC, bancos, material criptográfico, resultados e pacotes antigos. Há arquivos sensíveis rastreados pelo Git apesar das regras de exclusão existentes. Uma cópia integral também levaria aplicativos que o novo cliente não necessariamente utiliza.

Esta etapa produziu somente os cinco documentos solicitados. Não foram iniciados servidores, executados aplicativos, enviados e-mails, processados documentos de clientes, aplicadas migrações ou alteradas configurações de produção.

## Método e evidências

- Inspeção do código, catálogo, configurações com valores sensíveis omitidos, scripts e nomes/metadados dos arquivos locais.
- Consulta da estrutura de cinco bancos operacionais por SQLite com URI `mode=ro&immutable=1` e `PRAGMA query_only=ON`: somente metadados de tabelas e colunas, sem registros de negócio, usuários, hashes ou credenciais. Nenhum WAL desses cinco bancos estava presente no instante da leitura.
- Identificação de backup de Lembretes com esquema v2 e WAL; ele não foi usado como evidência do estado do banco ativo, que apresenta `user_version=3`.
- Inspeção do inventário Git e das dependências instaladas. Documentação antiga foi tratada como apoio, com prioridade para o código atual.
- O diagnóstico não importou `portal.servidor`: a importação instancia usuários e aplicativos, podendo criar/alterar bancos, chaves, índices e logs.

No início já havia alterações locais em `dados/usuarios.sqlite3`, `dados/apps/certificados/inventario.sqlite3` e dois arquivos de cache Python não rastreados em `apps/emite_guia/__pycache__/`. Esses arquivos não foram editados por este trabalho. A análise não pressupõe que processos externos tenham ficado parados.

Na conferência final, os 352 arquivos rastreados monitorados por SHA-256 mantiveram o conteúdo observado antes da redação. O estado Git apresentou somente os cinco documentos novos além das alterações preexistentes. Os documentos passaram pela conferência de UTF-8, links locais, blocos de código e ausência dos dois valores literais de senha identificados, comparados apenas em memória. Não foram executados testes funcionais.

## Arquitetura existente

`servidor.py` delega a `portal.servidor.main`. O módulo carrega `aplicativos.json`, importa os apps ativos e compõe o WSGI com `DispatcherMiddleware`. Cada app exporta `app`; a integração de acesso exige que seja uma instância Flask. Não é uma coleção de Blueprints.

O catálogo tem **12 entradas: 11 ativas e uma inativa**, `monitora_certificados`. A interface principal usa um iframe, com menu filtrado por permissão. A autorização também é aplicada às requisições dos aplicativos.

Há dois caminhos de inicialização: o servidor direto em loopback, normalmente porta 8080, e o complemento HTTPS com Caddy em `10.10.10.154:443`, encaminhando para Waitress em `127.0.0.1:8081`. O segundo é compatível com o endereço informado para a ICC; o processo efetivamente em execução não foi inspecionado.

O núcleo utiliza `dados/usuarios.sqlite3`; os apps mantêm outros bancos SQLite, arquivos JSON, planilhas, arquivos temporários e resultados. O agendador de Lembretes é um processo separado. Detalhamento em [ARQUITETURA_ATUAL.md](ARQUITETURA_ATUAL.md).

## Dependências específicas da ICC

| Elemento observado | Evidência | Externalização necessária |
|---|---|---|
| Nome ICC na interface e no cookie | `portal/templates/portal.html:5`, `:12`; `portal/acesso.py:24` | Nome, identidade visual e identificador de sessão por instalação |
| Raiz de documentos em unidade F: | `config.ini:32`, `config_apps.ini:3`; `apps/buscar_pdf_cnpj/config.json:7` | Diretório de documentos por cliente; eliminar fallback apontando à ICC |
| XMLs do HUB SIEG em Y: e ano 2026 | `config_apps.ini:9`, `:11` | Raiz e ano/critério temporal por instalação |
| Unidades A: e G: para certificados e relatórios | `config_apps.ini:23`, `:31`, `:71`, `:73` | Caminhos por app e conta de execução; preferir UNC validado onde necessário |
| Servidor `SRVPROSOFT`, compartilhamentos `Arquivos_ICC` e `g/programas` | `config_apps.ini:17`, `:81`, `:83`, `:97` | Compartilhamentos e permissões de rede por cliente |
| Caminho absoluto para estado legado de certificados | `config_apps.ini:95` | Tornar integração legada opcional e específica da ICC |
| Caminho absoluto de RCF da Planilha Amanda | `apps/planilha_amanda/app.py:44` | Configurar `[amanda].pasta_rcf`; a seção está ausente no `config.ini` atual |
| IP, origem pública e armazenamento TLS fixos | `https_icc/Caddyfile:5`, `:6`, `:12`; `https_icc/https_icc.py:20`; `config_apps.ini:101` | URL pública, bind, portas, armazenamento e CA próprios |
| SMTP KingHost, remetentes e destinatários locais | `config_apps.ini:41-49`; `apps/aberturas/app.py:63-70` | Configuração de envio por cliente; nenhuma conta real no pacote base |
| Duas atribuições de senha SMTP literais no iniciador | `2_iniciar_portal.bat:4-5` | Obter segredos no ambiente/cofre da instalação; não distribuir o script atual |
| Remetente de Lembretes fixo no código | `apps/lembretes_tarefas/settings.py:9`, `mailer.py` | Separar remetente, nome de exibição e usuário de autenticação SMTP |
| Feriados obrigatórios de Sorriso e fuso local | `apps/lembretes_tarefas/calendar.py:39-45`, `settings.py` | Calendário municipal e fuso por cliente |
| Tarefa Windows e regra de firewall com nomes ICC | `ferramentas_lembretes/Instalar_Agendador.ps1:3`; `firewall.ps1:8` | Identificadores únicos por instalação |
| Auxiliar de certificados e protocolo `icc-cert://` | `apps/certificados/app.py:174-202`, `auxiliar/` | Perfil e identificação por instalação; avaliar coexistência na mesma estação |

As letras de unidade são valores encontrados na configuração. Não foi verificado se correspondem a discos locais ou mapeamentos ativos. O endereço de exemplo com domínio ICC em `config_apps.ini:99` é comentário; a URL configurada é a baseada no IP. Endpoints de SEFAZ/MT pertencem à integração do app Emitir Guias, não à identidade do portal; sua disponibilidade não foi testada.

## Classificação dos componentes

As categorias podem se sobrepor: um código reutilizável pode exigir adaptação e produzir dados que não devem ser distribuídos.

| Categoria | Componentes | Tratamento proposto |
|---|---|---|
| **A — Núcleo reutilizável** | `servidor.py`; `portal/servidor.py`, `catalogo.py`, `acesso.py`, `usuarios.py`, `primeiro_admin.py`, `tarefas.py`; templates de conta | Reaproveitar comportamento e contratos, com parametrização e inicialização controlada |
| **B — Configurações do cliente** | `config.ini`, `config_apps.ini`, `aplicativos.json`, configuração de Lembretes, Caddy, SMTP, caminhos, calendário, tarefas Windows | Preservar na ICC; distribuir somente exemplos neutros na base |
| **C — Aplicativos da instalação ICC** | Os 12 módulos cadastrados; prioritariamente Aberturas, Planilha Amanda, Monitora SIEG e rotinas legadas de certificados | Manter no perfil ICC. Nenhum será incluído automaticamente no Portal_Base |
| **D — Dados não distribuíveis** | `dados/`, `logs/`, planilhas/documentos externos, certificados PFX/P12, chaves, credenciais XML, filas, índices, relatórios, backups e releases com dados | Exclusão explícita do pacote base; retenção/backup restritos ao cliente de origem |
| **E — Componentes a adaptar** | `settings.py`, `integracao.py`, catálogo vazio, inicialização, marca/cookie, scripts HTTPS/firewall, instaladores/atualizador, remetente/calendário, contratos entre apps | Adaptações incrementais em ambiente separado, com critérios de aceitação |

“Aplicativo da ICC” identifica o escopo atual da instalação, não uma conclusão sobre exclusividade comercial ou titularidade. Carta Frete, buscadores e Lembretes têm partes potencialmente reutilizáveis, mas devem ser pacotes opcionais, após revisão de regras e configuração. Não há evidência suficiente para prometer reutilização integral em qualquer cliente.

## Riscos priorizados

| Prioridade | Achado e consequência | Encaminhamento para planejamento |
|---|---|---|
| Alta | Senhas literais no iniciador; banco de usuários, chave de sessão, chave Fernet e material TLS constam entre arquivos rastreados. Copiar diretório/repositório pode copiar identidades e dados. | Construir pacote por lista permitida. Avaliar acesso ao repositório, histórico e rotação das credenciais/chaves com plano específico. Não foi afirmado comprometimento externo. |
| Alta | `.gitignore` não remove arquivos já rastreados; existem dados também em `Releases/` e cópias aninhadas. | Conferir conteúdo final do pacote, não confiar apenas em exclusões Git ou no nome da pasta. |
| Alta | Importar o portal pode criar bancos/chaves; Lembretes pode migrar na criação do Store e o buscador CNPJ prepara índice ao importar. | Isolar diagnóstico/testes; separar preparação persistente da montagem da aplicação. |
| Alta | Copiar fila de Lembretes e iniciar outro worker pode gerar envios indevidos ou duplicados entre instalações. | Novo cliente começa sem fila/histórico da ICC; manter worker desabilitado na homologação até configuração local. |
| Alta | IDs de usuários são referenciados por outros bancos/arquivos; permissões usam a rota como identidade. | Preservar IDs e rotas na evolução ICC. Não recriar usuários ou renomear rotas silenciosamente. |
| Alta | `certs.id` deriva do caminho normalizado do arquivo e senhas cifradas dependem de `segredo.key`. | Planejar mudança de raiz e backup conjunto banco/chave; nunca substituir chave da ICC pela de outra instalação. |
| Média | Catálogo não aceita zero apps e um erro de importação pode impedir a subida de todo o portal. | Base deve funcionar vazia, sem reduzir validação/autorização dos apps configurados. |
| Média | Núcleo exige `[documentos].pasta_clientes` mesmo sem buscador. Configurações são lidas por caminhos e precedências diferentes. | Retirar dependência obrigatória de documentos do núcleo e documentar resolução única. |
| Média | Cookie exige HTTPS, mas iniciador direto abre HTTP. Complemento HTTPS usa porta e fluxo próprios. | Unificar perfis de inicialização, mantendo o caminho ICC vigente até homologação. |
| Média | Aplicações compartilham processo/ambiente e privilégios Windows; limites de execução são locais ao processo. | Instalações independentes com ambiente, diretórios, contas e portas próprios; não tratar pasta de app como isolamento de segurança. |
| Média | Política atual aceita senhas de quatro caracteres; backend HTTPS não inclui `x-forwarded-for` entre cabeçalhos confiáveis. | Rever política e comportamento de bloqueio por IP em homologação; acessos pelo proxy podem compartilhar o IP observado. |
| Média | Remetente de Lembretes, feriados municipais e RCF têm comportamento fixo da ICC. | Parametrizar antes de disponibilizar esses apps para outro cliente. |
| Média | Auditoria/logs variam por app; não foi localizado registro central completo das alterações de usuários e permissões. | Definir política de auditoria, retenção e mascaramento como evolução planejada. |

## Preservação e proposta

O Portal_ICC deve manter catálogo, caminhos, banco de usuários, IDs, permissões, bancos dos apps, filas, chave de sessão, chave de certificados e configuração HTTPS até uma mudança controlada. Preservar operacionalmente não significa autorizar redistribuição. Eventual rotação de segredos é uma ação separada, não executada aqui.

O Portal_Base conterá núcleo, interface neutra, configuração de exemplo, instaladores genéricos e catálogo vazio. Cada cliente receberá uma instalação independente e apenas seus apps e dados. Não haverá banco multiempresa compartilhado nem necessidade inicial de trocar Flask, Waitress ou SQLite.

- Estrutura e plano detalhado da Etapa 2: [PLANO_PORTAL_BASE.md](PLANO_PORTAL_BASE.md).
- Arquivos a adaptar e preservar: [ARQUIVOS_MODIFICAR.md](ARQUIVOS_MODIFICAR.md).
- Critérios de preparação, homologação e futura migração: [CHECKLIST_MIGRACAO.md](CHECKLIST_MIGRACAO.md).

## Limites da verificação

Não foram verificados: processo/versão efetivamente em produção; serviços e tarefas Windows registrados; regras de firewall ativas; acessibilidade e ACLs dos compartilhamentos; validade das credenciais SMTP; entrega de e-mails; confiança TLS nas estações; funcionamento do auxiliar; disponibilidade de serviços externos; conteúdo de PFX, documentos e registros de usuários; integridade lógica completa dos bancos; restauração de backups; conteúdo integral de todos os arquivos compactados; exposição passada no histórico Git; execução de testes funcionais e carga.

As estruturas SQLite são fotografias de metadados locais, não auditoria de dados nem garantia de consistência durante atividade concorrente. As etapas 3 a 5 ainda não foram fornecidas. A Etapa 2 descrita neste conjunto é uma proposta técnica para revisão, não execução ou substituição de instruções futuras.
