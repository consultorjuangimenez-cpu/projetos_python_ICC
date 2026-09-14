import re
from datetime import datetime
from portal.tarefas import criar_app
from portal.integracao import caminho, CONFIG_APPS


def preparar(req, pasta):
    documento = re.sub(r'[\s./-]', '', req.form.get('documento','')).upper()
    if not re.fullmatch(r'(?:[0-9]{11}|[A-Z0-9]{12}[0-9]{2})', documento):
        raise ValueError('Informe um CPF com 11 dígitos ou CNPJ com 14 caracteres válidos.')
    tipo = req.form.get('tipo','Entrada')
    if tipo not in ('Entrada','Saida','Ambas'):
        raise ValueError('Tipo de movimentação inválido.')
    ano = req.form.get('ano','').strip()
    if not re.fullmatch(r'20[0-9]{2}',ano):
        raise ValueError('Informe um ano de quatro dígitos.')
    texto = req.form.get('chaves','').strip()
    partes = re.split(r'[;,\r\n]+',texto)
    chaves = list(dict.fromkeys(re.sub(r'[\s./-]','',p).upper() for p in partes if p.strip()))
    if not chaves or any(not re.fullmatch(r'[0-9]{6}[A-Z0-9]{12}[0-9]{26}', c) for c in chaves):
        raise ValueError('Cada chave deve conter 44 caracteres válidos. Separe por linha, vírgula ou ponto e vírgula.')
    if len(chaves)>1000:
        raise ValueError('Limite de 1.000 chaves por pesquisa.')
    raiz = caminho('sieg','pasta_xmls')
    if not raiz.is_dir():
        raise ValueError('A pasta de XMLs não está disponível. Confira config_apps.ini e o acesso do servidor.')
    return {'documento':documento,'tipo':tipo,'ano':ano,'chaves':chaves,'raiz':str(raiz)}

ano = CONFIG_APPS.get('sieg','ano',fallback=str(datetime.now().year))
# Valor de configuração validado antes de entrar no template.
if not re.fullmatch(r'20[0-9]{2}',ano): ano=str(datetime.now().year)
campos = '''<label>CPF/CNPJ</label><input name="documento" required>
<label>Movimentação</label><select name="tipo"><option>Entrada</option><option value="Saida">Saída</option><option>Ambas</option></select>
<label>Ano</label><input name="ano" value="'''+ano+'''" pattern="20[0-9]{2}" required>
<label>Chaves de acesso</label><textarea name="chaves" rows="7" required></textarea>'''
app = criar_app(__name__, 'buscar_nfe', 'Buscar NF-es v6.3',
    'Busca no cliente, no emitente e, se necessário, nas demais pastas do HUB SIEG. Confere a chave dentro do XML e inclui o PDF correspondente. A busca global pode demorar.',
    campos, preparar, 'apps.buscar_nfe.worker')
