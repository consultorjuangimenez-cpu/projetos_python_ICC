# Como adicionar um aplicativo

Cada aplicativo ocupa uma pasta em `apps`, com nome sem espaços ou acentos.
Por exemplo: `apps/emite_guia/`. Inclua `__init__.py`, `app.py` e, conforme
necessário, `templates/`, `static/` e módulos auxiliares.

O `app.py` deve exportar a aplicação WSGI na variável `app`. Para Flask:

```python
from flask import Flask
app = Flask(__name__)
```

Não execute `app.run()`, BATs, janelas gráficas ou abertura de navegador ao importar.
O portal inicia todas as aplicações cadastradas; clicar no menu abre sua página.
Scripts que só executam rotinas em console ainda precisam de adaptação para web.

Use imports relativos para arquivos do próprio aplicativo:

```python
from .leitura import processar
```

Para configurações comuns:

```python
from portal.settings import CONFIG, BASE_DIR
```

`BASE_DIR` sempre aponta para a raiz do portal. Caminhos de documentos continuam
no `config.ini`; logs devem ir para `BASE_DIR / 'logs' / 'nome_do_app'`.

Inclua um item na lista de `aplicativos.json`, com vírgula entre os objetos:

```json
{
  "nome": "Emitir Guias",
  "descricao": "Emissão de guias",
  "rota": "/emitir-guias",
  "modulo": "apps.emite_guia.app",
  "ativo": true
}
```

Cadastre apenas quando o módulo já existir. O cadastro acima é um exemplo,
não um aplicativo incluído no pacote. Cada rota precisa ser única e não terminar
com barra. O menu e a montagem da rota usam o mesmo cadastro. Para remover uma
aplicação do menu e de suas rotas, defina `ativo` como `false` e reinicie o portal.
Não é necessário alterar o HTML do menu ou `portal/servidor.py` a cada inclusão.
Este arquivo é mantido localmente pela TI; usuários não podem enviar módulos.

Os templates pertencem a cada aplicativo. Use `url_for` em formulários, links,
arquivos estáticos e URLs de API, para respeitar o prefixo no portal:

```html
<form action="{{ url_for('index') }}" method="post">
```

Evite caminhos fixos como `action="/"` ou chamadas para `localhost:5000`.
Não use arquivos globais como `resultado.xlsx` para todos os usuários.

Inclua as dependências no `requirements.txt` da raiz e execute `1_instalar.bat`.
As telas Flask usam um único processo e ambiente Python. As novas rotinas com acompanhamento usam subprocessos no mesmo ambiente Python.
A separação de pastas não isola dependências, memória ou permissões. Aplicativos
com versões de bibliotecas incompatíveis precisam de processos/ambientes separados
numa etapa posterior. A arquitetura atual não executa qualquer BAT automaticamente.

Antes de liberar:

1. Confira importação, rota, templates e configuração de caminhos.
2. Verifique o fluxo real completo, incluindo mensagens de erro e download.
3. Teste dois usuários para evitar mistura de resultados.
4. Confirme que os aplicativos já integrados continuam funcionando.
5. Mantenha uma cópia da versão anterior para retorno.

## Login e permissões

Nesta versão, a aplicação cadastrada deve ser uma instância Flask. O portal
instala automaticamente a verificação de sessão, autorização por rota e CSRF em
todas as rotas de cada aplicativo, antes de atender as requisições. Não substitua
os hooks ou a configuração de sessão instalada pelo portal e não exponha o app
por outro servidor sem autenticação.

Todo formulário POST precisa conter:

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
```

Para `fetch` com `FormData(form)`, o campo segue no formulário automaticamente.
Para requisições JSON, envie o token no cabeçalho `X-CSRF-Token`. Ele deve vir do
mesmo template renderizado para a sessão atual. Métodos que alteram dados não
devem usar GET. Um POST sem token válido recebe erro, mesmo com login válido.

O menu é filtrado pelo cadastro do usuário. A permissão é validada também em
URLs diretas, APIs e downloads. Novos aplicativos não são liberados para usuários
comuns automaticamente. O administrador deve editar os usuários para liberá-los.
Administradores têm acesso a todos os aplicativos ativos.

Rotas reservadas: /login, /sair, /admin, /minha-senha, /saude e /static.

Sessões e permissões ficam em dados/, que deve ser preservada nas atualizações.
O cadastro inicial de administrador acontece somente no console do notebook.
Não há cadastro público nem credencial embutida nos arquivos do projeto.


## Aplicativos com processamento demorado

Use `portal.tarefas.criar_app` para uma tela com upload, acompanhamento e resultados
privados. O preparo valida e salva as entradas; um módulo `worker` fixo processa
`parametros.json` e grava os arquivos em `saida/` da execução. O portal não aceita
nomes de módulo, comandos de shell ou caminhos de saída enviados pelo usuário.
Há uma execução por aplicativo e no máximo três subprocessos ao mesmo tempo.

O worker deve sinalizar falhas com exceção/código de saída diferente de zero;
`resultado.json` traz a mensagem de conclusão. Nunca grave saídas fora da pasta
recebida, exceto estados persistentes explicitamente previstos e protegidos.

O novo `config_apps.ini` permite manter configurações de caminhos separadas do
`config.ini` que já funciona. Para caminhos locais relativos, use a raiz do portal.

Referência de segurança para os formulários e limites de upload:
https://flask.palletsprojects.com/en/stable/web-security/
https://flask.palletsprojects.com/en/stable/patterns/fileuploads/
