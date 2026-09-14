import os
import re
import unicodedata
import pandas as pd
from flask import Flask, render_template, request, send_file
import io
import logging
import traceback

from pathlib import Path
from logging.handlers import RotatingFileHandler
from portal.settings import CONFIG, BASE_DIR
from .leitura_rcf import ler_relacao, identificar_colunas, letra_coluna

logger = logging.getLogger("planilha_amanda")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    (BASE_DIR / "logs" / "planilha_amanda").mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(BASE_DIR / "logs" / "planilha_amanda" / "planilha_amanda.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

@app.after_request
def response_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response

def show_form(error=None, status=200):
    return render_template("amanda.html", error=error), status

@app.errorhandler(413)
def too_large(error):
    return show_form("O envio excedeu 32 MB. Utilize uma planilha menor.", 413)

# =============================================================================
# CONFIGURAÇÃO DAS PLANILHAS DE RELAÇÃO DE CLIENTES / FORNECEDORES
# =============================================================================
PASTA_RCF = CONFIG.get("amanda", "pasta_rcf", fallback=r"C:\C\Projetos_Phyton\Planilha Amanda\RCF")
if not Path(PASTA_RCF).is_absolute():
    PASTA_RCF = str(BASE_DIR / PASTA_RCF)
ARQUIVOS_RCF = [
    "RELAÇÃO DE CLIENTES.xls",
    "RELAÇÃO DE FORNECEDORES.xls",
]


def extract_numbers(value):
    if pd.isna(value):
        return ""
    val_str = str(value).strip()
    partes = re.split(r'[- ]+', val_str)
    primeira_parte = partes[0]
    return re.sub(r'\D', '', primeira_parte)


def format_date(value):
    if pd.isna(value):
        return ""
    try:
        return pd.to_datetime(value).strftime('%d/%m/%Y')
    except:
        return value


def limpar_valor(valor):
    if pd.isna(valor) or str(valor).strip() == "":
        return 0.0
    try:
        if isinstance(valor, (int, float)):
            return round(float(valor), 2)
        val_str = str(valor).replace('R$', '').strip().replace('.', '').replace(',', '.')
        return round(float(val_str), 2)
    except:
        return 0.0


def normalizar_texto_match(valor):
    """
    Normaliza textos para comparação entre:
      - coluna K da planilha modelo
      - colunas H e I das planilhas de clientes/fornecedores

    A comparação ignora diferenças de maiúsculas/minúsculas, acentos,
    espaços duplicados e pontuação.
    """
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    if not texto or texto.lower() == 'nan':
        return ""

    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = texto.upper()
    texto = re.sub(r'[^A-Z0-9]+', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def limpar_documento_rcf(valor):
    """Preserva o valor da coluna J, removendo apenas artefatos comuns do Excel."""
    if pd.isna(valor):
        return ""

    documento = str(valor).strip()
    if not documento or documento.lower() == 'nan':
        return ""

    # Caso o Excel tenha lido um documento numérico como 12345678901.0
    if re.fullmatch(r'\d+\.0', documento):
        documento = documento[:-2]

    return documento


def criar_indice_rcf():
    """
    Lê uma única vez:
      - RELAÇÃO DE CLIENTES.xls
      - RELAÇÃO DE FORNECEDORES.xls

    Cria um índice em memória usando Nome e Razão Social como chaves
    e CPF-CNPJ como valor, identificados pelos cabeçalhos.

    Retorna:
        dict: {texto_normalizado_coluna_H_ou_I: cpf_cnpj_coluna_J}
    """
    indice = {}

    for nome_arquivo in ARQUIVOS_RCF:
        caminho = os.path.join(PASTA_RCF, nome_arquivo)

        if not os.path.exists(caminho):
            logger.error(f"[RCF] Arquivo não encontrado: {caminho}")
            raise ValueError(f"Arquivo de referência ausente: {nome_arquivo}. Confira pasta_rcf no config.ini do servidor.")

        try:
            # header=None porque a regra é baseada na posição física das colunas H, I e J.
            # dtype=str ajuda a preservar CPF/CNPJ sem conversões desnecessárias.
            df_rcf = ler_relacao(caminho)
            header_row, col_nome, col_razao, col_documento = identificar_colunas(df_rcf)
        except Exception as e:
            logger.error(f"[RCF] Erro ao ler {caminho}: {e}")
            raise ValueError(f"Não foi possível ler {nome_arquivo}. Consulte o log no servidor.") from e

        logger.info("[RCF] %s | cabeçalho=%d | Nome=%s | Razão Social=%s | Documento=%s",
                    nome_arquivo, header_row + 1, letra_coluna(col_nome),
                    letra_coluna(col_razao), letra_coluna(col_documento))

        adicionados = 0

        for _, row_rcf in df_rcf.iloc[header_row + 1:].iterrows():
            valor_h = row_rcf.iloc[col_nome]   # Nome, identificado pelo cabeçalho
            valor_i = row_rcf.iloc[col_razao]   # Razão Social, identificada pelo cabeçalho
            cpf_cnpj = limpar_documento_rcf(row_rcf.iloc[col_documento])  # Documento, identificado pelo cabeçalho

            if not cpf_cnpj:
                continue

            for valor_referencia in (valor_h, valor_i):
                chave = normalizar_texto_match(valor_referencia)
                if not chave:
                    continue

                if chave not in indice:
                    indice[chave] = cpf_cnpj
                    adicionados += 1
                elif indice[chave] != cpf_cnpj:
                    logger.warning(
                        f"[RCF] Referência duplicada com CPF/CNPJ diferente em {nome_arquivo}: "
                        f"'{valor_referencia}' | mantido: {indice[chave]} | ignorado: {cpf_cnpj}"
                    )

        logger.info(
            f"[RCF] {nome_arquivo}: {adicionados} referências H/I adicionadas ao índice."
        )

    logger.info(f"[RCF] Índice final criado com {len(indice)} referências.")
    return indice


def preencher_cnpj_modelo(df_destino, indice_rcf):
    """
    Usa a coluna K 'COMPLEMENTO DO HISTORICO CONTABIL' da planilha modelo
    para localizar um match nas colunas Nome/Razão Social das planilhas RCF.

    Quando encontra, preenche a coluna I 'CNPJ FORNECEDOR' com a coluna J
    da planilha RELAÇÃO DE CLIENTES.xls ou RELAÇÃO DE FORNECEDORES.xls.
    """
    if df_destino.empty:
        return df_destino

    total_matches = 0
    total_sem_match = 0

    for idx in df_destino.index:
        complemento = df_destino.at[idx, 'COMPLEMENTO DO HISTORICO CONTABIL']
        chave = normalizar_texto_match(complemento)

        if not chave:
            continue

        cpf_cnpj = indice_rcf.get(chave, "")

        if cpf_cnpj:
            df_destino.at[idx, 'CNPJ FORNECEDOR'] = cpf_cnpj
            total_matches += 1
            logger.info(
                f"[MATCH RCF] Complemento '{complemento}' -> CPF/CNPJ: {cpf_cnpj}"
            )
        else:
            total_sem_match += 1
            logger.debug(f"[SEM MATCH RCF] Complemento: '{complemento}'")

    logger.info(
        f"[RCF] Preenchimento concluído. Matches: {total_matches} | Sem match: {total_sem_match}"
    )
    return df_destino


def process_excel_direct(file_stream, cnpj_cliente):
    logger.info("--- Iniciando leitura do arquivo Excel ---")
    try:
        df = pd.read_excel(file_stream, header=None)
    except Exception as e:
        logger.error(f"Erro ao ler arquivo Excel: {e}")
        return None

    # Cria uma única vez o índice H/I -> J das relações de clientes e fornecedores.
    indice_rcf = criar_indice_rcf()

    linhas_destino = []
    current_date = ""
    current_tipo = ""

    for index, row in df.iterrows():
        try:
            is_total = False
            for col_idx in range(10):
                val_str = str(row.get(col_idx)).lower()
                if 'saldo atual' in val_str or 'totais' in val_str:
                    is_total = True
                    break

            if is_total:
                current_tipo = ""
                continue

            a, b, c, d = row.get(0), row.get(1), row.get(2), row.get(3)

            is_a_empty = pd.isna(a) or str(a).strip() == ""
            is_b_empty = pd.isna(b) or str(b).strip() == ""

            if not is_a_empty and not is_b_empty and pd.notna(c) and pd.notna(d):
                tipo_str = str(d).strip()
                if tipo_str.startswith(('7', '9', '10')):
                    current_date = format_date(b)
                    current_tipo = tipo_str
                else:
                    current_tipo = ""
                continue

            if current_tipo and is_a_empty and is_b_empty:
                if pd.notna(c) and 'loja' in str(c).lower():
                    continue

                if pd.isna(d) and pd.isna(row.get(4)) and pd.isna(row.get(6)):
                    continue

                nota_col_e = extract_numbers(row.get(4))
                nota_col_g = extract_numbers(row.get(6))

                tipo_nota = ''
                num_nota = ''

                if current_tipo.startswith('9'):
                    tipo_nota = 'SAI'
                    num_nota = nota_col_e if nota_col_e else nota_col_g
                elif current_tipo.startswith('7'):
                    tipo_nota = 'SAI'
                    num_nota = nota_col_g if nota_col_g else nota_col_e
                elif current_tipo.startswith('10'):
                    tipo_nota = 'ENT'
                    num_nota = nota_col_g if nota_col_g else nota_col_e

                valor_total_nota = row.get(8)

                # O CNPJ não é mais pesquisado nos XMLs.
                # Ele será preenchido após a criação da planilha modelo,
                # usando a coluna K como referência para as planilhas RCF.
                cnpj_fornecedor = ""

                nova_linha = {
                    'A_TIPO': tipo_nota,
                    'B_NUMERO_NOTA': num_nota,
                    'C_PARCELA': row.get(5),
                    'D_DATA_PGTO': current_date,
                    'E_VALOR_TOTAL': valor_total_nota,
                    'F_VALOR_JUROS': row.get(10),
                    'G_VALOR_MULTA': row.get(9),
                    'H_VALOR_DESCONTO': row.get(11),
                    'I_CNPJ_FORNECEDOR': cnpj_fornecedor,
                    'J_CONTA_RECEBIMENTO': '8',
                    'K_COMPLEMENTO': row.get(3)
                }

                if tipo_nota:
                    linhas_destino.append(nova_linha)

        except Exception as e:
            logger.error(f"Erro ao processar a linha {index}: {e}")

    logger.info(f"Fim do processamento. {len(linhas_destino)} notas filtradas.")

    df_destino = pd.DataFrame(linhas_destino)
    if not df_destino.empty:
        df_destino.columns = [
            'TIPO', 'NUMERO DA NOTA', 'PARCELA', 'DATA PGTO', 'VALOR TOTAL',
            'VALOR JUROS', 'VALOR MULTA', 'VALOR DESCONTO', 'CNPJ FORNECEDOR',
            'CONTA RECEBIMENTO', 'COMPLEMENTO DO HISTORICO CONTABIL'
        ]

        # Agora consulta literalmente a coluna K da planilha modelo já montada.
        df_destino = preencher_cnpj_modelo(df_destino, indice_rcf)

    return df_destino


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            file = request.files.get('file')
            cnpj_cliente = request.form.get('cnpj_cliente', '').strip()

            if file and file.filename.lower().endswith(('.xlsx', '.xls')) and cnpj_cliente:
                logger.info(f"Arquivo e CNPJ ({cnpj_cliente}) recebidos. Iniciando processamento...")

                df_resultado = process_excel_direct(io.BytesIO(file.read()), cnpj_cliente)

                if df_resultado is not None and not df_resultado.empty:
                    csv_buffer = io.StringIO()
                    df_resultado.to_csv(csv_buffer, index=False, sep=';', decimal=',')
                    csv_buffer.seek(0)

                    logger.info("Planilha gerada com sucesso.")
                    return send_file(
                        io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
                        mimetype='text/csv',
                        as_attachment=True,
                        download_name='planilhamodelo.csv'
                    )
                else:
                    logger.warning("Nenhum dado das categorias 7, 9 ou 10 foi encontrado.")
                    return show_form("Não foi possível ler a planilha ou não foram encontrados dados dos tipos 7, 9 ou 10.", 400)
            else:
                return show_form("Selecione um arquivo .xlsx ou .xls e informe o CNPJ do cliente.", 400)
        except ValueError as e:
            return show_form(str(e), 400)
        except Exception as e:
            from werkzeug.exceptions import HTTPException
            if isinstance(e, HTTPException):
                raise
            logger.error(f"Erro geral na rota (/): {e}")
            logger.error(traceback.format_exc())
            return show_form("Ocorreu um erro no servidor. Consulte logs/planilha_amanda/planilha_amanda.log no notebook.", 500)

    return show_form()


if __name__ == '__main__':
    from portal.servidor import main
    main()
