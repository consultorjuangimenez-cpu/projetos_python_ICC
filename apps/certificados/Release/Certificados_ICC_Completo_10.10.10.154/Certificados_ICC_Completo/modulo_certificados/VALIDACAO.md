# Validação da entrega

## Executado

- 13 testes automatizados do servidor e instalador, usando certificados PKCS#12 artificiais: aprovados.
- Integração com `portal/acesso.py` e `portal/usuarios.py` extraídos do pacote `Portal_Apps.zip` de referência: login, sessão, permissão e CSRF.
- Leitura de CPF/CNPJ, categorias de validade e limite de 30 dias.
- Reutilização de cache, remoção de arquivo da lista, pasta indisponível e rejeição de link para arquivo fora da raiz.
- Correção validada de senha, armazenamento cifrado e aproveitamento da senha do JSON legado sem publicar arquivos que não existem.
- Invalidação de dados antigos quando um PFX muda e deixa de abrir.
- Exportação XLSX somente da seleção solicitada, sem senhas.
- Solicitação de instalação, entrega com token único, token expirado, alteração de arquivo, retirada de permissão e confirmação do resultado pelo auxiliar simulado.
- Instalador: backup, preservação dos aplicativos anteriores e execução repetida sem duplicar cadastro ou configuração.
- JavaScript: verificação de sintaxe e execução em DOM de teste com 17 registros artificiais. Total, filtros por nome, CPF, situação, prazo, origem da senha, estado vazio, detalhes e elementos dos gráficos aprovados.
- Python: compilação de todos os arquivos.
- PowerShell: análise sintática dos três scripts. Arquivos com BOM UTF-8 e quebras CRLF para Windows PowerShell 5.1.

## Limites

A importação real no repositório Windows, a abertura do protocolo pelo navegador, o efeito das políticas do domínio e a confiança TLS das estações não foram executados neste ambiente Linux. O retorno de instalação foi simulado nos testes do servidor. Faça o piloto descrito em `HTTPS_E_VALIDACAO.md` antes de liberar para todos.

O ambiente não permitiu iniciar o Chromium para a conferência visual de layout. O teste funcional da interface foi feito em DOM, sem afirmar validação visual ou responsiva em navegador real.

Nenhum PFX real da empresa foi fornecido. Os certificados artificiais e as senhas dos testes não são distribuídos no pacote. Os caminhos reais da rede e os 638 registros do JSON enviado não foram tratados como arquivos existentes neste ambiente.

## Reexecutar os testes

No ambiente de desenvolvimento, instale `pytest` além das dependências do módulo e execute:

```powershell
python -m pytest tests -q
```

Para incluir os testes com a autenticação real, informe uma pasta que contenha `portal\acesso.py`, `portal\usuarios.py` e os templates do portal:

```powershell
$env:CERT_PORTAL_TEST_REF = 'C:\C\Projetos_Phyton\Portal_Apps'
python -m pytest tests -q
```

Os testes criam usuários e certificados apenas em diretórios temporários. Não acessam o banco real de usuários. Sem a referência do portal, os testes de integração são marcados como não executados.
