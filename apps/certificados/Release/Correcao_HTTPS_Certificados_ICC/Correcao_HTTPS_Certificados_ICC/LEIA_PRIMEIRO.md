# Ajuste da verificação HTTPS e diagnóstico

A URL e o backend enviados estão corretos. Um teste com a mesma configuração de cabeçalhos do Waitress aceitou a origem HTTPS. O log anterior também mostra que o Caddy iniciou e obteve o certificado. Esses dados não identificam qual condição está diferente na requisição real do módulo.

Este pacote faz um ajuste localizado no `apps\certificados\app.py` atual:

- Compara host e porta de forma normalizada: `https://10.10.10.154` e `https://10.10.10.154:443` representam a mesma origem.
- Mantém a exigência de HTTPS, host, porta e caminho configurados. Não usa cabeçalhos encaminhados diretamente nem contorna a validação TLS.
- Acrescenta uma página de diagnóstico para o administrador autenticado. Ela mostra os valores efetivos recebidos pelo Flask, sem listar os certificados.
- Faz backup dos arquivos alterados e preserva as demais funções do app. Não troca o módulo inteiro nem altera Caddy, backend, configurações, usuários ou dados.

A diferença de porta é uma possibilidade tratada pelo ajuste, não uma causa comprovada no seu servidor. O diagnóstico identifica a condição real.

## Aplicar

1. Extraia este ZIP em uma pasta separada do portal.
2. Encerre a janela de `2_INICIAR_HTTPS.bat` com CTRL+C.
3. Execute `APLICAR_CORRECAO.bat` e confirme a pasta `C:\C\Projetos_Phyton\Portal_Apps`.
4. Inicie novamente `Portal_Apps\https_icc\2_INICIAR_HTTPS.bat`.
5. Entre como administrador no portal e abra:

**https://10.10.10.154/certificados/api/diagnostico-https**

Copie o pequeno resultado JSON para análise. Depois, atualize o painel com CTRL+F5.

## Resultado esperado

```json
{
  "instalacao_https": true,
  "esquema_recebido": "https",
  "host_recebido": "10.10.10.154",
  "caminho_montagem": "/certificados",
  "verificacoes": {
    "url_configurada_valida": true,
    "python_recebe_https": true,
    "host_e_porta_conferem": true,
    "caminho_confere": true
  }
}
```

A resposta real inclui o motivo e a versão da verificação. Se alguma condição for falsa, esses valores mostram qual camada precisa de correção.

Se todas forem verdadeiras e os botões continuarem desabilitados em certificados válidos, investigue a resposta do painel, o JavaScript em execução e possíveis versões em cache. A instalação do auxiliar só passa a ser investigada depois que o botão fica habilitado.

Se a página retornar 404 após a aplicação, confira se a instância foi reiniciada e se o BAT apontou para a mesma pasta do portal executado. Se o patch informar estrutura diferente, ele não altera o app: é necessário analisar o `apps\certificados\app.py` atual.

## Reversão e testes

Para reverter, pare o portal e restaure o `app.py` do backup em `backups_atualizacao\correcao_https_DATA_HORA...`. A pasta também guarda a versão anterior de `conexao_https.py`, caso existisse.

Testados oito cenários em Flask/Waitress 3.0.2: HTTPS correto, porta padrão explícita, HTTP, host diferente, porta diferente, cabeçalhos de origem não confiável, ausência de cabeçalhos e caminho divergente. O patch foi conferido por AST para preservar as demais funções e poder ser reaplicado sem duplicar a rota.

A requisição real da estação e a importação de certificado no Windows ainda dependem da validação no ambiente da empresa.
