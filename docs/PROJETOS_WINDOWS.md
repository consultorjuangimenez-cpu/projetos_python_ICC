# Rotinas que continuam no Windows

| Projeto recebido | Motivo | Como manter |
|---|---|---|
| Instala Certificados | Chama `certutil` e instala no repositório de certificados do computador/conta que executa. Pelo portal, instalaria no servidor, não na estação. | Execute o projeto original na máquina que receberá os certificados. |
| Desbloquear_PDF | Usa watchdog, remove `Zone.Identifier` e atributos dos arquivos de pastas monitoradas. É um monitor contínuo do Windows, não uma tarefa de navegador. | Mantenha a execução original ou o serviço na máquina responsável pelas pastas. Não execute outra cópia pelo portal. |
| Segue_Mouse | Usa pyautogui para controlar a sessão gráfica local, com execução imediata no módulo. | Mantenha como ferramenta local; a página web não deve controlar o mouse do servidor. |

Estas três rotinas foram analisadas e não são carregadas nem executadas pelo portal.
Os originais permanecem no ZIP enviado e na pasta de projetos do notebook.

`Buscar PDF/APP.py` do ZIP é o projeto que já existia no portal. A versão integrada
com proteções de caminho e login foi preservada para evitar regressão.

Na Análise de E-mails, foi selecionado `app.py`, conforme o `executa.bat` enviado.
`app_chat.py`, releases, testes antigos, atalhos e monitores auxiliares não são
versões adicionais publicadas no menu.
