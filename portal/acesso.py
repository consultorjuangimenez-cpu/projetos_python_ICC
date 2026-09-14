"""Login e verificação central de acesso em todas as rotas de cada app Flask."""
import secrets
import sqlite3
from datetime import timedelta
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for, Response


def configure_access(portal, catalog, mounts, users, secure_cookie=False):
    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def deny(message, status):
        if '/api/' in request.path:
            return jsonify(success=False, message=message, documents=[]), status
        # A renderização pertence ao portal mesmo em requisições dos aplicativos.
        html = portal.jinja_env.get_template('acesso_negado.html').render(message=message)
        return Response(html, status=status, mimetype='text/html', headers={'X-Portal-Access':'denied'})

    def install(app, route=None):
        if not isinstance(app, Flask):
            raise ValueError('A integração de acesso exige aplicativos Flask. Adapte a autenticação antes de cadastrar outro tipo de WSGI.')
        app.config.update(SECRET_KEY=users.secret, SESSION_COOKIE_NAME='icc_portal_session',
                          SESSION_COOKIE_PATH='/', SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=secure_cookie,
                          PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False)
        @app.context_processor
        def access_context():
            return {'csrf_token':csrf_token, 'usuario':getattr(g,'usuario',None)}
        @app.before_request
        def guard():
            g.usuario = users.resolve(session.get('sid'))
            public = route is None and request.endpoint in {'login','health'}
            if not public and not g.usuario:
                if request.method in {'GET','HEAD'} and '/api/' not in request.path:
                    return redirect('/login')
                return deny('Sua sessão expirou. Volte ao portal, entre novamente e repita a operação.',401)
            if route and not (g.usuario['admin'] or route in g.usuario['routes']):
                return deny('Seu usuário não tem permissão para este aplicativo.',403)
            if request.method not in {'GET','HEAD','OPTIONS'}:
                sent = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
                expected = session.get('csrf','')
                if not expected or not isinstance(sent,str) or not secrets.compare_digest(sent,expected):
                    return deny('A página expirou ou o envio não foi validado. Atualize a página e tente novamente.',400)
        @app.after_request
        def secure_headers(response):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
            response.headers['X-Frame-Options']='SAMEORIGIN'
            response.headers['Referrer-Policy']='same-origin'
            return response
    install(portal)
    for route, app in mounts.items():
        install(app,route)

    def admin_only():
        if not g.usuario or not g.usuario['admin']:
            abort(403)

    @portal.route('/login',methods=['GET','POST'])
    def login():
        if g.usuario:
            return redirect('/')
        error=None
        if request.method=='POST':
            sid,error=users.authenticate(request.form.get('username',''),request.form.get('password',''),request.remote_addr or '')
            if sid:
                users.logout(session.get('sid'))
                session.clear()
                session['sid']=sid
                session['csrf']=secrets.token_urlsafe(32)
                session.permanent=True
                return redirect('/')
        return render_template('login.html',error=error), (401 if error else 200)

    @portal.post('/sair')
    def logout():
        users.logout(session.get('sid'))
        session.clear()
        return redirect('/login')

    @portal.get('/admin/usuarios')
    def user_list():
        admin_only()
        return render_template('usuarios.html',users=users.list())

    @portal.route('/admin/usuarios/novo',methods=['GET','POST'])
    @portal.route('/admin/usuarios/<int:uid>',methods=['GET','POST'])
    def user_edit(uid=None):
        admin_only()
        user=users.get(uid) if uid is not None else {'username':'','name':'','admin':False,'active':True,'routes':[]}
        if user is None:
            abort(404)
        error=None
        if request.method=='POST':
            user={**user,'username':request.form.get('username',''),'name':request.form.get('name',''),
                  'admin':request.form.get('admin')=='on','active':request.form.get('active')=='on',
                  'routes':request.form.getlist('routes')}
            password=request.form.get('password','')
            try:
                if password != request.form.get('password_confirm',''):
                    raise ValueError('As senhas não conferem.')
                if not set(user['routes']).issubset({a['rota'] for a in catalog}):
                    raise ValueError('Aplicativo inválido na seleção.')
                users.save(uid,user['username'],user['name'],password,user['admin'],user['active'],user['routes'],g.usuario['id'])
                flash('Usuário salvo. As permissões valem nas próximas requisições; atualize o menu no outro computador.')
                return redirect('/admin/usuarios')
            except sqlite3.IntegrityError:
                error='Este login já está cadastrado.'
            except ValueError as exc:
                error=str(exc)
        return render_template('usuario_editar.html',edited=user,uid=uid,aplicativos=catalog,error=error), (400 if error else 200)

    @portal.route('/minha-senha',methods=['GET','POST'])
    def password_change():
        error=None
        if request.method=='POST':
            try:
                password=request.form.get('password','')
                if password != request.form.get('password_confirm',''):
                    raise ValueError('As senhas não conferem.')
                users.change_password(g.usuario['id'],request.form.get('current',''),password)
                session.clear()
                flash('Senha alterada. Entre novamente com a nova senha.')
                return redirect('/login')
            except ValueError as exc:
                error=str(exc)
        return render_template('senha.html',error=error), (400 if error else 200)

    @portal.errorhandler(403)
    def forbidden(error):
        return deny('Somente administradores podem gerenciar usuários.',403)
