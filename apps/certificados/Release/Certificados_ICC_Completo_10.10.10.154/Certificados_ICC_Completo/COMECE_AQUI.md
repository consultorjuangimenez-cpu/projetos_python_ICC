# Instalação do ajuste ICC

Endereço configurado: **https://10.10.10.154/certificados/**.

## No servidor

1. Extraia este pacote em uma pasta separada, feche o portal e execute **INSTALAR_AJUSTE.bat**. Informe `C:\C\Projetos_Phyton\Portal_Apps`. Se o painel já existir, ele será mantido. Se ainda não existir, será instalado.
2. Baixe o [Caddy oficial para Windows amd64](https://caddyserver.com/download), sem plugins, e salve o executável como `C:\C\Projetos_Phyton\Portal_Apps\https_icc\caddy.exe`. O executável não está neste pacote.
3. Abra `Portal_Apps\https_icc\LEIA_PRIMEIRO.md` e siga a regra de firewall descrita ali. Execute **1_CONFIGURAR_HTTPS.bat** e depois **2_INICIAR_HTTPS.bat**. A primeira etapa faz backup dos INIs. A segunda mantém o portal funcionando enquanto sua janela ficar aberta.
4. Com o HTTPS iniciado, execute **3_EXPORTAR_CONFIANCA.bat** em outra janela. Ele gera:

```text
C:\C\Projetos_Phyton\Portal_Apps\https_icc\distribuir\Preparar_Estacao_ICC.zip
```

A partir da mudança, use o BAT HTTPS para iniciar o portal. O login exige HTTPS e o BAT antigo da porta 8080 deve ficar fechado. Mantenha o IP 10.10.10.154 reservado para o servidor.

## Nas máquinas dos usuários

Entregue **somente Preparar_Estacao_ICC.zip**, gerado no servidor. O usuário deve:

1. Extrair o ZIP inteiro.
2. Executar **INSTALAR_NESTE_COMPUTADOR.bat**, no próprio usuário do Windows.
3. Entrar no portal e usar **INSTALAR** no certificado A1 desejado.

Esse único BAT configura tanto a confiança HTTPS quanto o Auxiliar ICC. Também deve ser executado no usuário do servidor que acessará o portal. Não exige Python nas estações. O Windows pode pedir confirmação da confiança, e políticas do domínio podem exigir atuação da TI.

O certificado real HTTPS não está pré-gerado neste download: precisa corresponder à autoridade criada no seu servidor. O exportador faz essa preparação e embute a identificação SHA256 no BAT da estação. Não distribua a pasta `dados\caddy_https`, pois contém chaves privadas.

## Validação

Código Python e edição dos INIs conferidos; exportação da confiança testada com certificado artificial, garantindo que nenhuma chave privada entre no pacote das estações. O painel mantém a versão previamente entregue, que passou nos 13 testes automatizados. A importação real no Windows e o funcionamento do Caddy/firewall precisam ser confirmados em uma estação piloto.

As instruções completas e a reversão estão em `https_icc\LEIA_PRIMEIRO.md`. O código integral do painel também acompanha este pacote em `modulo_certificados`.

A importação da confiança usa o repositório do usuário atual, conforme [documentação da Microsoft](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate?view=windowsserver2025-ps).
