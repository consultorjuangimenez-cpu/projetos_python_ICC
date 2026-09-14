# HTTPS e validação da instalação

## Estado da entrega

O pacote inclui o painel e o código completo do auxiliar. Ele não configura DNS, proxy, certificado TLS ou estações da empresa automaticamente. O acesso HTTP atual pode continuar sendo usado para consultar o painel; o botão de instalação fica indisponível até concluir a configuração HTTPS.

## Quando houver proxy HTTPS no próprio servidor

1. Configure no proxy um endereço HTTPS reconhecido pelas estações, com certificado TLS válido e confiável. Encaminhe as requisições do portal para `http://127.0.0.1:8081` preservando o caminho.
2. Configure o proxy para **sobrescrever** `X-Forwarded-Proto` com `https` e `X-Forwarded-Host` com o nome e a porta externos. Se houver porta HTTPS diferente de 443, encaminhe também a porta externa corretamente. Não repasse valores desses cabeçalhos fornecidos pelo navegador sem substituição.
3. Copie `iniciar_atras_proxy_https.py` para a raiz do portal. Esse arquivo conserva a aplicação e o login existentes e faz o backend aceitar cabeçalhos encaminhados somente de `127.0.0.1`.
4. Pare a instância habitual e execute, na raiz do portal:

```powershell
.\.venv\Scripts\python.exe iniciar_atras_proxy_https.py
```

5. Edite a seção `[seguranca]` do `config.ini` para `cookie_https = true`. Reinicie o processo após a mudança. A partir daí use HTTPS para o login.
6. Configure `url_publica` em `[certificados_painel]`, em `config_apps.ini`, com a URL completa do módulo. Reinicie o processo após a mudança.

O arquivo opcional não cria o proxy e não fornece TLS sozinho. O Waitress fica restrito a loopback. Caso o proxy esteja em outra máquina, este iniciador não serve sem adaptação de escuta, firewall e IP de confiança para a topologia real. Não substitua `trusted_proxy` por `*`.

## Teste em uma estação piloto

1. Abra o endereço HTTPS no navegador da estação. Não pode haver erro de confiança do certificado TLS.
2. Entre com um usuário de teste autorizado ao aplicativo. Confirme a lista e use um certificado A1 autorizado para o piloto.
3. Configure o auxiliar nesse mesmo usuário do Windows.
4. Clique em **INSTALAR**, confira cliente/documento/computador e confirme.
5. Abra `certmgr.msc` na estação. Verifique o certificado em **Pessoal > Certificados**, inclusive a indicação de chave privada correspondente.
6. Confira que o painel recebeu o resultado e informou o computador correto. Clique novamente para validar a indicação de “já instalado”.
7. Faça um teste de uso no sistema que precisa do certificado. A instalação do arquivo não assegura, por si só, que uma cadeia de confiança esteja correta ou que todos os sistemas estejam compatíveis com o provedor da chave.
8. Teste a retirada da permissão do aplicativo no portal. O usuário não deve mais conseguir consultar ou solicitar novas instalações.

## Diagnóstico

| Sintoma | Causa provável | Teste de confirmação |
|---|---|---|
| Painel vazio com aviso de pasta | Unidade mapeada ausente para a conta do servidor ou caminho diferente | Abra a pasta usando a mesma conta que executa o Python; confira o caminho UNC real. |
| Senha não identificada/incorreta | Nome fora do padrão ou certificado renovado com nova senha | Abra os detalhes como TI via HTTPS e valide a senha correta. |
| INSTALAR desabilitado em toda a lista | HTTPS/URL pública pendente | Acesse exatamente a URL configurada; confira esquema, host, porta e caminho do módulo no proxy. |
| INSTALAR desabilitado somente em algumas linhas | Vencido, ainda não vigente ou falha na leitura | Confira situação e vencimento nos detalhes. |
| Nada acontece ao clicar | Auxiliar ainda não registrado neste usuário ou navegador bloqueou a abertura | Execute a configuração com o usuário atual e use “Abrir Auxiliar ICC” na janela do painel. |
| PowerShell bloqueia o script | Arquivo marcado como baixado ou política de assinatura da empresa | Confira propriedades/procedência do ZIP e a política aplicável. Se houver assinatura obrigatória, assine os scripts. |
| Solicitação expirada/já usada | Auxiliar abriu depois de três minutos ou link foi repetido | Feche a janela do painel e solicite uma nova instalação. |
| Arquivo alterado | PFX trocado entre consulta e instalação | Atualize o inventário e selecione novamente o certificado. |
| Windows instalou, painel não confirmou | Falha de rede no retorno do auxiliar | Confira em `certmgr.msc` antes de repetir. A tela não deve declarar sucesso sem o retorno. |
| Certificado aparece sem funcionar em um sistema | Cadeia da AC, provedor de chave ou compatibilidade da aplicação | Confira a cadeia e faça o piloto no sistema de destino com a TI. |

## Fontes técnicas verificadas

- [Microsoft: X509KeyStorageFlags, incluindo UserKeySet, PersistKeySet e EphemeralKeySet](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509keystorageflags?view=netframework-4.8.1).
- [Microsoft: importação de certificado e chave privada](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.x509certificates.x509certificate2.import?view=netframework-4.8.1).
- [Microsoft: repositório do usuário e chave exportável](https://learn.microsoft.com/en-us/powershell/module/pki/import-pfxcertificate?view=windowsserver2025-ps).
- [Waitress: uso com proxy reverso e cabeçalhos confiáveis](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html).
- [Cryptography: leitura de PKCS#12](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/).
