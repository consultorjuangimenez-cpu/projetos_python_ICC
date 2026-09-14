import os
import json
import re
import uuid
import shutil
import threading
from pathlib import Path
from functools import wraps
from portal.integracao import caminho, CONFIG_APPS
from portal.settings import BASE_DIR
import sys
import smtplib
import ssl
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

from flask import Flask, render_template_string, request, flash, redirect, url_for, send_file, g, abort
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
_PROCESSAMENTO_LOCK = threading.Lock()
_EMAIL_LOCK = threading.Lock()

def serializar(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _PROCESSAMENTO_LOCK.acquire(blocking=False):
            raise ValueError('A planilha está sendo processada. Aguarde e tente novamente.')
        try:
            return func(*args, **kwargs)
        finally:
            _PROCESSAMENTO_LOCK.release()
    return wrapper

def metadados(nome):
    if not isinstance(nome, str) or not re.fullmatch(r'RELATORIO_(VITORIA|ESCRITORIO)_[a-f0-9]{32}\.xlsx', nome):
        abort(404)
    path = Path(PASTA_RELATORIOS)/(nome+'.json')
    try:
        item = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        abort(404)
    if item['owner'] != g.usuario['id']:
        abort(404)
    return path, item


# Pasta para armazenar relatórios gerados
PASTA_RELATORIOS = str(BASE_DIR/'dados/apps/aberturas/relatorios')
os.makedirs(PASTA_RELATORIOS, exist_ok=True)

# ⚠️ NOME / CAMINHO DA PLANILHA PRINCIPAL
# Certifique-se de que este caminho está correto no seu computador.
# O "r" antes das aspas é importante para o Python ler as barras invertidas corretamente.
PLANILHA_PRINCIPAL = str(caminho('aberturas', 'planilha'))

# Configurações do servidor SMTP KingHost
SMTP_SERVER = CONFIG_APPS.get('aberturas', 'smtp_servidor', fallback='smtp.kinghost.net')
SMTP_PORT = CONFIG_APPS.getint('aberturas', 'smtp_porta', fallback=465)
EMAIL_REMETENTE = CONFIG_APPS.get('aberturas', 'email_remetente', fallback='')
SENHA_REMETENTE = os.environ.get('PORTAL_SMTP_SENHA', '')

# E-mails padrão com destinatários (separados por vírgula)
EMAIL_VITORIA_DEFAULT = CONFIG_APPS.get('aberturas', 'email_vitoria', fallback='')
EMAIL_ESCRITORIO_DEFAULT = CONFIG_APPS.get('aberturas', 'email_escritorio', fallback='')


def enviar_email_seguro(destino_email, assunto, corpo, caminho_anexo):
    """Envia o e-mail via SSL (Porta 465) com o servidor da KingHost para múltiplos destinatários."""
    if not EMAIL_REMETENTE or not SENHA_REMETENTE:
        return False, 'Configure o remetente em config_apps.ini e a variável PORTAL_SMTP_SENHA no servidor.'
    if not destino_email:
        return False, "E-mail de destino não informado."

    try:
        # Trata lista de e-mails separados por vírgula
        destinatarios = [e.strip() for e in destino_email.split(',') if e.strip()]
        if not destinatarios or any(not re.fullmatch(r'[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+', e) for e in destinatarios):
            return False, 'Confira os endereços de e-mail; separe os destinatários por vírgula.'


        msg = MIMEMultipart()
        msg['From'] = EMAIL_REMETENTE
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = assunto

        msg.attach(MIMEText(corpo, 'plain'))

        if caminho_anexo and os.path.exists(caminho_anexo):
            with open(caminho_anexo, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(caminho_anexo)}')
            msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=12) as server:
            server.login(EMAIL_REMETENTE, SENHA_REMETENTE)
            server.send_message(msg)

        return True, "E-mail enviado com sucesso!"
    except Exception as e:
        print(f"Erro no envio do e-mail: {e}")
        return False, f"Não foi possível enviar por e-mail ({str(e)})."


def extrair_data(valor):
    """Converte qualquer formato de data da coluna E de forma segura."""
    if isinstance(valor, datetime):
        return valor.date()
    elif isinstance(valor, date):
        return valor
    elif isinstance(valor, str):
        v = valor.strip()
        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
            try:
                return datetime.strptime(v, fmt).date()
            except ValueError:
                pass
    return None


@serializar
def processar_planilha(data_inicio, data_fim, destino, apenas_nao_enviados=True):
    if not os.path.exists(PLANILHA_PRINCIPAL):
        raise FileNotFoundError(f"Planilha principal não foi encontrada no caminho especificado: {PLANILHA_PRINCIPAL}")

    if destino not in {'VITORIA', 'ESCRITORIO'}:
        raise ValueError('Destino inválido.')
    if bool(data_inicio) != bool(data_fim) or (data_inicio and data_inicio > data_fim):
        raise ValueError('Informe as duas datas em ordem, ou deixe ambas vazias.')
    origem = Path(PLANILHA_PRINCIPAL)
    inicial = (origem.stat().st_mtime_ns, origem.stat().st_size)
    wb = openpyxl.load_workbook(PLANILHA_PRINCIPAL)
    sheet_name = '2026' if '2026' in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]

    # Coluna I (9) -> Vitória SOMENTE | Coluna J (10) -> Escritório SOMENTE
    col_alvo = 9 if destino == 'VITORIA' else 10
    registros_filtrados = []

    for r in range(1, ws.max_row + 1):
        val_empresa = ws.cell(row=r, column=2).value
        val_data = ws.cell(row=r, column=5).value
        val_status_especifico = ws.cell(row=r, column=col_alvo).value

        if not val_empresa or str(val_empresa).strip().upper() in ['EMPRESA', 'ABERTURA', 'ALTERAÇÃO', 'BAIXA']:
            continue

        dt = extrair_data(val_data)
        if dt is None:
            continue

        status_str = str(val_status_especifico).strip().lower() if val_status_especifico else ''
        ja_enviado = (status_str == 'sim')

        dentro_do_periodo = True
        if data_inicio and data_fim:
            dentro_do_periodo = (data_inicio <= dt <= data_fim)

        if dentro_do_periodo:
            if apenas_nao_enviados and ja_enviado:
                continue

            dados_linha = [ws.cell(row=r, column=col).value or '-' for col in range(2, 9)]
            dados_linha[3] = dt.strftime('%d/%m/%Y')
            registros_filtrados.append(dados_linha)

            ws.cell(row=r, column=col_alvo).value = 'Sim'

    if not registros_filtrados:
        return "", 0

    # A marcação Sim permanece no momento da geração, conforme o app enviado.
    # Salvar ocorre depois de gerar o relatório para evitar marcar caso a geração falhe.


    # -------------------------------------------------------------
    # Criação da Nova Planilha Formatada Exclusiva do Destino
    # -------------------------------------------------------------
    wb_novo = openpyxl.Workbook()
    ws_novo = wb_novo.active
    ws_novo.title = f"Enviados_{destino}"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Arial", size=10)

    # Bordas Pretas Bem Visíveis
    border_side_black = Side(style='thin', color='000000')
    border_thick_black = Side(style='medium', color='000000')

    # Borda do cabeçalho (Preta fina nas laterais/topo + Preta grossa na base)
    header_border = Border(left=border_side_black, right=border_side_black, top=border_side_black, bottom=border_thick_black)

    # Borda FINA PRETA completa para todas as células de dados
    cell_border = Border(left=border_side_black, right=border_side_black, top=border_side_black, bottom=border_side_black)

    headers = ['EMPRESA', 'CNPJ', 'CÓDIGO', 'DATA', 'REG. TRIBUTAÇÃO', 'RESPONSÁVEL / DETALHES', 'TIPO']
    ws_novo.append(headers)

    # Aplica formatação ao cabeçalho
    for col_num in range(1, len(headers) + 1):
        cell = ws_novo.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = header_border
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Adiciona as linhas de dados
    for linha in registros_filtrados:
        ws_novo.append(linha)

    # Aplica bordas pretas visíveis em CADA CÉLULA das linhas inseridas
    for row in ws_novo.iter_rows(min_row=2, max_row=len(registros_filtrados) + 1, min_col=1, max_col=7):
        for cell in row:
            cell.font = data_font
            cell.border = cell_border
            cell.alignment = Alignment(vertical='center')

    # Ajusta largura das colunas
    for col in ws_novo.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws_novo.column_dimensions[col_letter].width = max(max_len + 4, 12)

    nome_arquivo = f"RELATORIO_{destino}_{uuid.uuid4().hex}.xlsx"
    caminho_completo = os.path.join(PASTA_RELATORIOS, nome_arquivo)
    wb_novo.save(caminho_completo)
    if inicial != (origem.stat().st_mtime_ns, origem.stat().st_size):
        Path(caminho_completo).unlink(missing_ok=True)
        raise ValueError('A planilha foi alterada durante o processamento. Repita com a planilha fechada no Excel.')
    backups = BASE_DIR/'dados/apps/aberturas/backups'
    backups.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origem, backups/(uuid.uuid4().hex+'.xlsx'))
    temporario = origem.with_name(origem.stem+'.portal-'+uuid.uuid4().hex+'.xlsx')
    try:
        wb.save(temporario)
        os.replace(temporario, origem)
    finally:
        temporario.unlink(missing_ok=True)
        wb.close()
    meta = {'owner':g.usuario['id'], 'destino':destino, 'quantidade':len(registros_filtrados), 'enviado':False}
    Path(caminho_completo+'.json').write_text(json.dumps(meta), encoding='utf-8')

    return nome_arquivo, len(registros_filtrados)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <title>Planilha de Alterações</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #eef2f5; margin: 0; padding: 30px; }
        .container { max-width: 580px; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin: auto; }
        h2 { color: #1f4e78; margin-top: 0; text-align: center; }
        p.subtitle { text-align: center; color: #666; font-size: 14px; margin-bottom: 25px; }
        label { font-weight: bold; display: block; margin-top: 15px; color: #333; font-size: 14px; }
        input[type="date"], input[type="text"], input[type="email"], select { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        .checkbox-container { display: flex; align-items: center; margin-top: 15px; }
        .checkbox-container input { margin-right: 10px; width: 18px; height: 18px; }
        
        button, .btn-download, .btn-email { width: 100%; margin-top: 15px; padding: 12px; background-color: #1f4e78; color: white; border: none; border-radius: 6px; font-size: 16px; cursor: pointer; font-weight: bold; text-align: center; text-decoration: none; display: block; box-sizing: border-box; }
        button:hover { background-color: #143552; }
        .btn-download { background-color: #28a745; }
        .btn-download:hover { background-color: #218838; }
        .btn-email { background-color: #17a2b8; }
        .btn-email:hover { background-color: #138496; }

        .alert { padding: 12px; margin-bottom: 15px; border-radius: 6px; font-weight: bold; text-align: center; font-size: 14px; }
        .alert-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-warning { background-color: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
        .alert-info { background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .alert-danger { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }

        .painel-validacao { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 20px; margin-bottom: 25px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Planilha de Alterações</h2>
        <p class="subtitle">Aba '2026' | Leitura Automática ou Por Período</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% if arquivo_download %}
            <div class="painel-validacao">
                <p style="margin-top:0; font-weight:bold; color:#1f4e78; text-align:center;">Passo 1: Baixe e Valide a Planilha</p>
                <a href="{{ url_for('download_file', filename=arquivo_download) }}" class="btn-download">1. Baixar Planilha para Validação</a>
                
                <hr style="margin: 20px 0; border: 0; border-top: 1px solid #dee2e6;">
                
                <form method="POST" action="{{ url_for('enviar_email_confirmado') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <input type="hidden" name="arquivo_nome" value="{{ arquivo_download }}">
                    <input type="hidden" name="destino" value="{{ destino_selecionado }}">
                    <input type="hidden" name="qtd_registros" value="{{ qtd_registros }}">
                    
                    <label for="email_destino_envio">Passo 2: Após Validar, Envie por E-mail (Múltiplos com vírgula):</label>
                    <input type="text" id="email_destino_envio" name="email_destino_envio" value="{{ email_destino_valor }}" required>
                    
                    <button type="submit" class="btn-email">2. Confirmar e Enviar E-mail</button>
                </form>
            </div>
        {% endif %}

        <p>Ao gerar, a coluna I ou J será marcada como Sim, como na versão original. Mantenha a planilha principal fechada no Excel.</p>
        {% if historico %}<details><summary>Meus relatórios</summary><ul>{% for item in historico %}<li><a href="{{ url_for('index', relatorio=item.nome) }}">{{ item.destino }}: {{ item.quantidade }} registro(s){% if item.enviado %} · enviado{% endif %} · {{ item.nome }}</a></li>{% endfor %}</ul></details>{% endif %}
        <form method="POST" action="{{ url_for('index') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <label for="data_inicio">Data Inicial:</label>
            <input type="date" id="data_inicio" name="data_inicio">

            <label for="data_fim">Data Final:</label>
            <input type="date" id="data_fim" name="data_fim">

            <label for="destino">Destino:</label>
            <select id="destino" name="destino" onchange="atualizarEmail(this.value)">
                <option value="VITORIA">Vitória</option>
                <option value="ESCRITORIO">Escritório</option>
            </select>

            <label for="email_destino">E-mail do Destinatário:</label>
            <input type="text" id="email_destino" name="email_destino" value="{{ email_vitoria }}">

            <div class="checkbox-container">
                <input type="checkbox" id="apenas_nao_enviados" name="apenas_nao_enviados" checked>
                <label for="apenas_nao_enviados" style="margin-top:0; font-weight:normal;">Filtrar apenas registros <b>NÃO ENVIADOS</b></label>
            </div>

            <button type="submit">Processar e Gerar Planilha</button>
        </form>
    </div>

    <script>
        function atualizarEmail(destino) {
            const emailInput = document.getElementById('email_destino');
            if (destino === 'VITORIA') {
                emailInput.value = {{ email_vitoria|tojson }};
            } else {
                emailInput.value = {{ email_escritorio|tojson }};
            }
        }
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    arquivo_download = None
    destino_selecionado = None
    email_destino_valor = None
    qtd_registros = 0

    if request.method == 'POST':
        try:
            str_inicio = request.form.get('data_inicio', '').strip()
            str_fim = request.form.get('data_fim', '').strip()

            dt_inicio = datetime.strptime(str_inicio, '%Y-%m-%d').date() if str_inicio else None
            dt_fim = datetime.strptime(str_fim, '%Y-%m-%d').date() if str_fim else None

            destino = request.form['destino']
            email_dest = request.form.get('email_destino', '').strip()
            apenas_nao_enviados = 'apenas_nao_enviados' in request.form

            nome_arquivo, qtd = processar_planilha(dt_inicio, dt_fim, destino, apenas_nao_enviados)

            if qtd > 0:
                arquivo_download = nome_arquivo
                destino_selecionado = destino
                email_destino_valor = email_dest
                qtd_registros = qtd
                coluna_nome = "Coluna I (Vitória)" if destino == 'VITORIA' else "Coluna J (Escritório)"
                
                flash(f"Sucesso! {qtd} registro(s) encontrado(s) e atualizado(s) na {coluna_nome}. Baixe o arquivo para validar antes de enviar.", 'success')
            else:
                flash(f"Nenhum registro pendente foi encontrado para {destino.capitalize()}.", 'warning')

        except Exception as e:
            flash(f"Erro no processamento: {str(e)}", 'danger')

    historico = []
    for p in Path(PASTA_RELATORIOS).glob('*.xlsx.json'):
        try:
            item = json.loads(p.read_text(encoding='utf-8'))
            if item['owner'] == g.usuario['id']:
                historico.append({'nome':p.name[:-5], **item})
        except (ValueError, OSError, KeyError):
            continue
    if request.method == 'GET' and request.args.get('relatorio'):
        nome = request.args['relatorio']
        _, item = metadados(nome)
        arquivo_download = nome
        destino_selecionado = item['destino']
        qtd_registros = item['quantidade']
        email_destino_valor = EMAIL_VITORIA_DEFAULT if item['destino']=='VITORIA' else EMAIL_ESCRITORIO_DEFAULT
    return render_template_string(
        HTML_TEMPLATE,
        historico=historico,
        email_vitoria=EMAIL_VITORIA_DEFAULT,
        email_escritorio=EMAIL_ESCRITORIO_DEFAULT,
        arquivo_download=arquivo_download,
        destino_selecionado=destino_selecionado,
        email_destino_valor=email_destino_valor,
        qtd_registros=qtd_registros
    )


@app.route('/enviar_email_confirmado', methods=['POST'])
def enviar_email_confirmado():
    """Rota acionada apenas quando o usuário clica no botão de enviar após a validação."""
    nome_arquivo = request.form.get('arquivo_nome')
    destino = request.form.get('destino')
    email_dest = request.form.get('email_destino_envio', '').strip()
    meta_path, registro = metadados(nome_arquivo)
    qtd = registro['quantidade']
    destino = registro['destino']

    caminho_anexo = os.path.join(PASTA_RELATORIOS, nome_arquivo)

    if os.path.exists(caminho_anexo) and email_dest:
        # 1. Obtendo a data e hora atual
        agora = datetime.now()
        hora_atual = agora.hour
        
        # 2. Definindo a saudação com base na hora
        if hora_atual < 12:
            saudacao = "Bom dia"
        elif hora_atual < 18:
            saudacao = "Boa tarde"
        else:
            saudacao = "Boa noite"
            
        # 3. Dicionário para ter os meses em português (evita depender da linguagem do servidor)
        meses = {
            1: 'janeiro', 2: 'fevereiro', 3: 'março', 4: 'abril',
            5: 'maio', 6: 'junho', 7: 'julho', 8: 'agosto',
            9: 'setembro', 10: 'outubro', 11: 'novembro', 12: 'dezembro'
        }
        mes_corrente = meses[agora.month]
        ano_corrente = agora.year

        # 4. Ajustando o assunto e o corpo conforme solicitado
        assunto = f"Relatório Validado de Alterações e Aberturas - {mes_corrente.capitalize()}"
        corpo = f"{saudacao},\n\nSegue em anexo a planilha com as alterações/aberturas referente a {mes_corrente} de {ano_corrente}."
        
        with _EMAIL_LOCK:
            meta_path, registro = metadados(nome_arquivo)
            if registro.get('enviado'):
                flash('Este relatório já foi enviado.', 'info')
                return redirect(url_for('index'))
            if registro.get('envio_iniciado'):
                flash('Há um envio anterior sem confirmação. Confira o recebimento antes de uma nova tentativa; solicite revisão à TI.', 'warning')
                return redirect(url_for('index'))
            if not EMAIL_REMETENTE or not SENHA_REMETENTE:
                flash('Configure o remetente e PORTAL_SMTP_SENHA no servidor.', 'warning')
                return redirect(url_for('index'))
            emails = [e.strip() for e in email_dest.split(',') if e.strip()]
            if not emails or any(not re.fullmatch(r'[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+', e) for e in emails):
                flash('Confira os endereços de e-mail.', 'warning')
                return redirect(url_for('index'))
            registro['envio_iniciado'] = datetime.now().isoformat()
            registro['destinatarios_envio'] = email_dest
            meta_path.write_text(json.dumps(registro), encoding='utf-8')
            sucesso_email, msg_email = enviar_email_seguro(email_dest, assunto, corpo, caminho_anexo)
            if sucesso_email:
                registro['enviado'] = True
                meta_path.write_text(json.dumps(registro), encoding='utf-8')
        
        if sucesso_email:
            flash(f"E-mail enviado com sucesso para {email_dest}!", 'info')
        else:
            flash(msg_email, 'warning')
    else:
        flash("Não foi possível localizar o arquivo ou o e-mail informado.", 'danger')

    return redirect(url_for('index'))


@app.route('/download/<filename>')
def download_file(filename):
    metadados(filename)
    caminho = os.path.join(PASTA_RELATORIOS, filename)
    if os.path.exists(caminho):
        return send_file(caminho, as_attachment=True)
    flash("Arquivo não encontrado.", 'danger')
    return redirect(url_for('index'))


