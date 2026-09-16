"""Aplicativo Flask montado pelo catálogo e protegido pelo acesso central do portal."""
from datetime import date, datetime, timedelta
from functools import wraps
import secrets
import threading
import time
from zoneinfo import ZoneInfo
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from .recurrence import KINDS, WEEKDAYS, describe, integer
from .settings import REMETENTE, load_settings
from .store import Store
from .validation import email, task_input
from .versao import __version__

STATUS = {'ATIVO':'Ativo', 'PAUSADO':'Pausado', 'CONCLUIDO':'Concluído', 'CANCELADO':'Cancelado'}
DELIVERY_STATUS = {'WAITING':'Na fila', 'SENDING':'Enviando', 'SENT':'Enviado', 'ERROR':'Erro',
                   'UNKNOWN':'Conferência necessária', 'CANCELED':'Cancelado', 'DISCARDED':'Encerrado sem reenvio'}
DELIVERY_KINDS = {'SCHEDULED':'Agendado', 'MANUAL':'Manual', 'TEST':'Teste'}


def create_app(settings=None, store=None):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 256 * 1024
    cache, lock = {}, threading.Lock()
    if settings:
        cache['settings'] = settings
    if store:
        cache['store'] = store

    def protected(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            # Os before_request do portal já executaram antes de chegar à view.
            user = getattr(g, 'usuario', None)
            if not user or not app.secret_key:
                abort(401, description='Abra este aplicativo pelo Portal de Aplicações e faça login.')
            if not user.get('admin') and request.script_root not in user.get('routes', []):
                abort(403)
            if request.method == 'POST':
                sent, expected = request.form.get('csrf_token',''), session.get('csrf','')
                if not expected or not secrets.compare_digest(sent, expected):
                    abort(400, description='A página expirou. Atualize e tente novamente.')
            with lock:
                if 'settings' not in cache:
                    cache['settings'] = load_settings()
                if 'store' not in cache:
                    cache['store'] = Store(cache['settings'].db_path)
            g.settings, g.store = cache['settings'], cache['store']
            return view(*args, **kwargs)
        return wrapped

    def action_token(action, task_id=0, revision=0):
        serializer = URLSafeTimedSerializer(app.secret_key, salt='icc-lembretes-actions-v1')
        return serializer.dumps({'action':action,'task':task_id,'revision':revision,'user':g.usuario['id'],'nonce':secrets.token_hex(16)})

    def read_action(token, action, task_id=0):
        try:
            data = URLSafeTimedSerializer(app.secret_key, salt='icc-lembretes-actions-v1').loads(token, max_age=900)
            if data['action'] != action or data['task'] != task_id or data['user'] != g.usuario['id']:
                raise ValueError()
            return data
        except (BadSignature, ValueError, KeyError, TypeError):
            raise ValueError('A confirmação expirou. Abra a ação novamente.') from None

    def pager(total, page):
        count = max(1, (total+49)//50)
        def link(number):
            args = request.args.to_dict()
            args['page'] = number
            return url_for(request.endpoint, **args)
        return {'page':page,'pages':count,'prev':link(page-1) if page>1 else None,'next':link(page+1) if page<count else None}

    @app.template_filter('dt')
    def dt(value, zone=None):
        if value is None:
            return 'Não há'
        zone = zone or (g.settings.timezone if getattr(g,'settings',None) else 'America/Cuiaba')
        return datetime.fromtimestamp(value, ZoneInfo(zone)).strftime('%d/%m/%Y %H:%M')

    @app.context_processor
    def common():
        return {'statuses':STATUS,'kinds':KINDS,'weekdays':WEEKDAYS,'describe':describe,
                'delivery_status':DELIVERY_STATUS,'delivery_kinds':DELIVERY_KINDS,
                'version':__version__,'sender':REMETENTE,'now_ts':int(time.time())}

    @app.get('/')
    @protected
    def index():
        now = int(time.time())
        filters = request.args.to_dict()
        try:
            page = integer(filters.get('page', 1), 'Página', 1, 100000)
            for key, dbkey, extra in [('from_date','from_ts',0),('to_date','to_ts',1)]:
                if filters.get(key):
                    day = date.fromisoformat(filters[key])+timedelta(days=extra)
                    filters[dbkey] = int(datetime.combine(day, datetime.min.time(), g.settings.zone).timestamp())
            if filters.get('from_ts') and filters.get('to_ts') and filters['from_ts']>=filters['to_ts']:
                raise ValueError('O fim do período deve ser igual ou posterior ao início.')
        except ValueError as exc:
            abort(400, description=str(exc))
        tasks, total = g.store.list_tasks(g.usuario, filters, page)
        worker = g.store.worker_info()
        online = worker and now-worker['heartbeat'] <= 180
        return render_template('index.html', tasks=tasks, total=total, filters=filters,
            metrics=g.store.dashboard(g.usuario, now, g.settings.zone), worker=worker,
            online=online, pager=pager(total,page), timezone=g.settings.timezone)

    def form_values(task=None):
        if request.method == 'POST':
            result = request.form.to_dict()
            result['weekdays'] = request.form.getlist('weekdays')
            result['links'] = [{'label':a,'value':b} for a,b in zip(request.form.getlist('link_label'),request.form.getlist('link_value'))]
            return result
        if task:
            rule = task['rule']
            return {**task, **rule, 'custom_mode':rule.get('mode','days'), 'weekdays':[str(n) for n in rule.get('weekdays',[])], 'interval':rule.get('interval',1), 'monthday':rule.get('monthday',10)}
        when = datetime.now(g.settings.zone)+timedelta(minutes=15)
        return {'name':'','email':'','title':'','description':'','start_date':when.date().isoformat(),
                'clock':when.strftime('%H:%M'), 'kind':'none', 'custom_mode':'days', 'interval':1,
                'monthday':10,'weekdays':[],'links':[],'revision':0}

    @app.route('/nova', methods=['GET','POST'])
    @app.route('/tarefas/<int:task_id>/editar', methods=['GET','POST'])
    @protected
    def edit(task_id=None):
        old = g.store.get(task_id,g.usuario) if task_id else None
        error = None
        if request.method == 'POST':
            try:
                revision = integer(request.form.get('revision',0),'Versão',0,1000000000)
                zone = old['timezone'] if old else g.settings.timezone
                data = task_input(request.form, zone, int(time.time()), old)
                task_id = g.store.save(data,g.usuario,task_id,revision)
                flash('Tarefa salva. O agendador enviará o lembrete na data programada.', 'success')
                return redirect(url_for('detail',task_id=task_id),code=303)
            except ValueError as exc:
                error = str(exc)
        return render_template('form.html',form=form_values(old),task=old,error=error,
                               timezone=old['timezone'] if old else g.settings.timezone), (400 if error else 200)

    @app.get('/tarefas/<int:task_id>')
    @protected
    def detail(task_id):
        task = g.store.get(task_id,g.usuario)
        history, _ = g.store.history(g.usuario,task_id)
        return render_template('detail.html',task=task,history=history,pending=g.store.pending(g.usuario,task_id),audits=g.store.audits(task_id,g.usuario))

    @app.route('/tarefas/<int:task_id>/acao/<action>', methods=['GET','POST'])
    @protected
    def action(task_id, action):
        task = g.store.get(task_id,g.usuario)
        labels = {'send':'Enviar agora','pause':'Pausar tarefa','resume':'Reativar tarefa','cancel':'Cancelar tarefa'}
        if action not in labels:
            abort(404)
        if request.method == 'POST':
            try:
                data = read_action(request.form.get('action_token',''),action,task_id)
                if action == 'send':
                    g.store.queue_manual(task_id,g.usuario,'manual:'+data['nonce'],int(time.time()),data['revision'])
                    flash('Envio manual colocado na fila. A programação futura foi preservada.', 'success')
                else:
                    g.store.change_status(task_id,action,g.usuario,data['revision'],int(time.time()))
                    flash('Status atualizado.', 'success')
                return redirect(url_for('detail',task_id=task_id),code=303)
            except ValueError as exc:
                flash(str(exc),'error')
                return redirect(url_for('detail',task_id=task_id),code=303)
        return render_template('confirm.html',task=task,action=action,label=labels[action],token=action_token(action,task_id,task['revision']))

    @app.get('/historico')
    @protected
    def history():
        page = integer(request.args.get('page',1),'Página',1,100000)
        rows,total = g.store.history(g.usuario,page=page,result=request.args.get('result'))
        return render_template('history.html',history=rows,pending=g.store.pending(g.usuario),total=total,pager=pager(total,page))

    @app.post('/envios/<int:delivery_id>/<action>')
    @protected
    def resolve(delivery_id,action):
        try:
            g.store.resolve(delivery_id,action,g.usuario,int(time.time()))
            flash('Ocorrência atualizada. Consulte o resultado no histórico.', 'success')
        except ValueError as exc:
            flash(str(exc),'error')
        return redirect(url_for('history'),code=303)

    @app.route('/teste-email', methods=['GET','POST'])
    @protected
    def test_email():
        if not g.usuario.get('admin'):
            abort(403)
        error = None
        if request.method == 'POST':
            try:
                recipient = email(request.form.get('email',''))
                data = read_action(request.form.get('action_token',''),'test')
                g.store.queue_test(recipient,g.usuario,'test:'+data['nonce'],int(time.time()),g.settings.timezone)
                flash('Teste colocado na fila do agendador. Consulte o histórico e a caixa de entrada do destinatário.', 'success')
                return redirect(url_for('history'),code=303)
            except ValueError as exc:
                error = str(exc)
        return render_template('test_email.html',token=action_token('test'),error=error,settings=g.settings,worker=g.store.worker_info()), (400 if error else 200)

    @app.errorhandler(LookupError)
    def missing(error):
        return render_template('error.html',message='Tarefa ou envio não encontrado.'),404

    @app.errorhandler(ValueError)
    def invalid(error):
        return render_template('error.html',message=str(error)),400

    for code in (400,401,403,404,413):
        def handler(error):
            descriptions = {400:'Dados inválidos. Confira os campos.',401:'Faça login pelo portal.',403:'Acesso não permitido.',404:'Página não encontrada.',413:'O formulário excede o tamanho permitido.'}
            return render_template('error.html',message=descriptions.get(error.code,'Não foi possível continuar.')),error.code
        app.register_error_handler(code,handler)
    return app


app = create_app()
