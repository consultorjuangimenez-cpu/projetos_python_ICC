# Plano técnico para Portal_Base

Proposta de 16/09/2026. **Somente planejamento; Etapa 2 não implementada.** O projeto tem cinco etapas; os enunciados das etapas seguintes ainda não foram recebidos.

## Decisão arquitetural

Manter Python, Flask, Waitress, SQLite local, catálogo JSON e os módulos atuais. O catálogo já desacopla o menu dos módulos e o núcleo já centraliza controle de acesso. A separação por instalação atende ao objetivo sem banco multiempresa, tenant ID, nova SPA, microserviços ou reescrita do produto.

O Portal_Base será uma distribuição versionada de código comum e exemplos neutros. Portal_ICC e Portal_Cliente_X serão instalações completas independentes desse código, cada uma com sua configuração, ambiente, identidade, apps selecionados, dados e segredos. Elas não executarão código por um link compartilhado para a pasta do Portal_Base, evitando que uma edição atualize todos os clientes sem controle.

Inicialmente, manter a disposição atual de diretórios reduz mudanças: `portal/`, `apps/`, `dados/`, `logs/` e INIs na raiz de cada instalação. Centralizar a resolução desses caminhos permite evoluir depois para diretórios de dados externos. Nesta proposta, nenhuma mudança física na ICC é pré-requisito para construir a base.

## Estrutura proposta

```text
Portal_Base/                         # fonte/pacote comum, sem estado de cliente
  servidor.py
  portal/
    servidor.py                     # montagem controlada por factory
    settings.py                     # configuração neutra e caminhos da instalação
    integracao.py
    catalogo.py
    acesso.py
    usuarios.py
    primeiro_admin.py
    tarefas.py
    verificar.py
    atualizar_pacote.py
    templates/                      # identidade parametrizada
  apps/
    __init__.py                     # nenhum app ICC incluído por padrão
  aplicativos.json                 # [] aceito após adaptação do carregador
  config.exemplo.ini
  config_apps.exemplo.ini
  requirements.txt                 # dependências do núcleo
  instalar.bat                     # nomes propostos
  iniciar.bat
  infraestrutura/
    Caddyfile.modelo
    configurar_https.py
  docs/                            # documentação neutra de instalação/contratos

Portal_ICC/                          # nome lógico; preservar caminho atual inicialmente
  portal/                           # versão homologada do núcleo
  apps/                             # aplicativos ICC selecionados
  aplicativos.json                  # catálogo atual, inclusive ativo/inativo
  config.ini
  config_apps.ini
  .venv/
  dados/                            # usuários, bancos, chaves, filas e execuções ICC
  logs/
  https_icc/                        # compatibilidade até adaptação específica
  ferramentas_lembretes/            # se o app estiver instalado

Portal_Cliente_X/
  portal/                           # cópia da versão aprovada do núcleo
  apps/                             # somente apps contratados/homologados
  aplicativos.json                  # catálogo próprio
  config.ini
  config_apps.ini
  .venv/
  dados/                            # gerado novo, sem qualquer conteúdo da ICC
  logs/
  infraestrutura/                   # HTTPS, portas e identidade próprios
```

As pastas e scripts propostos ainda não foram criados. `Portal_ICC` não implica renomear agora `C:\C\Projetos_Phyton\Portal_Apps`, pois há caminhos absolutos, tarefas e configuração TLS dependentes dele.

## Contratos a preservar e ampliar

1. **App:** manter `apps.<slug>.app` exportando uma instância Flask em `app`, com rotas relativas e recursos por `url_for`. Adotar factory opcional para testes/inicialização sem quebrar os módulos existentes.
2. **Acesso:** manter `g.usuario` com `id`, `name`, `admin` e `routes`, helpers de sessão/CSRF e validação central em URLs diretas. Apps opcionais não devem substituir hooks de segurança.
3. **Identidade:** preservar rotas da ICC, pois são chaves de autorização. Não introduzir novo `app_id` ou migrar permissões como requisito inicial.
4. **Configuração:** documentar fonte, precedência, tipo e obrigatoriedade de cada opção. Conservar leitores de compatibilidade para os INIs atuais durante transição.
5. **Persistência:** nenhuma atualização de código substitui `dados/`, chaves, filas ou configurações do cliente. Inicialização de banco novo deve ser explícita e vinculada à instalação selecionada.
6. **Workers:** executar no ambiente e conta da instalação correspondente, com namespace próprio para locks/tarefas. Não iniciar workers de envio automaticamente ao extrair um pacote.
7. **Atualização:** pacote versionado com lista de arquivos de código; configurações existentes são preservadas. Novas opções entram como defaults neutros ou passos documentados, nunca valores da ICC.

## Configurações a externalizar

| Grupo proposto | Conteúdo | Compatibilidade necessária |
|---|---|---|
| Identidade do portal | Nome da organização, título, logo, cores e identificador da instalação | Remover literals ICC dos templates; manter aparência ICC via configuração |
| Servidor | Host interno, porta, URL pública, perfil HTTPS e proxy confiável | Preservar loopback e confiança restrita; não confiar indiscriminadamente em cabeçalhos enviados pelo cliente |
| Sessão | Nome do cookie por instalação e flags seguras | Migração do nome invalida sessões existentes; planejar janela de login, não fazê-la silenciosamente |
| Diretórios | Raiz da instalação, dados, logs e temporários | Defaults relativos; apps devem consumir a mesma resolução, inclusive Certificados e Lembretes |
| Apps | Catálogo, caminhos, opções e dependências por app | Nenhum caminho obrigatório de documentos no núcleo se o buscador não estiver instalado |
| SMTP | Host, porta, TLS, remetente, nome de exibição e destinatários autorizados | Distinguir autenticação de identidade do remetente; remover variável específica de pessoa do contrato comum |
| Regionalização | Fuso e feriados municipais | Não acrescentar Sorriso automaticamente a outro cliente |
| Operação Windows | Conta, nome de tarefa/serviço, regra de firewall, perfil do auxiliar | Evitar colisões entre duas instalações na mesma máquina/estação |

Segredos ficam em mecanismo da própria instalação, como ambiente protegido ou credencial Windows vinculada à conta de serviço. Arquivos de exemplo conterão nomes e instruções, sem valores reais. A chave de sessão e a chave de Certificados devem ser criadas novas no novo cliente. A CA HTTPS também deve ser própria quando adotado o modelo de CA interna.

Uma simples troca do IP ou de `config.ini` não atende: o código atual tem loaders diferentes, defaults absolutos, remetente fixo, calendário municipal e scripts especializados em certificados.

## Escopo proposto e detalhado da Etapa 2

Objetivo proposto: produzir uma base neutra verificável em ambiente separado, preservando a instalação ICC. Ajustar este plano ao enunciado da Etapa 2 quando ele for fornecido.

| Passo | Trabalho previsto | Entrega verificável / aceite |
|---|---|---|
| 2.1 — Preparar trabalho isolado | Selecionar versão de origem; inventariar arquivos por lista permitida; criar área de desenvolvimento separada com dados sintéticos | Nenhum banco, chave, log, resultado, credencial, release histórico ou `.venv` ICC presente no pacote de trabalho distribuível |
| 2.2 — Definir configuração comum | Parametrizar marca, sessão, URL/portas e caminhos; separar opções de documentos/apps; definir precedência e validação | Base abre configuração neutra sem servidor, unidade ou conta da ICC; perfil de compatibilidade interpreta os INIs existentes |
| 2.3 — Controlar inicialização | Introduzir factory/fluxo explícito de preparação; conservar entrada WSGI/CLI de compatibilidade | Validação estática não cria banco/log/chave; inicialização nova grava somente no diretório da instalação de teste |
| 2.4 — Aceitar catálogo vazio | Remover apenas exigência de pelo menos um app; preservar validações de módulos, duplicatas e rotas reservadas | Login, administração e tela de nenhum app funcionam com `[]`; app inválido gera erro claro sem reduzir segurança |
| 2.5 — Neutralizar interface e instaladores | Parametrizar templates; separar dependências do núcleo das opcionais; criar exemplos sem valores reais | Instalação mínima usa só dependências comuns; instalar app acrescenta suas dependências sem impor toda a pilha ICC |
| 2.6 — Definir HTTPS genérico | Retirar dependência de Certificados do bootstrap HTTPS; parametrizar URL, portas e storage; manter adaptador ICC | Duas configurações de homologação usam nomes/portas/CA/diretórios independentes; backend continua inacessível externamente por bind direto |
| 2.7 — Tornar diagnóstico/pacote previsíveis | Adaptar verificador aos apps selecionados; manter atualização preservando estado; conferir lista de distribuição | Verificação não acessa integrações ausentes; pacote não contém dados/segredos; incompatibilidades não sobrescrevem configuração |
| 2.8 — Homologar núcleo | Usar usuários/arquivos sintéticos; testar login, administração, CSRF, autorização direta, isolamento e um app de teste | Critérios de aceite registrados; nenhum acesso de homologação às pastas/SMTP ICC |
| 2.9 — Preparar compatibilidade ICC | Comparar contratos, rotas, loaders e scripts; listar ajustes futuros dos apps sem mover dados | Relatório de compatibilidade e retorno, com pendências explícitas; nenhuma implantação automática na ICC |

Apps específicos entram como trabalho condicionado à seleção do cliente. Não é necessário generalizar todos os 12 para entregar o núcleo. Para disponibilizar Lembretes, sua configuração de remetente/calendário deve ser resolvida; para Certificados, devem ser resolvidos auxiliar, CA, URL, caminho e acesso ao esquema central. Os códigos desses apps permanecem fora da base mínima.

## Critérios de aceitação da base

- Funcionar com catálogo vazio e novo administrador definido pelo operador, sem conta ou senha padrão.
- Instalações A e B com bancos, chaves, cookies, dados, logs, URLs e tarefas independentes; autenticação de uma não dá acesso à outra.
- Ausência de literais operacionais da ICC nos exemplos e arquivos comuns; referências históricas só na documentação interna de diagnóstico, excluída da distribuição genérica quando contiver detalhes do ambiente.
- App montado protegido por login, permissão e CSRF; URLs de APIs/downloads sem permissão bloqueadas.
- Instalação de app opcional não libera acesso automaticamente a usuários comuns.
- Configurações faltantes produzem mensagens úteis sem imprimir segredos.
- Atualização de código não substitui estado/configuração do cliente; restauração ensaiada em ambiente de teste antes de qualquer evolução de produção.
- Versão do núcleo e compatibilidade dos apps registradas no pacote; suporte às versões de Python deve ser testado, não inferido apenas do instalador atual.

## Preservação e retorno da ICC

Não copiar a ICC inteira para criar novo cliente. Para futura atualização da própria ICC, fazer backup consistente dos bancos e arquivos associados, com tratamento de WAL e interrupção controlada dos writers/worker quando necessária. Guardar configurações, catálogo, código vigente e chaves sob acesso restrito. Não usar cópia simples de banco ativo como única estratégia de backup.

Preservar usuários e seus IDs, permissões por rota, filas e histórico de Lembretes, inventário e chave Fernet. Não mover pastas de certificados sem avaliar o identificador derivado do caminho. Mudanças de protocolo do auxiliar ou cookie exigem compatibilidade/transição nas estações.

Se não houver mudança de esquema, retorno pode usar o código/configuração anteriores preservando os dados compatíveis. Se futuramente houver migração, o retorno precisa de par código/esquema compatível e plano para os dados criados após o backup; restaurar cegamente o banco pode perder informações ou duplicar envios. Esse procedimento deverá ser detalhado na etapa que autorizar migração/implantação.

## Fora da execução desta etapa

Não foram criados Portal_Base/Portal_Cliente_X, alterados arquivos funcionais, trocadas credenciais, removidos arquivos do Git, reescrito histórico, reinstaladas dependências, modificados bancos, emitidos certificados ou publicados serviços. Essas ações constam como propostas condicionadas ao escopo das próximas etapas.
