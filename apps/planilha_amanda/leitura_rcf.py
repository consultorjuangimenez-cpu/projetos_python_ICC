"""Leitura das relações RCF, preservando posições e documentos como texto."""
import logging
import re
import unicodedata
import pandas as pd

logger = logging.getLogger('planilha_amanda')

def normalizar_cabecalho(value):
    if pd.isna(value):
        return ''
    text = unicodedata.normalize('NFKD', str(value))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]', '', text.upper())

def ler_relacao(caminho):
    """Tenta o leitor padrão e usa Calamine se a exportação XLS for incompatível.

    Nenhuma escrita ou reparo é realizado no arquivo de origem.
    """
    try:
        frame = pd.read_excel(caminho, header=None, dtype=str)
    except Exception as original_error:
        logger.warning('[RCF] Leitor padrão falhou (%s). Tentando Calamine: %s',
                       type(original_error).__name__, caminho)
        try:
            frame = pd.read_excel(caminho, engine='calamine', header=None, dtype=str)
        except Exception as fallback_error:
            logger.exception('[RCF] Calamine também não conseguiu ler a relação.')
            raise ValueError('Não foi possível ler a relação RCF. Execute 1_instalar.bat novamente e consulte logs/planilha_amanda/planilha_amanda.log.') from fallback_error
        logger.info('[RCF] Leitura alternativa concluída sem alterar o arquivo: %s', caminho)
    return frame

def identificar_colunas(frame):
    """Localiza Nome, Razão Social e CPF/CNPJ na mesma linha de cabeçalho.

    Não supõe letras fixas: relatórios com células mescladas alteram as posições.
    Ambiguidade ou cabeçalho ausente interrompem a leitura para evitar documentos errados.
    """
    for row_idx in range(min(100, len(frame))):
        names, companies, docs = [], [], []
        for col_idx, value in enumerate(frame.iloc[row_idx]):
            key = normalizar_cabecalho(value)
            if key == 'NOME':
                names.append(col_idx)
            elif key == 'RAZAOSOCIAL':
                companies.append(col_idx)
            elif 'CNPJ' in key and 'CPF' in key:
                docs.append(col_idx)
        if len(names) == len(companies) == len(docs) == 1:
            return row_idx, names[0], companies[0], docs[0]
    raise ValueError('Cabeçalhos RCF não identificados com segurança. São necessários Nome, Razão Social e CPF/CNPJ na mesma linha, entre as primeiras 100 linhas.')

def letra_coluna(index):
    result = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        result = chr(65 + rest) + result
    return result
