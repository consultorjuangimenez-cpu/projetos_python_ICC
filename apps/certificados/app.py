"""App Flask montada pelo portal, com permissões centrais preservadas."""
from __future__ import annotations
import base64
import io
import json
import re
import secrets
import sqlite3
import time
import zipfile
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, abort, g, jsonify, request, send_file, render_template, session
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix
from .core import Inventory, config, digest, validade, LABELS, MAX_PFX

BASE = Path(__file__).resolve().parents[2]

def create_app(base=BASE, inventory=None):
    cfg=inventory.cfg if inventory else config(Path(base))
    inv=inventory or Inventory(cfg)
    app=Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=128*1024
    app.extensions['certificados']=inv
    bridge=Flask(__name__+'_agente')
    bridge.config['MAX_CONTENT_LENGTH']=8192

    def login_required(admin=False):
        def deco(fn):
            @wraps(fn)
            def run(*args,**kwargs):
                user=getattr(g,'usuario',None)
                if not user: abort(401,description='Acesse este aplicativo pelo portal autenticado.')
                if admin and not user.get('admin'): abort(403,description='Somente a TI pode alterar senhas e configurar o auxiliar.')
                return fn(*args,**kwargs)
            return run
        return deco

    def via_https_proxy():
        # O módulo aceita operações sensíveis somente quando a conexão veio do
        # proxy HTTPS local. Não confiamos em X-Forwarded-For, portanto
        # request.remote_addr continua sendo o endereço real do proxy (loopback).
        return (request.remote_addr in {'127.0.0.1','::1'}
                and request.headers.get('X-ICC-HTTPS-Proxy')=='1')

    def ready_https():
        # ICC_HTTPS_DIAGNOSTICO_V2
        from .conexao_https import diagnostico
        return diagnostico(request, cfg['url'])['instalacao_https']

    @app.get('/api/diagnostico-https')
    def diagnostico_conexao_https():
        from .conexao_https import diagnostico
        user = getattr(g, 'usuario', None)
        if not user or not user.get('admin'):
            abort(403, description='Diagnóstico disponível somente ao administrador autenticado.')
        return jsonify(diagnostico(request, cfg['url']))

    def bridge_tls():
        from .conexao_https import diagnostico
        result = diagnostico(request, cfg['url'], verificar_caminho=False)
        if not result['instalacao_https']:
            abort(403, description=result['motivo'])

    def alive(row):
        # Revalida a sessão e permissão atuais, inclusive após retirada de acesso.
        path=Path(base)/'dados/usuarios.sqlite3'
        if not path.is_file(): return False
        db=sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)
        try:
            user=db.execute('''SELECT u.admin FROM users u JOIN sessions s ON s.user_id=u.id
              WHERE u.id=? AND u.active=1 AND s.token=? AND s.expires>?''',
              (row['uid'],row['sid_hash'],time.time())).fetchone()
            return bool(user and (user[0] or db.execute(
                'SELECT 1 FROM permissions WHERE user_id=? AND route=?',(row['uid'],row['route'])).fetchone()))
        finally: db.close()

    @app.errorhandler(Exception)
    @bridge.errorhandler(Exception)
    def error(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc,HTTPException):
            return jsonify(erro=exc.description),exc.code
        if isinstance(exc,(ValueError,FileNotFoundError)):
            return jsonify(erro=str(exc) if isinstance(exc,ValueError) else 'Arquivo indisponível. Atualize a lista.'),400
        return jsonify(erro='Falha na operação. Verifique os caminhos e as permissões do serviço.'),500

    @app.after_request
    @bridge.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                                 'Referrer-Policy':'no-referrer','X-Frame-Options':'SAMEORIGIN'})
        return response

    @app.get('/')
    @login_required()
    def home():
        inv.start()
        return render_template('index.html',admin=bool(g.usuario['admin']))

    @app.get('/api/dados')
    @login_required()
    def data():
        inv.start()
        rows,counts,meta=inv.snapshot()
        return jsonify(certificados=rows,contagem=counts,meta=meta,
                       dias_proximo=cfg['days'],instalacao_https=ready_https(),admin=bool(g.usuario['admin']))

    @app.post('/api/atualizar')
    @login_required()
    def refresh():
        # Uma varredura por vez. Cliques simultâneos reutilizam a mesma execução.
        started=inv.start(force=True)
        return jsonify(iniciado=started),202

    @app.get('/api/certificados/<ident>')
    @login_required()
    def details(ident):
        row,path,data=inv.get_file(ident)
        result=dict(data)
        if g.usuario['admin']: result.update(arquivo_original=path.name,caminho=str(path))
        return jsonify(result)

    @app.post('/api/certificados/<ident>/senha')
    @login_required(admin=True)
    def password(ident):
        if not ready_https(): abort(403,description='Use o endereço HTTPS configurado pela TI para enviar a senha corrigida.')
        password=(request.get_json() or {}).get('senha')
        if not isinstance(password,str) or len(password)>512: abort(400,description='Senha inválida.')
        inv.correct(ident,password)
        inv.audit(g.usuario['id'],ident,'senha_corrigida')
        return jsonify(ok=True)

    @app.post('/api/exportar')
    @login_required()
    def export():
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        rows,_,_=inv.snapshot()
        ids=(request.get_json() or {}).get('ids')
        if not isinstance(ids,list) or len(ids)>50000 or any(not isinstance(i,str) for i in ids):
            abort(400,description='Seleção inválida.')
        selected=set(ids); rows=[r for r in rows if r['id'] in selected]
        wb=Workbook(); ws=wb.active; ws.title='Certificados'
        ws.append(['CERTIFICADOS DIGITAIS ICC']); ws.merge_cells('A1:I1')
        counts={s:sum(r['status']==s for r in rows) for s in LABELS}
        ws.append(['Total',len(rows),'Válidos',counts['valido'],'Próximos',counts['proximo'],'Vencidos',counts['vencido']])
        ws.append(['Falhas',counts['erro'],'Ainda não vigentes',counts['futuro']]); ws.append([])
        ws.append(['TIPO','NOME DO CLIENTE','CNPJ/CPF','IDENTIFICAÇÃO DO ARQUIVO','ORIGEM DA SENHA',
                   'STATUS DA VALIDAÇÃO','VENCIMENTO (UTC)','DIAS RESTANTES','STATUS DE VALIDADE'])
        def safe(v):
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')): return "'"+v
            return v
        for r in rows:
            ws.append([safe(v) for v in [r['tipo'],r['cliente'],r['documento'],r['arquivo'],r['origem_senha'],
                      r['validacao'],r['vencimento'],r['dias'],r['status_label']]])
        for line in ws:
            for cell in line:
                cell.fill=PatternFill('solid',fgColor='EDF4FA' if cell.row%2==0 else 'FFFFFF')
                cell.alignment=Alignment(vertical='center')
        for rownum in (1,5):
            for cell in ws[rownum]:
                cell.fill=PatternFill('solid',fgColor='173A5E'); cell.font=Font(color='FFFFFF',bold=True)
        for col,width in zip('ABCDEFGHI',[12,44,23,25,28,52,30,18,28]): ws.column_dimensions[col].width=width
        for line in ws.iter_rows(min_row=6): line[2].number_format='@'
        ws.freeze_panes='D6'; ws.auto_filter.ref=f'A5:I{max(5,ws.max_row)}'; ws.sheet_view.showGridLines=False
        out=io.BytesIO(); wb.save(out); out.seek(0)
        return send_file(out,as_attachment=True,download_name='Certificados_filtrados.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.get('/auxiliar.zip')
    @login_required(admin=True)
    def helper_zip():
        if not ready_https(): abort(403,description='Configure url_publica e acesse este módulo por HTTPS para preparar o auxiliar.')
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for path in (Path(__file__).parent/'auxiliar').iterdir():
                if path.is_file(): z.write(path,path.name)
            z.writestr('config.json',json.dumps({'url':cfg['url']},ensure_ascii=False,indent=2))
        out.seek(0)
        return send_file(out,as_attachment=True,download_name='Auxiliar_Certificados_ICC.zip')

    @app.post('/api/instalar/<ident>')
    @login_required()
    def install(ident):
        if not ready_https(): abort(403,description='A TI precisa habilitar HTTPS e configurar o endereço de instalação.')
        row,path,data=inv.get_file(ident)
        if validade(data,days=cfg['days'])[0] not in {'valido','proximo'}:
            abort(400,description='Certificado vencido, ainda não vigente ou sem leitura válida.')
        import hashlib
        if hashlib.sha256(path.read_bytes()).hexdigest()!=data['sha256']:
            abort(409,description='O certificado mudou na pasta. Atualize a lista antes de instalar.')
        token=secrets.token_urlsafe(32); hashed=digest(token); created=time.time()
        with inv.db() as db:
            pending=db.execute("SELECT count(*) FROM tickets WHERE uid=? AND state='aguardando' AND expires>?",(g.usuario['id'],created)).fetchone()[0]
            if pending>=5: abort(429,description='Há instalações aguardando. Aguarde três minutos e tente novamente.')
            db.execute('''INSERT INTO tickets(hash,cert,uid,sid_hash,route,created,expires,state,sha256,thumbprint)
            VALUES(?,?,?,?,?,?,?,'aguardando',?,?)''',
            (hashed,ident,g.usuario['id'],digest(session.get('sid','')),request.script_root,created,created+180,data['sha256'],data['thumbprint']))
        inv.audit(g.usuario['id'],ident,'instalacao_solicitada')
        return jsonify(uri='icc-cert://instalar/'+token,id=hashed)

    @app.get('/api/instalacao/<ident>')
    @login_required()
    def install_status(ident):
        with inv.db() as db: row=db.execute('SELECT * FROM tickets WHERE hash=? AND uid=?',(ident,g.usuario['id'])).fetchone()
        if not row: abort(404)
        state=row['state']
        if state=='aguardando' and row['expires']<time.time(): state='expirado'
        if state=='recebido' and row['callback_expires']<time.time(): state='sem_confirmacao'
        return jsonify(estado=state,maquina=row['machine'])

    @bridge.post('/resgatar')
    def redeem():
        bridge_tls()
        body=request.get_json() or {}; token=body.get('token',''); machine=body.get('maquina','')
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): abort(400)
        if not isinstance(machine,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',machine): abort(400)
        callback=secrets.token_urlsafe(32)
        with inv.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM tickets WHERE hash=?',(digest(token),)).fetchone()
            if not row or row['state']!='aguardando' or row['expires']<time.time():
                abort(410,description='Solicitação vencida ou já usada. Clique em INSTALAR novamente.')
            if not alive(row): abort(403,description='Sessão encerrada ou permissão retirada.')
            cert,path,data=inv.get_file(row['cert'])
            import hashlib
            raw=path.read_bytes()
            if len(raw)>MAX_PFX or hashlib.sha256(raw).hexdigest()!=row['sha256'] or data['thumbprint']!=row['thumbprint']:
                abort(409,description='Arquivo alterado. Atualize o painel.')
            if validade(data,days=cfg['days'])[0] not in {'valido','proximo'}: abort(400,description='Certificado não vigente.')
            db.execute("UPDATE tickets SET state='recebido',callback=?,callback_expires=?,machine=? WHERE hash=?",
                       (digest(callback),time.time()+600,machine,row['hash']))
        inv.audit(row['uid'],row['cert'],'auxiliar_recebeu',machine)
        return jsonify(pfx=base64.b64encode(raw).decode('ascii'),senha=inv.unseal(cert['password']),
                       cliente=data['cliente'],documento=data['documento'],thumbprint=data['thumbprint'],
                       sha256=data['sha256'],callback=callback)

    @bridge.post('/resultado')
    def result():
        bridge_tls()
        body=request.get_json() or {}; token=body.get('callback',''); state=body.get('estado','')
        if state not in {'instalado','ja_instalado','cancelado','falhou'}: abort(400)
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): abort(400)
        with inv.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM tickets WHERE callback=? AND state='recebido'",(digest(token),)).fetchone()
            if not row or row['callback_expires']<time.time(): abort(410)
            db.execute('UPDATE tickets SET state=?,callback=NULL WHERE hash=?',(state,row['hash']))
        inv.audit(row['uid'],row['cert'],'auxiliar_'+state,row['machine'])
        return jsonify(ok=True)

    # Canal restrito a tokens de uso único. Não concede sessão nem expõe outras rotas.
    # A autenticação normal continua no app principal, instalada por portal.acesso.
    # Caddy termina o TLS e encaminha somente scheme/host. O endereço remoto
    # NÃO é reescrito, permitindo confirmar que o pedido veio do loopback.
    internal=DispatcherMiddleware(app.wsgi_app,{'/agente-api':bridge})
    app.wsgi_app=ProxyFix(internal,x_proto=1,x_host=1)
    return app

app=create_app()
