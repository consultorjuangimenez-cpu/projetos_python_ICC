from portal.tarefas import criar_app, arquivo_enviado
from datetime import datetime
import re
import pandas as pd

def preparar(req, pasta):
    arquivo = arquivo_enviado(req, 'planilha', pasta/'entrada', {'.xlsx'})
    df = pd.read_excel(arquivo, sheet_name='Plan1', dtype={'CHAVE DE ACESSO': str})
    if not {'CHAVE DE ACESSO','VALOR'}.issubset(df.columns):
        raise ValueError('A aba Plan1 deve conter CHAVE DE ACESSO e VALOR.')
    linhas = 0
    for _, row in df.iterrows():
        chave = str(row['CHAVE DE ACESSO']).strip() if pd.notna(row['CHAVE DE ACESSO']) else ''
        if not chave or chave == 'nan': break
        if not re.fullmatch(r'[0-9]{44}', chave):
            raise ValueError('Cada chave deve conter 44 dígitos e estar armazenada como texto no Excel.')
        try:
            valor = float(row['VALOR'])
            import math
            if not math.isfinite(valor) or valor <= 0: raise ValueError()
        except (TypeError, ValueError):
            raise ValueError('A coluna VALOR deve conter valores numéricos positivos.')
        linhas += 1
    if not linhas: raise ValueError('Nenhuma linha para emitir foi encontrada.')
    dados = {key: req.form.get(key,'').strip() for key in ('cnpj_cliente','periodo_ref','especificacao_receita','destinatario','data_vencimento')}
    dados['cnpj_cliente'] = re.sub(r'\D','', dados['cnpj_cliente'])
    if len(dados['cnpj_cliente']) != 14: raise ValueError('Informe um CNPJ com 14 dígitos.')
    datetime.strptime(dados['periodo_ref'], '%m/%Y')
    datetime.strptime(dados['data_vencimento'], '%d/%m/%Y')
    if dados['especificacao_receita'] not in {'2817','9895'} or not dados['destinatario']:
        raise ValueError('Confira a receita e o destinatário.')
    dados['tipo_emissao'] = 'CNPJ'
    return {'planilha':arquivo, 'dados':dados, 'total':linhas}

CAMPOS = '<p class="note">A emissão ocorre na SEFAZ. Confira os dados antes de iniciar. Se houver falha de download, verifique a emissão antes de repetir.</p>\n<label>Planilha Excel (aba Plan1)</label><input type="file" name="planilha" accept=".xlsx" required>\n<label>CNPJ do cliente</label><input name="cnpj_cliente" required>\n<label>Período de referência (mm/aaaa)</label><input name="periodo_ref" placeholder="09/2026" required>\n<label>Receita</label><select name="especificacao_receita"><option value="2817">2817 - ICMS ST ENTRAD.INTEREST.DEST.POR OP C/IE</option><option value="9895">9895 - OUTRAS RECEITAS</option></select>\n<label>CPF/CNPJ/IE do destinatário</label><input name="destinatario" required>\n<label>Vencimento (dd/mm/aaaa)</label><input name="data_vencimento" placeholder="30/09/2026" required>'
app = criar_app(__name__, 'emite_guia', 'Emitir guias SEFAZ/MT',
    'Envie a planilha e preencha os dados para emitir por CNPJ. Os PDFs serão disponibilizados para download nesta execução.',
    CAMPOS, preparar, 'apps.emite_guia.worker')
