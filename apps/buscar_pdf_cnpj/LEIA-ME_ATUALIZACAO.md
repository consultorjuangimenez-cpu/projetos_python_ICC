# Buscar PDFs por CNPJ, versão 1.1.1

Este pacote atualiza o módulo existente do portal. Não é uma aplicação independente: continua dependendo de `portal.integracao`, `portal.settings`, do usuário autenticado e da proteção CSRF fornecidos pelo portal.

## Correção 1.1.1: índice antigo e caminhos equivalentes

O PDF CNPJ.pdf enviado foi testado com pypdf e PyMuPDF. Ambos extraíram corretamente 42.072.999/0001-24. Em teste local, a busca encontrou o documento e o download devolveu os mesmos bytes do PDF original.

A versão 1.0 armazenava o caminho resolvido pelo sistema operacional. A versão 1.1.0 comparava esses registros com o caminho literal configurado, como F:\Documentos\Rafael. Quando a unidade mapeada corresponde a um caminho UNC diferente no banco, esse filtro podia ignorar registros existentes e iniciar uma indexação desnecessária. Essa falha foi reproduzida usando dois caminhos equivalentes no ambiente de teste.

A versão 1.1.1 confirma a equivalência da raiz ao iniciar o módulo e normaliza apenas os registros dessa raiz, em uma transação SQLite, sem reler os PDFs. Em duplicatas, preserva o registro com a atualização mais recente. Registros de outras raízes permanecem intactos. A confirmação da raiz acessa o sistema de arquivos na preparação; as buscas continuam locais.

O caminho informado para o banco é o esperado:

```text
C:\C\Projetos_Phyton\Portal_Apps\dados\apps\buscar_pdf_cnpj\indice_pdfs.sqlite3
```

Pare o portal, substitua o módulo, mantenha esse banco e reinicie. Faça primeiro a busca pelo CNPJ, sem solicitar nova indexação. O log registra `Diagnóstico do índice`, com o caminho do banco, o total de registros e o total reconhecido na raiz. Se houver normalização, registra `Compatibilidade restaurada` e a quantidade de registros reaproveitados.

O log enviado confirmou uma busca com somente 100 registros, durante a atualização. Ele não contém os caminhos armazenados no banco. Por isso, a correção da incompatibilidade foi validada em teste, mas sua ocorrência no banco real depende dos registros existentes. Se o índice tiver sido substituído, estiver incompleto ou os PDFs nunca tiverem sido indexados, a normalização não recria o texto ausente. O novo log permitirá distinguir esses casos.

A interface agora destaca buscas parciais. Se houver registros no banco e nenhum for reconhecido na raiz configurada, não inicia automaticamente uma varredura como se o banco estivesse vazio; mostra o aviso de incompatibilidade.

## Como instalar

1. Pare o portal e faça uma cópia da pasta atual `buscar_pdf_cnpj`.
2. Extraia este ZIP e substitua os arquivos da pasta `buscar_pdf_cnpj` existente. Preserve seu `config.json` caso tenha alterações próprias. Não crie uma segunda pasta `buscar_pdf_cnpj` dentro da primeira.
3. No mesmo ambiente Python usado para iniciar o portal, instale o motor de leitura:

   ```bat
   python -m pip install "PyMuPDF>=1.26,<2"
   ```

   Se o portal usa um ambiente virtual, ative esse ambiente antes do comando ou use o caminho completo do `python.exe` dele. As demais dependências já eram usadas pelo módulo; `requirements.txt` lista as dependências para instalação completa.

4. Inicie o portal pelo BAT habitual e recarregue a página com Ctrl+F5.
5. Faça uma busca. O índice que já existe será aproveitado imediatamente. Para conferir PDFs novos, alterados ou removidos, clique em **Atualizar índice**. Quando a atualização terminar, faça a busca novamente.

**Não apague `dados/apps/buscar_pdf_cnpj/indice_pdfs.sqlite3`, na pasta do portal.** Esse é o índice que levou duas horas para ser construído. O esquema antigo continua compatível e PDFs inalterados não são relidos. O ZIP não contém nenhum banco de dados para sobrescrever o seu.

## O que foi corrigido

Antes, toda busca executava uma varredura recursiva na rede, verificava cada arquivo e consultava seu registro individual, antes de retornar os resultados. Por isso, mesmo com o texto salvo, a próxima busca podia continuar muito lenta.

Agora, a busca consulta somente o SQLite na pasta local do portal. Ela não lista a pasta de documentos, não verifica os PDFs na rede e não extrai texto. A rede é acessada durante a atualização do índice e durante o download dos documentos selecionados.

A atualização ocorre em segundo plano, com contagem de arquivos verificados, lidos e reaproveitados. Sem índice anterior, a primeira busca inicia essa atualização. Enquanto ela roda, buscas usam os dados já salvos e podem trazer resultados incompletos. Com um índice já existente, a atualização é iniciada pelo botão, não por cada consulta.

O leitor preferencial é PyMuPDF. Todas as páginas continuam sendo lidas. Se a biblioteca não estiver instalada, ou falhar ao abrir um PDF, o módulo mantém a alternativa com pypdf. A escolha do motor aparece no log da atualização. A documentação do PyMuPDF descreve a [extração de texto](https://pymupdf.readthedocs.io/en/latest/app1.html) e as [restrições de uso com múltiplas threads](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html). Nesta versão, um único trabalho de atualização faz a extração, sem distribuir PDFs entre threads.

Os dados são gravados a cada 25 PDFs e ao final. Se o portal for encerrado, os lotes concluídos ficam salvos; clique em Atualizar índice para retomar a conferência. Arquivos removidos saem do índice após uma varredura concluída sem falha de acesso. Uma falha de rede ou de permissão suspende as exclusões desse ciclo, evitando apagar o índice por indisponibilidade temporária.

O download passou a enviar o ZIP em blocos, com tamanho explícito e fechamento do temporário ao terminar. O ZIP não recomprime os PDFs, reduzindo trabalho de CPU, embora possa ficar maior. Nomes repetidos recebem sufixos. Se um arquivo selecionado estiver inacessível, a operação informa o problema em vez de entregar silenciosamente um ZIP incompleto. As seleções ficam em um banco separado, vinculadas ao usuário e com a expiração existente no config.json, resistindo ao reinício do módulo.

## Validação e limites

Dez testes automatizados passaram, incluindo o PDF real enviado e PDFs gerados para validação. Cobrem busca sem varredura na rede, reutilização do índice antigo, atualização incremental, exclusão, isolamento entre pastas, falha de acesso, documento sem texto, PDF inválido, CNPJ na última página, alternativa pypdf, atualização sem bloquear buscas e download integrado a um caminho de portal simulado. O download foi conferido tanto com temporário em memória quanto em disco, incluindo conteúdo, nomes duplicados, usuário diferente, seleção inválida, expiração e arquivo removido.

Os testes adicionais conferem normalização entre raízes equivalentes, mistura de registros antigos e novos, preservação de outra raiz e busca/download do PDF real após compatibilização. O PDF do cliente não está incluído no ZIP.

A sintaxe Python e JavaScript também foi verificada. Para executar os testes incluídos, entre na pasta deste módulo e rode:

```bat
python -m unittest discover -s tests -v
```

O teste opcional com o documento real é executado quando a variável de ambiente `PDF_TESTE_CNPJ` contém o caminho do CNPJ.pdf. Sem essa variável, nove testes são executados e o teste real é marcado como ignorado.

Em uma amostra local sintética de 80 PDFs e 400 páginas, a extração com pypdf levou 1,316 s e com PyMuPDF 0,388 s. A consulta ao índice pronto levou menos de 0,001 s. Esses números demonstram o comportamento nessa amostra, não estimam o tempo da pasta real do escritório. Não houve acesso ao seu Windows, à rede F: nem ao código completo do portal.

A primeira indexação ainda precisa ler todos os PDFs. Quantidade, tamanho, documentos difíceis e velocidade da rede continuam influenciando esse tempo. O índice e o portal devem permanecer no disco local para obter o ganho esperado. A busca ainda percorre o conteúdo numérico armazenado no SQLite; bases muito grandes podem exigir uma evolução adicional do índice.

PDFs escaneados sem camada textual continuam sem OCR, como na versão original. A busca conserva a regra numérica anterior e a validação de CNPJ existente.

O controle de atualização em segundo plano pressupõe uma instância do processo do portal, que pode atender vários usuários por threads. Não execute múltiplas instâncias atualizando o mesmo índice simultaneamente.

O portal completo não veio no anexo, portanto autenticação, CSRF e middleware reais não puderam ser executados aqui. Se o download continuar falhando no escritório, registre o erro mostrado no navegador e consulte `logs/buscar_pdf_cnpj`, dentro da pasta do portal. O código enviado originalmente não inclui logs suficientes para confirmar a causa exata dessa falha.
