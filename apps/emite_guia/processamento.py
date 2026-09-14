import os, time, logging, threading
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

def processar_linha_sefaz(context, dados_form, linha_num, chave, valor_fmt, timeout_segundos=15):
    logging.info(f"--- Processando Linha {linha_num} | Chave: {chave} | Valor: {valor_fmt} | Timeout PDF: {timeout_segundos}s ---")
    
    pdf_linha = {}

    def monitorar_respostas_linha(response):
        try:
            ct = response.headers.get("content-type", "").lower()
            url = response.url.lower()
            
            if "pdf" in ct or "impirmirdar" in url or "darlivre" in url or url.endswith(".pdf"):
                body = response.body()
                if body and body.startswith(b"%PDF"):
                    pdf_linha['bytes'] = body
                    logging.info(f"PDF autêntico capturado via rede para Linha {linha_num}! Tamanho: {len(body)} bytes.")
        except Exception:
            pass

    context.on("response", monitorar_respostas_linha)

    for p_extra in context.pages[1:]:
        try:
            p_extra.close()
        except Exception:
            pass

    page = context.pages[0] if len(context.pages) > 0 else context.new_page()
    page.bring_to_front()

    sucesso = False
    try:
        logging.info("Acessando a página inicial da SEFAZ...")
        page.goto('https://www.sefaz.mt.gov.br/arrecadacao/darlivre/menudarnovo?tipoTributo=66&tipoContribuinte=3&pagn=contribuinte')
        page.wait_for_load_state("domcontentloaded")

        radio_cnpj = page.locator("input[type='radio'][value='2'], input[type='radio'][value='CNPJ'], input[id*='cnpj']")
        if radio_cnpj.count() > 0:
            radio_cnpj.first.click()
        else:
            page.locator("label:has-text('CNPJ'), td:has-text('CNPJ') input").first.click()
        
        time.sleep(0.2)

        campo_cnpj = page.locator("input[type='text']:visible").first
        campo_cnpj.fill(dados_form['cnpj_cliente'])
        time.sleep(0.2)

        botao_continuar = page.locator("input[type='submit'], input[type='button'], button").filter(has_text="Continuar")
        if botao_continuar.count() == 0:
            botao_continuar = page.locator("input[value*='Continuar'], input[name*='btnContinuar']")

        if botao_continuar.count() > 0:
            botao_continuar.first.click()
        else:
            campo_cnpj.press("Enter")
        
        page.wait_for_load_state("networkidle")
        time.sleep(0.8)

        page.locator("input[name='periodoReferencia']").first.fill(dados_form['periodo_ref'])
        time.sleep(0.2)

        select_receita = page.locator("select[name='codigoReceita'], select").first
        select_receita.click()
        time.sleep(0.2)
        
        codigo_desejado = dados_form['especificacao_receita']
        try:
            select_receita.select_option(value=codigo_desejado)
        except Exception:
            options = select_receita.locator("option").all()
            for op in options:
                if codigo_desejado in op.inner_text():
                    select_receita.select_option(value=op.get_attribute("value"))
                    break

        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.5)

        campo_dest = page.locator("input[name='numrDocumentoDestinatario'], input[name='numCnpjCpfDestinatario']").first
        if campo_dest.is_visible():
            campo_dest.fill(dados_form['destinatario'])
        time.sleep(0.2)

        campo_venc = page.locator("input[name='dataVencimento']").first
        if campo_venc.is_visible():
            campo_venc.fill(dados_form['data_vencimento'])
        time.sleep(0.2)

        for i in range(9):
            chk = page.locator("table tr input[type='checkbox']").nth(i)
            if chk.is_checked():
                chk.uncheck()

        chk_10 = page.locator("table tr input[type='checkbox']").nth(9)
        if not chk_10.is_checked():
            chk_10.check()

        campo_linha_10 = page.locator("input[name='numrNota10'], input[id='numrNota10']").first
        if campo_linha_10.is_visible():
            campo_linha_10.fill(chave)
        else:
            page.locator("table tr input[name*='numrNota']:visible").nth(9).fill(chave)

        time.sleep(0.3)

        loc_valor = page.locator("input[name='valorTributo'], input[name='valrTributo'], input[id='valorTributo']").first
        if loc_valor.count() > 0 and loc_valor.is_visible():
            loc_valor.fill(valor_fmt)
        else:
            page.locator("input[name='dataVencimento']").first.press("Tab")
            page.keyboard.type(valor_fmt)

        time.sleep(0.3)

        botao_emitir = page.locator("input[value*='Emitir'], button:has-text('Emitir')").first
        if botao_emitir.is_visible():
            botao_emitir.click()
        else:
            page.evaluate("document.querySelector(\"input[value*='Emitir']\").click()")
            
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        nome_arquivo = f"Guia_Linha_{linha_num}_{chave[:10]}.pdf"
        caminho_final = os.path.join(PASTA_DESTINO, nome_arquivo)

        if os.path.exists(caminho_final):
            try:
                os.remove(caminho_final)
            except PermissionError:
                ts = datetime.now().strftime("%H%M%S")
                nome_arquivo = f"Guia_Linha_{linha_num}_{chave[:10]}_{ts}.pdf"
                caminho_final = os.path.join(PASTA_DESTINO, nome_arquivo)

        botoes_pdf = page.locator("input[value*='DAR'], input[value*='PDF'], button:has-text('DAR'), button:has-text('PDF'), a:has-text('DAR'), input[value*='Imprimir']")
        
        # Estratégia Principal: Captura nativa via evento expect_download do Playwright
        try:
            with page.expect_download(timeout=timeout_segundos * 1000) as download_info:
                clicou = False
                if botoes_pdf.count() > 0:
                    for idx in range(botoes_pdf.count()):
                        btn = botoes_pdf.nth(idx)
                        if btn.is_visible():
                            try:
                                btn.click()
                                clicou = True
                                logging.info(f"Clicou no botão de emissão #{idx+1}")
                                break
                            except Exception as e_click:
                                logging.warning(f"Erro ao clicar no botão #{idx+1}: {e_click}")

                if not clicou:
                    page.evaluate("if(document.forms && document.forms.length > 0) document.forms[0].submit()")

            download = download_info.value
            download.save_as(caminho_final)
            logging.info(f"Guia em PDF salva via download nativo: {caminho_final}")
            sucesso = True

        except Exception:
            # Fallback 1: Verificação dos bytes no buffer do listener de rede
            if 'bytes' in pdf_linha and pdf_linha['bytes'].startswith(b"%PDF"):
                with open(caminho_final, "wb") as f:
                    f.write(pdf_linha['bytes'])
                logging.info(f"Guia em PDF salva via listener de rede: {caminho_final}")
                sucesso = True

            # Fallback 2: Requisita URL das abas abertas
            if not sucesso:
                for p_extra in context.pages:
                    try:
                        url_p = p_extra.url
                        if "impirmirdar" in url_p or "darlivre" in url_p or ".pdf" in url_p or "chavePix" in url_p:
                            res = p_extra.request.get(url_p)
                            if res.ok and res.body().startswith(b"%PDF"):
                                with open(caminho_final, "wb") as f:
                                    f.write(res.body())
                                logging.info(f"Guia em PDF salva via requisição de aba: {caminho_final}")
                                sucesso = True
                                break
                    except Exception:
                        pass

            # Fallback 3: GET direto no endpoint
            if not sucesso:
                try:
                    url_padrao = "https://www.sefaz.mt.gov.br/arrecadacao/darlivre/impirmirdar?chavePix=true"
                    res = page.request.get(url_padrao)
                    if res.ok and res.body().startswith(b"%PDF"):
                        with open(caminho_final, "wb") as f:
                            f.write(res.body())
                        logging.info(f"Guia em PDF salva via GET direto no endpoint: {caminho_final}")
                        sucesso = True
                except Exception:
                    pass

        if not sucesso:
            logging.error(f"Não foi possível obter o PDF para a linha {linha_num} no tempo estipulado ({timeout_segundos}s).")

    except Exception as err_linha:
        logging.error(f"Erro ao processar linha {linha_num}: {str(err_linha)}", exc_info=True)
    finally:
        try:
            context.remove_listener("response", monitorar_respostas_linha)
        except Exception:
            pass

    return sucesso


def rodar_automacao_background(dados_form, excel_file, pasta_destino):
    global EXCEL_FILE, PASTA_DESTINO
    EXCEL_FILE, PASTA_DESTINO = excel_file, pasta_destino
    status_execucao = {"rodando": True}
    
    logging.info("="*50)
    logging.info("INICIANDO PROCESSO DE EMISSÃO DE GUIAS")
    logging.info(f"Parâmetros recebidos: {dados_form}")

    try:
        if not os.path.exists(EXCEL_FILE):
            logging.error(f"Arquivo Excel '{EXCEL_FILE}' não foi encontrado!")
            status_execucao["rodando"] = False
            raise FileNotFoundError('A planilha enviada não foi encontrada.')

        df = pd.read_excel(EXCEL_FILE, sheet_name='Plan1')
        os.makedirs(PASTA_DESTINO, exist_ok=True)

        linhas_para_processar = []
        for index, row in df.iterrows():
            linha_num = index + 2
            chave = str(row['CHAVE DE ACESSO']).strip() if pd.notna(row['CHAVE DE ACESSO']) else ''

            if not chave or chave == 'nan':
                break

            valor_tributo = row['VALOR']
            valor_fmt = f"{float(valor_tributo):.2f}".replace('.', ',')
            linhas_para_processar.append({
                'linha_num': linha_num,
                'chave': chave,
                'valor_fmt': valor_fmt
            })

        with sync_playwright() as p:
            logging.info("Iniciando navegador Chromium...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            for item in linhas_para_processar:
                processar_linha_sefaz(
                    context, dados_form, item['linha_num'], item['chave'], item['valor_fmt'],
                    timeout_segundos=15
                )

            browser.close()

        MAX_TENTATIVAS_RETRY = 2
        for tentativa in range(1, MAX_TENTATIVAS_RETRY + 1):
            pendentes = []
            
            for item in linhas_para_processar:
                prefixo_esperado = f"Guia_Linha_{item['linha_num']}_{item['chave'][:10]}"
                arquivos_existentes = os.listdir(PASTA_DESTINO)
                salvo = any(f.startswith(prefixo_esperado) and f.endswith(".pdf") for f in arquivos_existentes)
                
                if not salvo:
                    pendentes.append(item)

            if not pendentes:
                logging.info("Todas as guias em PDF foram salvas na pasta com sucesso!")
                break

            logging.warning(f"--- ROTINA DE REPROCESSAMENTO (Tentativa {tentativa}/{MAX_TENTATIVAS_RETRY}) ---")
            logging.warning(f"Total de linhas pendentes sem PDF salvo: {len(pendentes)}")

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    accept_downloads=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )

                for item in pendentes:
                    logging.info(f"Refazendo Linha {item['linha_num']} com timeout expandido (60s)...")
                    processar_linha_sefaz(
                        context, dados_form, item['linha_num'], item['chave'], item['valor_fmt'],
                        timeout_segundos=60
                    )

                browser.close()

        logging.info("==================================================")
        logging.info("PROCESSAMENTO FINALIZADO PARA TODAS AS LINHAS!")
        return linhas_para_processar

    except Exception as e:
        logging.critical(f"Erro crítico durante o processo: {str(e)}", exc_info=True)
        raise
    finally:
        status_execucao["rodando"] = False


