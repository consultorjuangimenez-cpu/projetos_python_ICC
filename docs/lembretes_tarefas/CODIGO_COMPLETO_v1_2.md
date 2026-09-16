# Código completo — partes alteradas e adicionadas na versão 1.2.0

Este documento contém os arquivos completos aplicados ao projeto, preservando seus caminhos. Testes e documentação de migração acompanham o ZIP.

## apps/lembretes_tarefas/app.py

```python
"""Aplicativo Flask montado pelo catálogo e protegido pelo acesso central do portal."""
from datetime import date, datetime, timedelta
from functools import wraps
import secrets
import threading
import time
from zoneinfo import ZoneInfo
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer
from .recurrence import BUSINESS_DAYS, KINDS, WEEKDAYS, describe, integer
from .settings import REMETENTE, load_settings
from .store import Store
from .validation import PRIORITIES, email, task_input
from .calendar import national_holidays, sorriso_holidays
from .clients import certificate_clients
from .versao import __version__

STATUS = {'ATIVO':'Ativo', 'PAUSADO':'Pausado', 'CONCLUIDO':'Programação encerrada', 'CANCELADO':'Cancelado'}
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
                'business_days':BUSINESS_DAYS,'priorities':PRIORITIES,
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
            return {**task, **rule, 'deadline':datetime.fromtimestamp(task['deadline_ts'], ZoneInfo(task['timezone'])).strftime('%Y-%m-%dT%H:%M') if task.get('deadline_ts') else '',
                    'custom_mode':rule.get('mode','days'), 'weekdays':[str(n) for n in rule.get('weekdays',[])], 'interval':rule.get('interval',1), 'monthday':rule.get('monthday',10)}
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
                submitted = request.form.copy()
                if submitted.get('collaborator_id'):
                    collaborator_id = integer(submitted['collaborator_id'],'Colaborador',1,2147483647)
                    contact = g.store.get_collaborator(collaborator_id,active_only=True)
                    submitted['name'], submitted['email'] = contact['name'], contact['email']
                data = task_input(submitted, zone, int(time.time()), old, g.store.calendar())
                task_id = g.store.save(data,g.usuario,task_id,revision)
                flash('Tarefa salva. O agendador enviará o lembrete na data programada.', 'success')
                return redirect(url_for('detail',task_id=task_id),code=303)
            except ValueError as exc:
                error = str(exc)
        clients, client_notice = certificate_clients(g.settings.root)
        return render_template('form.html',form=form_values(old),task=old,error=error,
                               models=g.store.models(),clients=clients,client_notice=client_notice,
                               collaborators=g.store.active_collaborators(),
                               timezone=old['timezone'] if old else g.settings.timezone), (400 if error else 200)

    @app.get('/colaboradores')
    @protected
    def collaborators():
        page = integer(request.args.get('page',1),'Página',1,100000)
        contacts,total = g.store.list_collaborators(request.args.get('q',''),request.args.get('active',''),page)
        return render_template('collaborators.html',contacts=contacts,total=total,pager=pager(total,page))

    @app.route('/colaboradores/novo',methods=['GET','POST'])
    @app.route('/colaboradores/<int:collaborator_id>/editar',methods=['GET','POST'])
    @protected
    def collaborator_edit(collaborator_id=None):
        if not g.usuario.get('admin'):
            abort(403)
        old = g.store.get_collaborator(collaborator_id) if collaborator_id else None
        error = None
        if request.method=='POST':
            try:
                revision=integer(request.form.get('revision',0),'Versão',0,1000000000)
                g.store.save_collaborator(request.form,g.usuario,collaborator_id,revision)
                flash('Colaborador salvo. Os dados estarão disponíveis ao preencher novas tarefas.','success')
                return redirect(url_for('collaborators'),code=303)
            except ValueError as exc:
                error=str(exc)
        values=request.form.to_dict() if request.method=='POST' else old or {'name':'','email':'','active':1,'revision':0}
        return render_template('collaborator_form.html',form=values,contact=old,error=error),(400 if error else 200)

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
        labels = {'send':'Enviar agora','pause':'Pausar tarefa','resume':'Reativar tarefa','cancel':'Cancelar tarefa','complete':'Marcar tarefa como concluída'}
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

    @app.route('/feriados', methods=['GET','POST'])
    @protected
    def holidays():
        if request.method == 'POST':
            if not g.usuario.get('admin'):
                abort(403)
            g.store.save_holiday(request.form.get('day',''),request.form.get('name',''),g.usuario,
                                 remove=request.form.get('action')=='remove')
            flash('Calendário atualizado. Próximas ocorrências ajustadas; envios anteriores preservados.','success')
            return redirect(url_for('holidays'),code=303)
        year = integer(request.args.get('year', datetime.now(g.settings.zone).year),'Ano',1900,9998)
        defaults = [{'day':day,'name':name,'scope':'Nacional'} for day,name in national_holidays(year).items()]
        defaults += [{'day':day,'name':name,'scope':'Sorriso/MT'} for day,name in sorriso_holidays(year).items()]
        return render_template('holidays.html',year=year,defaults=sorted(defaults,key=lambda h:h['day']),holidays=g.store.holidays())

    @app.get('/modelos')
    @protected
    def models():
        return render_template('models.html',models=g.store.models(active_only=not g.usuario.get('admin')))

    @app.route('/modelos/novo', methods=['GET','POST'])
    @app.route('/modelos/<int:model_id>/editar', methods=['GET','POST'])
    @protected
    def model_edit(model_id=None):
        if not g.usuario.get('admin'):
            abort(403)
        old = g.store.get_model(model_id) if model_id else None
        error = None
        if request.method == 'POST':
            try:
                revision = integer(request.form.get('revision',0),'Versão',0,1000000000)
                g.store.save_model(request.form,g.usuario,model_id,revision)
                flash('Modelo salvo. Tarefas já cadastradas não foram alteradas.','success')
                return redirect(url_for('models'),code=303)
            except ValueError as exc:
                error = str(exc)
        if request.method == 'POST':
            form = form_values()
        else:
            rule = old['rule'] if old else {'kind':'none'}
            form = {**(old or {}), **rule, 'model_name':old['name'] if old else '',
                    'custom_mode':rule.get('mode','days'),'weekdays':[str(n) for n in rule.get('weekdays',[])]}
        return render_template('model_form.html',form=form,model=old,error=error),(400 if error else 200)

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
```

## apps/lembretes_tarefas/recurrence.py

```python
"""Recorrência calculada pela âncora original, sem materializar datas futuras."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KINDS = {'none': 'Não repetir', 'daily': 'Diariamente', 'weekly': 'Semanalmente',
         'monthly': 'Mensalmente', 'yearly': 'Anualmente', 'custom': 'Personalizado'}
WEEKDAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
BUSINESS_DAYS = {'keep': 'Manter', 'previous': 'Antecipar para dia útil', 'next': 'Postergar para dia útil'}


def business_date(day, policy='keep', holidays=()):
    if policy not in BUSINESS_DAYS:
        raise ValueError('Selecione uma regra válida para dias não úteis.')
    if policy == 'keep':
        return day
    step = timedelta(days=-1 if policy == 'previous' else 1)
    try:
        while day.weekday() >= 5 or day.isoformat() in holidays:
            day += step
    except OverflowError:
        raise ValueError('O ajuste de dia útil excede o calendário suportado.') from None
    return day


def integer(value, label, low, high):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label}: informe um número inteiro.') from None
    if not low <= result <= high:
        raise ValueError(f'{label}: informe um valor de {low} a {high}.')
    return result


def parse_rule(form):
    kind = form.get('kind', 'none')
    if kind not in KINDS:
        raise ValueError('Selecione uma repetição válida.')
    rule = {'kind': kind}
    if kind == 'custom':
        mode = form.get('custom_mode', 'days')
        if mode not in {'days', 'weekdays', 'monthday'}:
            raise ValueError('Repetição personalizada inválida.')
        rule['mode'] = mode
        if mode == 'days':
            rule['interval'] = integer(form.get('interval'), 'Intervalo de dias', 1, 3650)
        elif mode == 'weekdays':
            values = form.getlist('weekdays') if hasattr(form, 'getlist') else form.get('weekdays', [])
            rule['weekdays'] = sorted({integer(x, 'Dia da semana', 0, 6) for x in values})
            if not rule['weekdays']:
                raise ValueError('Selecione pelo menos um dia da semana.')
        else:
            rule['monthday'] = integer(form.get('monthday'), 'Dia do mês', 1, 31)
    if form.get('end_date'):
        try:
            rule['end_date'] = date.fromisoformat(form['end_date']).isoformat()
        except ValueError:
            raise ValueError('Data de término inválida.') from None
    if form.get('max_count'):
        rule['max_count'] = integer(form['max_count'], 'Máximo de ocorrências', 1, 100000)
    return rule


def occurrence_date(start, rule, index):
    """Dia 31 usa o último dia do mês; 29/02 usa 28/02 em ano comum."""
    kind = rule['kind']
    if index < 0 or index >= rule.get('max_count', 100000):
        return None
    try:
        if kind == 'none':
            result = start if index == 0 else None
        elif kind in {'daily', 'weekly'} or (kind == 'custom' and rule['mode'] == 'days'):
            interval = 1 if kind == 'daily' else 7 if kind == 'weekly' else rule['interval']
            result = start + timedelta(days=index * interval)
        elif kind == 'custom' and rule['mode'] == 'weekdays':
            days = rule['weekdays']
            monday = start - timedelta(days=start.weekday())
            first = [d for d in days if d >= start.weekday()]
            if index < len(first):
                result = monday + timedelta(days=first[index])
            else:
                week, offset = divmod(index - len(first), len(days))
                result = monday + timedelta(days=7 * (week + 1) + days[offset])
        elif kind == 'yearly':
            year = start.year + index
            result = date(year, start.month, min(start.day, monthrange(year, start.month)[1]))
        else:
            day = rule.get('monthday', start.day)
            first_day = min(day, monthrange(start.year, start.month)[1])
            offset = int(kind == 'custom' and first_day < start.day)
            year, month0 = divmod(start.year * 12 + start.month - 1 + index + offset, 12)
            result = date(year, month0 + 1, min(day, monthrange(year, month0 + 1)[1]))
    except (ValueError, OverflowError):
        return None
    if result and rule.get('end_date') and result > date.fromisoformat(rule['end_date']):
        return None
    return result


def local_timestamp(day, clock, zone):
    naive = datetime.combine(day, time.fromisoformat(clock))
    # Horário inexistente no início do DST avança até o primeiro minuto válido.
    # Horário ambíguo usa a primeira ocorrência (fold=0).
    for minute in range(181):
        candidate = (naive + timedelta(minutes=minute)).replace(tzinfo=ZoneInfo(zone), fold=0)
        if candidate.astimezone(timezone.utc).astimezone(candidate.tzinfo).replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return int(candidate.timestamp())
    raise ValueError('Não foi possível resolver o horário no fuso configurado.')


def slot(start_date, clock, zone, rule, index, policy='keep', holidays=()):
    day = occurrence_date(date.fromisoformat(start_date), rule, index)
    return local_timestamp(business_date(day, policy, holidays), clock, zone) if day else None


def next_slot(start_date, clock, zone, rule, after, minimum_index=0, policy='keep', holidays=()):
    """Primeira ocorrência >= after. Busca binária, inclusive após longas paradas."""
    low, high = minimum_index, rule.get('max_count', 100000)
    if rule['kind'] == 'none':
        high = min(high, 1)
    while low < high:
        mid = (low + high) // 2
        value = slot(start_date, clock, zone, rule, mid, policy, holidays)
        if value is None or value >= after:
            high = mid
        else:
            low = mid + 1
    value = slot(start_date, clock, zone, rule, low, policy, holidays)
    return (value, low) if value is not None and value >= after else (None, low)


def describe(rule):
    text = KINDS[rule['kind']]
    if rule['kind'] == 'custom':
        if rule['mode'] == 'days':
            text = f"A cada {rule['interval']} dia(s)"
        elif rule['mode'] == 'weekdays':
            text = ', '.join(WEEKDAYS[d] for d in rule['weekdays'])
        else:
            text = f"Dia {rule['monthday']} de cada mês"
    return text
```

## apps/lembretes_tarefas/validation.py

```python
import json
import re
import unicodedata
from datetime import date, datetime, time
from urllib.parse import quote, urlsplit
from .recurrence import BUSINESS_DAYS, parse_rule, next_slot, local_timestamp, integer

PRIORITIES = {'NORMAL': 'Normal', 'ALTA': 'Alta', 'CRITICA': 'Crítica'}


def short_text(value, label, maximum=160):
    value = value.strip()
    if len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f'{label}: use até {maximum} caracteres, sem quebras de linha.')
    return value


def content_input(form):
    title = short_text(form.get('title', ''), 'Título', 200)
    if not title:
        raise ValueError('Informe o título da tarefa com até 200 caracteres.')
    description = form.get('description', '').strip()
    if len(description) > 10000:
        raise ValueError('A descrição deve ter até 10.000 caracteres.')
    labels, values = form.getlist('link_label'), form.getlist('link_value')
    if len(labels) != len(values) or len(labels) > 20:
        raise ValueError('Informe até 20 links, cada um com descrição e endereço.')
    links = [link for label, value in zip(labels, values) if (link := related_link(label, value))]
    return {'title': title, 'description': description, 'links': links, 'rule': parse_rule(form)}


def model_input(form):
    name = short_text(form.get('model_name', ''), 'Nome do modelo', 120)
    if not name:
        raise ValueError('Informe o nome do modelo.')
    if form.get('active', '1') not in {'0', '1'}:
        raise ValueError('Situação do modelo inválida.')
    return {**content_input(form), 'name': name, 'active': int(form.get('active', '1'))}


def search_key(value):
    text = unicodedata.normalize('NFKD', ' '.join(value.split()).casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def collaborator_input(form):
    name = ' '.join(form.get('name', '').split())
    if not name or len(name) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in form.get('name', '')):
        raise ValueError('Informe o nome do colaborador com até 120 caracteres.')
    address = email(form.get('email', ''))
    active = form.get('active', '1')
    if active not in {'0', '1'}:
        raise ValueError('Selecione uma situação válida para o colaborador.')
    return {'name': name, 'name_key': search_key(name), 'email': address,
            'email_key': address.casefold(), 'active': int(active)}


def email(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise ValueError('Informe um único endereço de e-mail válido, sem nome ou separadores.')
    labels = value.rsplit('@', 1)[1].split('.')
    if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in labels):
        raise ValueError('Domínio de e-mail inválido.')
    return value


def related_link(label, value):
    label, value = label.strip(), value.strip()
    if not label and not value:
        return None
    if not label or len(label) > 150 or not value or len(value) > 2048:
        raise ValueError('Cada link precisa de descrição (até 150 caracteres) e endereço (até 2048).')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('O endereço de um link contém caracteres inválidos.')
    if value.startswith('\\\\'):
        parts = [p for p in value[2:].split('\\') if p]
        if len(parts) < 2 or any(c in value for c in ['<', '>', '"', '|', '*', '?']):
            raise ValueError('Caminho UNC inválido. Exemplo: \\\\servidor\\pasta\\arquivo.xlsx')
        href = 'file://' + '/'.join(quote(p, safe='') for p in parts)
        kind = 'path'
    elif re.match(r'^[A-Za-z]:[\\/]', value):
        href = 'file:///' + quote(value.replace('\\', '/'), safe='/:')
        kind = 'path'
    else:
        try:
            parsed = urlsplit(value)
            parsed.port
            if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value) or '\\' in value:
                raise ValueError()
        except ValueError:
            raise ValueError('Use uma URL http/https ou um caminho Windows/UNC válido.') from None
        href, kind = value, 'web'
    return {'label': label, 'value': value, 'href': href, 'kind': kind}


def task_input(form, zone, now, old=None, holidays=()):
    name, title = form.get('name', '').strip(), form.get('title', '').strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Informe o nome do colaborador com até 120 caracteres.')
    if not title or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise ValueError('Informe o título da tarefa com até 200 caracteres.')
    description = form.get('description', '').strip()
    if len(description) > 10000:
        raise ValueError('A descrição deve ter até 10.000 caracteres.')
    try:
        start = date.fromisoformat(form.get('start_date', '')).isoformat()
        clock = time.fromisoformat(form.get('clock', ''))
        if clock.tzinfo or clock.second or clock.microsecond:
            raise ValueError()
        clock = clock.strftime('%H:%M')
    except ValueError:
        raise ValueError('Informe data e horário válidos, com hora e minuto.') from None
    rule = parse_rule(form)
    if rule.get('end_date') and rule['end_date'] < start:
        raise ValueError('O término deve ser igual ou posterior à primeira data.')
    labels, values = form.getlist('link_label'), form.getlist('link_value')
    if len(labels) != len(values) or len(labels) > 20:
        raise ValueError('Informe até 20 links, cada um com descrição e endereço.')
    links = [link for label, value in zip(labels, values) if (link := related_link(label, value))]
    policy = form.get('business_day_policy', 'keep')
    if policy not in BUSINESS_DAYS:
        raise ValueError('Selecione uma regra válida para dias não úteis.')
    priority = form.get('priority', 'NORMAL')
    if priority not in PRIORITIES:
        raise ValueError('Selecione uma prioridade válida.')
    deadline = None
    if form.get('deadline'):
        try:
            moment = datetime.fromisoformat(form['deadline'])
            if moment.tzinfo or moment.second or moment.microsecond:
                raise ValueError()
            deadline = local_timestamp(moment.date(), moment.strftime('%H:%M'), zone)
        except ValueError:
            raise ValueError('Informe o prazo final com data, hora e minuto válidos.') from None
        if deadline <= now and (not old or deadline != old.get('deadline_ts')):
            raise ValueError('O novo prazo final deve estar no futuro.')
    if priority == 'CRITICA' and deadline is None:
        raise ValueError('Tarefas críticas exigem prazo final. O alerta será enviado ao e-mail do dono da tarefa.')
    unchanged = old and (old['start_date'], old['clock'], old['rule'], old['timezone'], old.get('business_day_policy', 'keep')) == (start, clock, rule, zone, policy)
    first, idx = next_slot(start, clock, zone, rule, 0, policy=policy, holidays=holidays)
    if not unchanged:
        if local_timestamp(date.fromisoformat(start), clock, zone) < now:
            raise ValueError('A primeira data e horário devem estar no futuro. Ajuste também o horário do lembrete.')
        if first is None:
            raise ValueError('A regra não tem ocorrências dentro do período informado.')
        if first < now:
            raise ValueError('A primeira ocorrência ajustada para dia útil está no passado. Ajuste a data inicial ou a regra.')
    collaborator_id = integer(form['collaborator_id'], 'Colaborador', 1, 2147483647) if form.get('collaborator_id') else None
    return {'name': name, 'email': email(form.get('email', '')), 'title': title,
            'collaborator_id': collaborator_id,
            'description': description, 'links': links, 'start_date': start, 'clock': clock,
            'business_day_policy': policy, 'priority': priority, 'deadline_ts': deadline,
            'department': short_text(form.get('department', ''), 'Departamento'),
            'client': short_text(form.get('client', ''), 'Cliente', 240),
            'rule': rule, 'timezone': zone, 'next_ts': old['next_ts'] if unchanged else first,
            'next_index': old['next_index'] if unchanged else idx, 'schedule_changed': not unchanged}
```

## apps/lembretes_tarefas/store.py

```python
"""Fila durável. A reserva é confirmada no SQLite antes de qualquer SMTP."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
import time
import uuid
from .recurrence import next_slot
from .validation import collaborator_input, model_input, search_key, short_text
from .calendar import BusinessCalendar
from .migrations import backup_before_upgrade, upgrade


class Conflict(ValueError):
    pass


def unpack(row):
    if row is None:
        return None
    result = dict(row)
    for field in ('rule', 'links', 'payload'):
        if field in result:
            result[field] = json.loads(result[field])
    return result


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup_before_upgrade(self.path)
        with self.db() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > 3:
                raise RuntimeError('Banco criado por uma versão mais recente. Não faça downgrade.')
            con.execute('PRAGMA journal_mode=WAL')
            # Migrar também bases da v1 sem alterar tarefas, envios ou histórico.
            # CREATE TABLE/INDEX e user_version são confirmados juntos.
            con.execute('BEGIN IMMEDIATE')
            if con.execute('PRAGMA user_version').fetchone()[0] > 3:
                raise RuntimeError('Banco criado por uma versão mais recente. Não faça downgrade.')
            statement = ''
            for line in Path(__file__).with_name('schema.sql').read_text(encoding='utf-8').splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    con.execute(statement)
                    statement = ''
            if statement.strip():
                raise RuntimeError('Definição de banco incompleta.')
            upgrade(con)

    @contextmanager
    def db(self, write=False):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA synchronous=FULL')
        try:
            if write:
                con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _owned(con, task_id, actor):
        task = unpack(con.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone())
        if not task or (not actor.get('admin') and task['created_by'] != actor['id']):
            raise LookupError('Tarefa não encontrada.')
        return task

    def get(self, task_id, actor):
        with self.db() as con:
            return self._owned(con, task_id, actor)

    @staticmethod
    def _audit(con, task_id, actor, action, detail='', now=None):
        con.execute('INSERT INTO audit(task_id,at,actor_id,actor_name,action,detail) VALUES(?,?,?,?,?,?)',
                    (task_id, int(time.time()) if now is None else now, actor.get('id'), actor.get('name', 'Agendador'), action, detail))

    @staticmethod
    def _mutable(con, task, revision):
        if task['revision'] != revision:
            raise Conflict('Esta tarefa foi alterada. Atualize a página antes de continuar.')
        if con.execute("SELECT 1 FROM deliveries WHERE task_id=? AND state IN ('SENDING','UNKNOWN')", (task['id'],)).fetchone():
            raise Conflict('Há um envio em andamento ou sem confirmação. Consulte o histórico antes de alterar a tarefa.')

    def save(self, data, actor, task_id=None, revision=None, now=None):
        now = int(time.time()) if now is None else now
        fields = ['name','email','title','description','links','start_date','clock','timezone','rule','next_ts','next_index',
                  'business_day_policy','priority','department','client','deadline_ts']
        with self.db(True) as con:
            # Seleção do cadastro é resolvida novamente dentro da transação.
            # Não confiar no e-mail enviado por JavaScript para um ID selecionado.
            if data.get('collaborator_id'):
                contact = con.execute('SELECT * FROM collaborators WHERE id=? AND active=1', (data['collaborator_id'],)).fetchone()
                if not contact:
                    raise ValueError('O colaborador selecionado foi inativado ou não existe. Selecione outro cadastro.')
                data = {**data, 'name': contact['name'], 'email': contact['email']}
            if data['schedule_changed'] and data['business_day_policy'] != 'keep':
                value, idx = next_slot(data['start_date'], data['clock'], data['timezone'], data['rule'], 0,
                                      policy=data['business_day_policy'], holidays=self._calendar(con))
                if value is None or value < now:
                    raise ValueError('A ocorrência ajustada está no passado ou fora do período. Confira o calendário.')
                data = {**data, 'next_ts': value, 'next_index': idx}
            values = [encoded(data[key]) if key in {'links','rule'} else data[key] for key in fields]
            if task_id is None:
                task_id = con.execute(f"INSERT INTO tasks({','.join(fields)},created_at,updated_at,created_by,created_by_name,status) VALUES({','.join('?' for _ in fields)},?,?,?,?,?)",
                    (*values, now, now, actor['id'], actor['name'], 'ATIVO')).lastrowid
                action = 'CRIADA'
            else:
                old = self._owned(con, task_id, actor)
                self._mutable(con, old, revision)
                if old['status'] == 'CANCELADO' or old['completed_at'] is not None:
                    raise ValueError('Tarefa cancelada ou concluída manualmente não pode ser editada. Cadastre uma nova tarefa.')
                con.execute("UPDATE deliveries SET state='CANCELED',finished_at=? WHERE task_id=? AND purpose='REMINDER' AND state IN ('WAITING','ERROR')", (now, task_id))
                if any(old[key] != data[key] for key in ('priority','deadline_ts','email')):
                    con.execute("UPDATE deliveries SET state='CANCELED',finished_at=? WHERE task_id=? AND purpose='ESCALATION' AND state IN ('WAITING','ERROR')", (now, task_id))
                status = old['status']
                if data['schedule_changed'] and status == 'CONCLUIDO':
                    status = 'ATIVO'
                con.execute(f"UPDATE tasks SET {','.join(key+'=?' for key in fields)},updated_at=?,revision=revision+1,last_error=NULL,status=? WHERE id=?",
                            (*values, now, status, task_id))
                action = 'EDITADA'
            self._audit(con, task_id, actor, action, now=now)
        return task_id

    def get_collaborator(self, collaborator_id, active_only=False):
        with self.db() as con:
            row = con.execute('SELECT * FROM collaborators WHERE id=?'+(' AND active=1' if active_only else ''), (collaborator_id,)).fetchone()
            if not row:
                raise ValueError('Colaborador não encontrado ou indisponível.')
            return dict(row)

    def active_collaborators(self):
        with self.db() as con:
            return [dict(row) for row in con.execute('SELECT id,name,email FROM collaborators WHERE active=1 ORDER BY name_key,email_key,id')]

    def list_collaborators(self, query='', active='', page=1):
        where, params = [], []
        if query:
            where.append('(name_key LIKE ? OR email_key LIKE ?)')
            params += ['%'+search_key(query[:200])+'%', '%'+query[:200].casefold()+'%']
        if active in {'0','1'}:
            where.append('active=?')
            params.append(int(active))
        clause = ' WHERE '+' AND '.join(where) if where else ''
        with self.db() as con:
            total = con.execute('SELECT COUNT(*) FROM collaborators'+clause,params).fetchone()[0]
            rows = con.execute('SELECT * FROM collaborators'+clause+' ORDER BY active DESC,name_key,email_key,id LIMIT 50 OFFSET ?',(*params,(page-1)*50)).fetchall()
            return [dict(row) for row in rows],total

    def save_collaborator(self, form, actor, collaborator_id=None, revision=None, now=None):
        if not actor.get('admin'):
            raise PermissionError('Somente administradores podem alterar o cadastro de colaboradores.')
        data = collaborator_input(form)
        now = int(time.time()) if now is None else now
        values = [data[k] for k in ['name','name_key','email','email_key','active']]
        with self.db(True) as con:
            try:
                if collaborator_id is None:
                    collaborator_id = con.execute('INSERT INTO collaborators(name,name_key,email,email_key,active,created_at,updated_at,created_by,updated_by) VALUES(?,?,?,?,?,?,?,?,?)',
                        (*values,now,now,actor['id'],actor['id'])).lastrowid
                    action='COLABORADOR_CADASTRADO'
                else:
                    old = con.execute('SELECT * FROM collaborators WHERE id=?',(collaborator_id,)).fetchone()
                    if not old or old['revision']!=revision:
                        raise Conflict('O cadastro foi alterado por outra pessoa. Atualize a página e confira os dados.')
                    con.execute('UPDATE collaborators SET name=?,name_key=?,email=?,email_key=?,active=?,updated_at=?,updated_by=?,revision=revision+1 WHERE id=?',
                        (*values,now,actor['id'],collaborator_id))
                    action='COLABORADOR_EDITADO'
            except sqlite3.IntegrityError:
                raise ValueError('Este e-mail já possui cadastro, inclusive entre os inativos. Edite ou reative o cadastro existente.') from None
            self._audit(con,None,actor,action,f'Cadastro #{collaborator_id}: {data["name"]}; ativo={data["active"]}. Tarefas anteriores preservadas.',now)
        return collaborator_id

    def change_status(self, task_id, action, actor, revision, now):
        with self.db(True) as con:
            task = self._owned(con, task_id, actor)
            self._mutable(con, task, revision)
            status, next_ts, idx = task['status'], task['next_ts'], task['next_index']
            skipped = 0
            completed = task['completed_at']
            if completed is not None:
                raise ValueError('Esta tarefa já foi concluída manualmente.')
            if action == 'complete' and status != 'CANCELADO':
                status, next_ts, completed = 'CONCLUIDO', None, now
            elif action == 'pause' and status == 'ATIVO':
                status = 'PAUSADO'
            elif action == 'cancel' and status != 'CANCELADO':
                status, next_ts = 'CANCELADO', None
            elif action == 'resume' and status == 'PAUSADO':
                next_ts, idx = next_slot(task['start_date'], task['clock'], task['timezone'], task['rule'], now, idx,
                                         task['business_day_policy'], self._calendar(con))
                if next_ts is None:
                    raise ValueError('Não há próxima data. Edite a programação para definir uma data futura.')
                skipped = max(0, idx - task['next_index'])
                status = 'ATIVO'
            else:
                raise ValueError('Ação incompatível com o status atual.')
            con.execute("UPDATE deliveries SET state='CANCELED',finished_at=? WHERE task_id=? AND state IN ('WAITING','ERROR') AND (purpose='REMINDER' OR ? IN ('cancel','complete'))", (now, task_id, action))
            con.execute('UPDATE tasks SET status=?,next_ts=?,next_index=?,revision=revision+1,updated_at=?,last_error=NULL,skipped_count=skipped_count+?,completed_at=? WHERE id=?',
                        (status, next_ts, idx, now, skipped, completed, task_id))
            self._audit(con, task_id, actor, action.upper(), f'{skipped} ocorrência(s) transcorrida(s) durante a pausa.' if skipped else '', now=now)

    @staticmethod
    def _enqueue(con, key, task, kind, actor, now, payload=None, purpose='REMINDER'):
        payload = payload or {k: task[k] for k in ('name','email','title','description','links','timezone')}
        scheduled = task['next_ts'] if kind == 'SCHEDULED' else now
        payload['scheduled_ts'] = scheduled
        message_id = f'<icc-lembrete-{uuid.uuid4().hex}@icccontabilidade.com.br>'
        con.execute("""INSERT OR IGNORE INTO deliveries(request_key,task_id,kind,generation,ordinal,scheduled_ts,payload,
            actor_id,actor_name,state,available_at,created_at,message_id,purpose) VALUES(?,?,?,?,?,?,?,?,?,'WAITING',?,?,?,?)""",
            (key, task['id'] if task else None, kind, task['revision'] if task else None,
             task['next_index'] if task and kind == 'SCHEDULED' else None, scheduled, encoded(payload),
             actor['id'], actor['name'], now, now, message_id, purpose))
        return con.execute('SELECT id FROM deliveries WHERE request_key=?', (key,)).fetchone()[0]

    def queue_manual(self, task_id, actor, key, now, revision):
        with self.db(True) as con:
            task = self._owned(con, task_id, actor)
            previous = con.execute('SELECT id FROM deliveries WHERE request_key=? AND actor_id=?', (key, actor['id'])).fetchone()
            if previous:
                return previous[0]
            self._mutable(con, task, revision)
            if task['status'] == 'CANCELADO' or task['completed_at'] is not None:
                raise ValueError('Tarefa cancelada ou concluída manualmente não aceita novos envios.')
            if con.execute("SELECT 1 FROM deliveries WHERE task_id=? AND kind='MANUAL' AND purpose='REMINDER' AND state='WAITING'", (task_id,)).fetchone():
                raise Conflict('Já existe um envio manual na fila para esta tarefa.')
            result = self._enqueue(con, key, task, 'MANUAL', actor, now)
            self._audit(con, task_id, actor, 'ENVIO_MANUAL_SOLICITADO', now=now)
            return result

    def queue_test(self, recipient, actor, key, now, zone):
        if not actor.get('admin'):
            raise PermissionError('Somente administradores podem testar SMTP.')
        with self.db(True) as con:
            if con.execute("SELECT COUNT(*) FROM deliveries WHERE actor_id=? AND kind='TEST' AND created_at>?", (actor['id'], now-3600)).fetchone()[0] >= 10:
                raise ValueError('Limite de 10 testes por hora. Aguarde antes de testar novamente.')
            payload = {'name': 'Administrador', 'email': recipient, 'title': 'Teste de envio de e-mail',
                       'description': 'O envio SMTP do aplicativo Lembretes de Tarefas foi executado pelo servidor.', 'links': [], 'timezone': zone}
            return self._enqueue(con, key, None, 'TEST', actor, now, payload)

    def queue_due(self, now):
        with self.db(True) as con:
            rows = con.execute("""SELECT * FROM tasks t WHERE status='ATIVO' AND completed_at IS NULL AND next_ts<=?
                AND NOT EXISTS(SELECT 1 FROM deliveries d WHERE d.task_id=t.id AND d.kind='SCHEDULED'
                  AND d.generation=t.revision AND d.scheduled_ts=t.next_ts)
                ORDER BY next_ts LIMIT 200""", (now,)).fetchall()
            for row in rows:
                task = unpack(row)
                key = f"scheduled:{task['id']}:{task['revision']}:{task['next_ts']}"
                self._enqueue(con, key, task, 'SCHEDULED', {'id':task['created_by'], 'name':'Agendador'}, now)
            return len(rows)

    def queue_escalations(self, now):
        """Um alerta por tarefa/prazo/destinatário, inclusive após indisponibilidade."""
        with self.db(True) as con:
            rows = con.execute("""SELECT * FROM tasks WHERE priority='CRITICA' AND completed_at IS NULL
                AND status!='CANCELADO' AND deadline_ts IS NOT NULL AND deadline_ts-86400<=?
                ORDER BY deadline_ts,id""", (now,)).fetchall()
            queued = 0
            for row in rows:
                task = unpack(row)
                key = f"escalation:{task['id']}:{task['deadline_ts']}:{task['email'].casefold()}"
                previous = con.execute('SELECT id,state FROM deliveries WHERE request_key=?', (key,)).fetchone()
                if previous and previous['state'] != 'CANCELED':
                    continue
                payload = {k: task[k] for k in ('name','email','title','description','links','timezone','department','client','deadline_ts')}
                payload['scheduled_ts'] = now
                if previous:
                    con.execute("""UPDATE deliveries SET state='WAITING',available_at=?,created_at=?,finished_at=NULL,
                        started_at=NULL,error=NULL,attempts=0,payload=?,generation=? WHERE id=?""",
                        (now, now, encoded(payload), task['revision'], previous['id']))
                else:
                    self._enqueue(con, key, task, 'MANUAL', {'id':task['created_by'], 'name':'Agendador'}, now,
                                  payload, purpose='ESCALATION')
                self._audit(con, task['id'], {'name':'Agendador'}, 'ALERTA_CRITICO_SOLICITADO',
                            'Alerta ao dono da tarefa, 24 horas antes do prazo ou na retomada.', now)
                queued += 1
            return queued

    @staticmethod
    def _valid_escalation(task, delivery):
        payload = delivery['payload']
        return (task and task['priority'] == 'CRITICA' and task['completed_at'] is None
                and task['status'] != 'CANCELADO' and task['deadline_ts'] == payload.get('deadline_ts')
                and task['email'].casefold() == payload['email'].casefold())

    def claim(self, now):
        with self.db(True) as con:
            row = con.execute("SELECT * FROM deliveries WHERE state='WAITING' AND available_at<=? ORDER BY (purpose='ESCALATION') DESC,available_at,id LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            delivery = unpack(row)
            if delivery['task_id']:
                task = con.execute('SELECT * FROM tasks WHERE id=?', (delivery['task_id'],)).fetchone()
                valid = task and task['completed_at'] is None and task['status'] != 'CANCELADO' and task['revision'] == delivery['generation']
                if delivery['purpose'] == 'ESCALATION':
                    valid = self._valid_escalation(task, delivery)
                if delivery['kind'] == 'SCHEDULED':
                    valid = valid and task['status'] == 'ATIVO' and task['next_ts'] == delivery['scheduled_ts']
                if not valid:
                    con.execute("UPDATE deliveries SET state='CANCELED',finished_at=? WHERE id=?", (now, delivery['id']))
                    return None
            con.execute("UPDATE deliveries SET state='SENDING',started_at=?,attempts=attempts+1 WHERE id=? AND state='WAITING'", (now, delivery['id']))
            delivery.update(state='SENDING', started_at=now, attempts=delivery['attempts']+1)
            return delivery

    @staticmethod
    def _refresh_error(con, task_id):
        row = con.execute("SELECT error FROM deliveries WHERE task_id=? AND state IN ('WAITING','SENDING','ERROR','UNKNOWN') AND error IS NOT NULL ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        con.execute('UPDATE tasks SET last_error=? WHERE id=?', (row['error'] if row else None, task_id))

    @staticmethod
    def _advance(con, delivery, now, sent):
        if not delivery['task_id']:
            return
        task = unpack(con.execute('SELECT * FROM tasks WHERE id=?', (delivery['task_id'],)).fetchone())
        if delivery.get('purpose') == 'ESCALATION':
            Store._refresh_error(con, task['id'])
            return
        if sent:
            con.execute('UPDATE tasks SET send_count=send_count+1,last_sent=?,last_error=NULL WHERE id=?', (now, task['id']))
        if delivery['kind'] != 'SCHEDULED' or task['revision'] != delivery['generation'] or task['next_ts'] != delivery['scheduled_ts']:
            Store._refresh_error(con, task['id'])
            return
        value, idx = next_slot(task['start_date'], task['clock'], task['timezone'], task['rule'],
                               max(now + 1, delivery['scheduled_ts'] + 1), delivery['ordinal'] + 1,
                               task['business_day_policy'], Store._calendar(con))
        skipped = max(0, idx - delivery['ordinal'] - 1)
        if not sent:
            skipped += 1
        con.execute('UPDATE tasks SET next_ts=?,next_index=?,status=?,scheduled_count=scheduled_count+?,skipped_count=skipped_count+?,last_error=NULL,updated_at=? WHERE id=?',
                    (value, idx, 'ATIVO' if value is not None else 'CONCLUIDO', int(sent), skipped, now, task['id']))
        if skipped:
            Store._audit(con, task['id'], {'name':'Agendador'}, 'OCORRENCIAS_PULADAS',
                         f'{skipped} ocorrência(s) sem envio; próxima data calculada após a retomada ou encerramento manual.', now)
        Store._refresh_error(con, task['id'])

    def success(self, delivery, now, detail='Aceito pelo servidor SMTP. A entrega na caixa de entrada depende do provedor.'):
        with self.db(True) as con:
            changed = con.execute("UPDATE deliveries SET state='SENT',finished_at=?,error=NULL WHERE id=? AND state='SENDING'", (now, delivery['id'])).rowcount
            if changed != 1:
                raise Conflict('Reserva do envio deixou de estar ativa.')
            con.execute("INSERT INTO history(delivery_id,at,result,detail) VALUES(?,?,'ENVIADO',?)", (delivery['id'], now, detail))
            self._advance(con, delivery, now, True)

    def failure(self, delivery, now, error, transient=False, uncertain=False):
        retry = transient and not uncertain and delivery['attempts'] < 3
        state = 'UNKNOWN' if uncertain else 'WAITING' if retry else 'ERROR'
        delay = (60, 300, 900)[min(delivery['attempts']-1, 2)]
        with self.db(True) as con:
            con.execute('UPDATE deliveries SET state=?,available_at=?,finished_at=?,error=? WHERE id=? AND state=\'SENDING\'',
                        (state, now+delay, None if retry else now, error, delivery['id']))
            con.execute("INSERT INTO history(delivery_id,at,result,detail) VALUES(?,?,'ERRO',?)", (delivery['id'], now, error))
            if delivery['task_id']:
                con.execute('UPDATE tasks SET last_error=? WHERE id=?', (error, delivery['task_id']))

    def recover_interrupted(self, now):
        """Só chamar após obter o lock exclusivo do processo, nunca por timeout."""
        with self.db(True) as con:
            rows = con.execute("SELECT * FROM deliveries WHERE state='SENDING'").fetchall()
            error = 'Envio interrompido: resultado SMTP não confirmado. Confira com o destinatário antes de decidir.'
            for row in rows:
                con.execute("UPDATE deliveries SET state='UNKNOWN',error=?,finished_at=? WHERE id=?", (error, now, row['id']))
                con.execute("INSERT INTO history(delivery_id,at,result,detail) VALUES(?,?,'ERRO',?)", (row['id'], now, error))
                if row['task_id']:
                    con.execute('UPDATE tasks SET last_error=? WHERE id=?', (error, row['task_id']))
            return len(rows)

    def resolve(self, delivery_id, action, actor, now):
        with self.db(True) as con:
            delivery = unpack(con.execute('SELECT * FROM deliveries WHERE id=?', (delivery_id,)).fetchone())
            if not delivery:
                raise LookupError('Envio não encontrado.')
            if delivery['task_id']:
                self._owned(con, delivery['task_id'], actor)
            elif not actor.get('admin'):
                raise LookupError('Envio não encontrado.')
            if action == 'retry' and delivery['state'] == 'ERROR':
                if delivery['task_id']:
                    task = self._owned(con, delivery['task_id'], actor)
                    valid = self._valid_escalation(task, delivery) if delivery['purpose'] == 'ESCALATION' else (
                        task['completed_at'] is None and task['revision'] == delivery['generation'] and task['status'] != 'CANCELADO'
                        and (delivery['kind'] != 'SCHEDULED' or task['status'] == 'ATIVO'))
                    if not valid:
                        raise ValueError('A programação mudou. Esta ocorrência não pode ser reenviada.')
                con.execute("UPDATE deliveries SET state='WAITING',available_at=?,attempts=0,finished_at=NULL WHERE id=?", (now, delivery_id))
            elif action in {'confirm_sent','discard'} and delivery['state'] in {'UNKNOWN','ERROR'}:
                sent = action == 'confirm_sent'
                con.execute('UPDATE deliveries SET state=?,finished_at=? WHERE id=?', ('SENT' if sent else 'DISCARDED', now, delivery_id))
                if sent:
                    con.execute("INSERT INTO history(delivery_id,at,result,detail) VALUES(?,?,'ENVIADO',?)",
                                (delivery_id, now, f"Envio confirmado manualmente por {actor['name']}; não houve nova transmissão SMTP."))
                self._advance(con, delivery, now, sent)
            else:
                raise ValueError('A ocorrência já foi tratada ou não permite essa ação.')
            self._audit(con, delivery['task_id'], actor, action.upper(), f'Envio {delivery_id}', now)

    def heartbeat(self, now, pid, ready, error=''):
        with self.db(True) as con:
            con.execute('INSERT INTO worker_state VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,pid=excluded.pid,smtp_ready=excluded.smtp_ready,last_error=excluded.last_error',
                        (now, pid, int(ready), error))

    def worker_info(self):
        with self.db() as con:
            return unpack(con.execute('SELECT * FROM worker_state WHERE id=1').fetchone())

    def list_tasks(self, actor, filters=None, page=1):
        filters = filters or {}
        conditions, params = [], []
        if not actor.get('admin'):
            conditions.append('created_by=?')
            params.append(actor['id'])
        for field in ['name','email','title','department','client']:
            if filters.get(field):
                conditions.append(f'{field} LIKE ?')
                params.append('%'+filters[field][:200]+'%')
        if filters.get('q'):
            conditions.append('(name LIKE ? OR title LIKE ?)')
            params.extend(['%'+filters['q'][:200]+'%']*2)
        if filters.get('status'):
            conditions.append('status=?')
            params.append(filters['status'])
        if filters.get('priority'):
            conditions.append('priority=?')
            params.append(filters['priority'])
        if filters.get('completion') in {'open','done'}:
            conditions.append('completed_at IS '+('NOT NULL' if filters['completion']=='done' else 'NULL'))
        if filters.get('kind'):
            # JSON extraído em Python não é necessário: SQLite embarcado inclui JSON1.
            conditions.append("json_extract(rule,'$.kind')=?")
            params.append(filters['kind'])
        for name, operation in [('from_ts','>='),('to_ts','<')]:
            if filters.get(name) is not None:
                conditions.append('next_ts'+operation+'?')
                params.append(filters[name])
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        with self.db() as con:
            total = con.execute('SELECT COUNT(*) FROM tasks'+where, params).fetchone()[0]
            rows = con.execute('SELECT * FROM tasks'+where+' ORDER BY next_ts IS NULL,next_ts,id LIMIT 50 OFFSET ?', (*params, (page-1)*50)).fetchall()
            return [unpack(row) for row in rows], total

    def dashboard(self, actor, now, zone):
        today = datetime.fromtimestamp(now, zone).date()
        start = int(datetime.combine(today, datetime.min.time(), zone).timestamp())
        end = int(datetime.combine(today+timedelta(days=1), datetime.min.time(), zone).timestamp())
        own = '' if actor.get('admin') else ' AND created_by=?'
        params = () if actor.get('admin') else (actor['id'],)
        with self.db() as con:
            result = {}
            for key, condition, arguments in [
                ('active', "status='ATIVO'", ()), ('today', "status='ATIVO' AND next_ts>=? AND next_ts<?", (start,end)),
                ('late', "status='ATIVO' AND next_ts<?", (now,)), ('errors', 'last_error IS NOT NULL', ())]:
                result[key] = con.execute('SELECT COUNT(*) FROM tasks WHERE '+condition+own, arguments+params).fetchone()[0]
            result['sent'] = con.execute("SELECT COUNT(*) FROM deliveries d JOIN tasks t ON t.id=d.task_id WHERE d.state='SENT' AND d.purpose='REMINDER'"+('' if actor.get('admin') else ' AND t.created_by=?'), params).fetchone()[0]
            return result

    def history(self, actor, task_id=None, page=1, result=None):
        conditions, params = [], []
        if not actor.get('admin'):
            conditions.append('(t.created_by=? OR (d.task_id IS NULL AND d.actor_id=?))')
            params.extend([actor['id'],actor['id']])
        if task_id is not None:
            conditions.append('d.task_id=?')
            params.append(task_id)
        if result in {'ENVIADO','ERRO'}:
            conditions.append('h.result=?')
            params.append(result)
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        base = ' FROM history h JOIN deliveries d ON d.id=h.delivery_id LEFT JOIN tasks t ON t.id=d.task_id'
        with self.db() as con:
            total = con.execute('SELECT COUNT(*)'+base+where, params).fetchone()[0]
            rows = con.execute('SELECT h.*,d.task_id,d.kind,d.purpose,d.payload,d.state,d.actor_name'+base+where+' ORDER BY h.id DESC LIMIT 50 OFFSET ?', (*params,(page-1)*50)).fetchall()
            return [unpack(row) for row in rows], total

    def pending(self, actor, task_id=None):
        conditions = ["d.state IN ('WAITING','SENDING','ERROR','UNKNOWN')"]
        params = []
        if not actor.get('admin'):
            conditions.append('(t.created_by=? OR (d.task_id IS NULL AND d.actor_id=?))')
            params.extend([actor['id'], actor['id']])
        if task_id is not None:
            conditions.append('d.task_id=?')
            params.append(task_id)
        with self.db() as con:
            rows = con.execute('SELECT d.* FROM deliveries d LEFT JOIN tasks t ON t.id=d.task_id WHERE '+' AND '.join(conditions)+' ORDER BY d.id DESC LIMIT 100', params).fetchall()
            return [unpack(row) for row in rows]

    def audits(self, task_id, actor):
        with self.db() as con:
            self._owned(con, task_id, actor)
            return [dict(r) for r in con.execute('SELECT * FROM audit WHERE task_id=? ORDER BY id DESC LIMIT 100', (task_id,))]

    @staticmethod
    def _calendar(con):
        return BusinessCalendar(row[0] for row in con.execute('SELECT day FROM holidays'))

    def calendar(self):
        with self.db() as con:
            return self._calendar(con)

    def holidays(self):
        with self.db() as con:
            return [dict(row) for row in con.execute('SELECT * FROM holidays ORDER BY day')]

    def save_holiday(self, day, name, actor, remove=False, now=None):
        if not actor.get('admin'):
            raise PermissionError('Somente administradores podem alterar feriados.')
        day = date.fromisoformat(day).isoformat()
        name = short_text(name, 'Nome do feriado')
        if not remove and not name:
            raise ValueError('Informe o nome do feriado.')
        now = int(time.time()) if now is None else now
        with self.db(True) as con:
            if remove:
                con.execute('DELETE FROM holidays WHERE day=?', (day,))
            else:
                con.execute('INSERT INTO holidays VALUES(?,?,?,?) ON CONFLICT(day) DO UPDATE SET name=excluded.name',
                            (day, name, actor['id'], now))
            calendar = self._calendar(con)
            rows = con.execute("SELECT * FROM tasks WHERE status IN ('ATIVO','PAUSADO') AND completed_at IS NULL AND next_ts IS NOT NULL AND business_day_policy!='keep'").fetchall()
            for row in rows:
                task = unpack(row)
                value, idx = next_slot(task['start_date'], task['clock'], task['timezone'], task['rule'],
                                      (task['last_sent'] or 0)+1, task['next_index'], task['business_day_policy'], calendar)
                if (value, idx) == (task['next_ts'], task['next_index']):
                    continue
                self._mutable(con, task, task['revision'])
                con.execute("UPDATE deliveries SET state='CANCELED',finished_at=? WHERE task_id=? AND purpose='REMINDER' AND state IN ('WAITING','ERROR')", (now, task['id']))
                status = task['status'] if value is not None else 'CONCLUIDO'
                con.execute('UPDATE tasks SET next_ts=?,next_index=?,revision=revision+1,updated_at=?,status=? WHERE id=?',
                            (value, idx, now, status, task['id']))
                self._audit(con, task['id'], actor, 'CALENDARIO_RECALCULADO', f'Complemento do calendário alterado: {day}.', now)
            self._audit(con, None, actor, 'FERIADO_REMOVIDO' if remove else 'FERIADO_SALVO', day+' '+name, now)

    def models(self, active_only=True):
        with self.db() as con:
            return [unpack(row) for row in con.execute('SELECT * FROM task_models'+(' WHERE active=1' if active_only else '')+' ORDER BY name COLLATE NOCASE,id')]

    def get_model(self, model_id):
        with self.db() as con:
            item = unpack(con.execute('SELECT * FROM task_models WHERE id=?', (model_id,)).fetchone())
            if not item:
                raise LookupError('Modelo não encontrado.')
            return item

    def save_model(self, form, actor, model_id=None, revision=0, now=None):
        if not actor.get('admin'):
            raise PermissionError('Somente administradores podem alterar modelos compartilhados.')
        data = model_input(form)
        now = int(time.time()) if now is None else now
        values = (data['name'], data['title'], data['description'], encoded(data['links']), encoded(data['rule']), data['active'])
        with self.db(True) as con:
            if model_id is None:
                model_id = con.execute('INSERT INTO task_models(name,title,description,links,rule,active,created_by,updated_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                       (*values, actor['id'], actor['id'], now, now)).lastrowid
            else:
                changed = con.execute('UPDATE task_models SET name=?,title=?,description=?,links=?,rule=?,active=?,updated_by=?,updated_at=?,revision=revision+1 WHERE id=? AND revision=?',
                                      (*values, actor['id'], now, model_id, revision)).rowcount
                if not changed:
                    raise Conflict('O modelo foi alterado. Atualize a página antes de salvar.')
            self._audit(con, None, actor, 'MODELO_SALVO', f'Modelo #{model_id}: {data["name"]}. Tarefas existentes preservadas.', now)
        return model_id
```

## apps/lembretes_tarefas/schema.sql

```sql
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, title TEXT NOT NULL,
 description TEXT NOT NULL, links TEXT NOT NULL, start_date TEXT NOT NULL, clock TEXT NOT NULL,
 timezone TEXT NOT NULL, rule TEXT NOT NULL, next_ts INTEGER, next_index INTEGER NOT NULL DEFAULT 0,
 last_sent INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 created_by INTEGER NOT NULL, created_by_name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ATIVO','PAUSADO','CONCLUIDO','CANCELADO')),
 send_count INTEGER NOT NULL DEFAULT 0, scheduled_count INTEGER NOT NULL DEFAULT 0,
 skipped_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
 revision INTEGER NOT NULL DEFAULT 1,
 business_day_policy TEXT NOT NULL DEFAULT 'keep' CHECK(business_day_policy IN ('keep','previous','next')),
 priority TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('NORMAL','ALTA','CRITICA')),
 department TEXT NOT NULL DEFAULT '', client TEXT NOT NULL DEFAULT '',
 deadline_ts INTEGER, completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(status, next_ts);
CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(created_by);
CREATE TABLE IF NOT EXISTS deliveries (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 task_id INTEGER REFERENCES tasks(id), kind TEXT NOT NULL CHECK(kind IN ('SCHEDULED','MANUAL','TEST')),
 generation INTEGER, ordinal INTEGER, scheduled_ts INTEGER NOT NULL,
 payload TEXT NOT NULL, actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('WAITING','SENDING','SENT','ERROR','UNKNOWN','CANCELED','DISCARDED')),
 available_at INTEGER NOT NULL, created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT, message_id TEXT NOT NULL,
 purpose TEXT NOT NULL DEFAULT 'REMINDER' CHECK(purpose IN ('REMINDER','ESCALATION'))
);
CREATE INDEX IF NOT EXISTS deliveries_queue ON deliveries(state, available_at);
CREATE INDEX IF NOT EXISTS deliveries_task ON deliveries(task_id, generation, scheduled_ts);
CREATE TABLE IF NOT EXISTS history (
 id INTEGER PRIMARY KEY, delivery_id INTEGER NOT NULL REFERENCES deliveries(id), at INTEGER NOT NULL,
 result TEXT NOT NULL CHECK(result IN ('ENVIADO','ERRO')), detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_at ON history(at);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id), at INTEGER NOT NULL,
 actor_id INTEGER, actor_name TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worker_state (
 id INTEGER PRIMARY KEY CHECK(id=1), heartbeat INTEGER NOT NULL, pid INTEGER NOT NULL,
 smtp_ready INTEGER NOT NULL, last_error TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS collaborators (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL,
 email TEXT NOT NULL, email_key TEXT NOT NULL UNIQUE,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 created_by INTEGER NOT NULL, updated_by INTEGER NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS collaborators_name ON collaborators(name_key);
CREATE INDEX IF NOT EXISTS collaborators_active ON collaborators(active, name_key);
CREATE TABLE IF NOT EXISTS holidays (
 day TEXT PRIMARY KEY, name TEXT NOT NULL, created_by INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS task_models (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 links TEXT NOT NULL, rule TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
 created_by INTEGER NOT NULL, updated_by INTEGER NOT NULL, created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS models_active ON task_models(active,name);
```

## apps/lembretes_tarefas/worker.py

```python
"""Processo independente, iniciado pelo Agendador de Tarefas do Windows."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import time
from .mailer import MailFailure, send_email
from .settings import load_settings
from .store import Store


class AlreadyRunning(RuntimeError):
    pass


class ProcessLock:
    """Lock do SO, liberado também quando o processo morre. Nunca apagar o arquivo."""
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        if self.file.seek(0, 2) == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise AlreadyRunning('Já existe um agendador ativo para este banco.') from None
        return self

    def __exit__(self, *args):
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()


def run_cycle(store, settings, sender=send_email, clock=time.time, limit=50):
    now = int(clock())
    ready = bool(settings.password and settings.username)
    store.heartbeat(now, os.getpid(), ready, '' if ready else 'Configure a credencial SMTP e reinicie o agendador.')
    store.queue_due(now)
    store.queue_escalations(now)
    if not ready:
        return 0
    processed = 0
    for _ in range(limit):
        now = int(clock())
        delivery = store.claim(now)
        if not delivery:
            break
        try:
            sender(settings, delivery)
        except MailFailure as exc:
            store.failure(delivery, int(clock()), str(exc), exc.transient, exc.uncertain)
            logging.warning('Envio %s: %s', delivery['id'], str(exc))
        except Exception as exc:
            # Uma falha inesperada pode ocorrer depois do aceite remoto.
            store.failure(delivery, int(clock()), f'Falha inesperada ({type(exc).__name__}). Resultado não confirmado.', uncertain=True)
            logging.error('Envio %s: falha inesperada %s', delivery['id'], type(exc).__name__)
        else:
            # Falha ao gravar o sucesso encerra o processo. A retomada marca UNKNOWN.
            store.success(delivery, int(clock()))
            logging.info('Envio %s aceito pelo SMTP; tipo=%s', delivery['id'], delivery['kind'])
        processed += 1
        store.heartbeat(int(clock()), os.getpid(), ready)
    return processed


def main(argv=None):
    parser = argparse.ArgumentParser(description='Agendador de lembretes ICC')
    parser.add_argument('--once', action='store_true', help='Processa uma rodada e encerra; pode enviar mensagens reais.')
    parser.add_argument('--check', action='store_true', help='Valida configuração e banco sem conectar ao SMTP ou enviar e-mail.')
    args = parser.parse_args(argv)
    settings = load_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if args.check:
        Store(settings.db_path)
        print('Banco e fuso válidos. Credencial SMTP: '+('disponível' if settings.password else 'ausente neste processo')+'. Nenhum e-mail enviado.')
        return 0
    try:
        with ProcessLock(settings.data_dir / 'agendador.lock'):
            logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                handlers=[RotatingFileHandler(settings.log_dir/'agendador.log', maxBytes=2_000_000, backupCount=5, encoding='utf-8'), logging.StreamHandler()])
            store = Store(settings.db_path)
            store.recover_interrupted(int(time.time()))
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            logging.info('Agendador iniciado; fuso=%s; verificação=%ss', settings.timezone, settings.poll)
            while not stop.is_set():
                run_cycle(store, settings)
                if args.once:
                    break
                stop.wait(settings.poll)
            logging.info('Agendador encerrado.')
            return 0
    except AlreadyRunning as exc:
        print(str(exc))
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Não registrar variáveis de ambiente, credenciais, mensagens ou traceback SMTP.
        print(f'Falha no agendador ({type(exc).__name__}). Confira configuração, permissões e banco.', file=sys.stderr)
        raise SystemExit(1)
```

## apps/lembretes_tarefas/mailer.py

```python
"""SMTP com classificação conservadora de falhas antes/depois de DATA."""
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr
from html import escape
import smtplib
import ssl
from zoneinfo import ZoneInfo
from .settings import REMETENTE


class MailFailure(Exception):
    def __init__(self, message, transient=False, uncertain=False):
        super().__init__(message)
        self.transient = transient
        self.uncertain = uncertain


def message_for(delivery):
    payload = delivery['payload']
    when = datetime.fromtimestamp(payload['scheduled_ts'], ZoneInfo(payload['timezone']))
    subject = 'Teste de e-mail: Lembretes de Tarefas' if delivery['kind'] == 'TEST' else 'Lembrete de tarefa: '+payload['title']
    alert = delivery.get('purpose') == 'ESCALATION'
    intro = 'Este é um lembrete referente à tarefa abaixo:'
    if alert:
        subject = 'Alerta de tarefa crítica: '+payload['title']
        deadline = datetime.fromtimestamp(payload['deadline_ts'], ZoneInfo(payload['timezone']))
        intro = (f'A tarefa crítica ainda não foi marcada como concluída. Prazo final: {deadline:%d/%m/%Y %H:%M} '
                 f'({payload["timezone"]}). O alerta é programado para 24 horas antes do prazo; '
                 'se houver indisponibilidade, será enviado na retomada. '
                 f'Departamento: {payload.get("department") or "Não informado"}. Cliente: {payload.get("client") or "Não informado"}.')
    msg = EmailMessage(policy=SMTP)
    msg['From'] = formataddr(('ICC Contabilidade | Lembretes', REMETENTE))
    msg['To'] = payload['email']
    msg['Subject'] = subject
    msg['Message-ID'] = delivery['message_id']
    msg['Date'] = format_datetime(datetime.now(timezone.utc))
    parts = [f"Olá, {payload['name']}.", intro,
             f"Tarefa: {payload['title']}", f"Data: {when:%d/%m/%Y}", f"Horário: {when:%H:%M} ({payload['timezone']})",
             payload['description'] or 'Sem descrição.', 'Links relacionados:']
    for link in payload['links']:
        parts.append(f"{link['label']}: {link['value']}")
    footer = 'Este é um lembrete automático enviado pelo Portal de Aplicações da ICC Contabilidade.'
    parts.append(footer)
    msg.set_content('\n\n'.join(parts))
    links = ''.join('<li style="margin:10px 0"><a href="'+escape(link['href'], quote=True)+'">'+escape(link['label'])+'</a><br><span style="font-size:13px;word-break:break-all">'+escape(link['value'])+'</span></li>' for link in payload['links'])
    has_paths = any(link['kind'] == 'path' for link in payload['links'])
    html = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><body style="margin:0;background:#f2f4f6;font:15px Arial,sans-serif;color:#243547">
    <div style="max-width:640px;margin:24px auto;background:white;border:1px solid #dce3e9;padding:30px">
    <p style="color:#526a7d;font-size:12px;letter-spacing:1px">ICC CONTABILIDADE · LEMBRETE DE TAREFA</p>
    <p>Olá, {escape(payload['name'])}.</p><p>{escape(intro)}</p>
    <h1 style="font-size:23px;color:#1f4e78">{escape(payload['title'])}</h1>
    <p><strong>Data:</strong> {when:%d/%m/%Y}<br><strong>Horário:</strong> {when:%H:%M} ({escape(payload['timezone'])})</p>
    <p><strong>Descrição:</strong></p><p style="line-height:1.6">{escape(payload['description'] or 'Sem descrição.').replace(chr(10), '<br>')}</p>
    {('<p><strong>Links relacionados:</strong></p><ul>'+links+'</ul>') if links else ''}
    {'<p style="font-size:13px">Se um caminho de rede não abrir pelo e-mail, copie o endereço e cole no Explorador de Arquivos do Windows. O acesso depende das permissões e da conexão à rede da empresa.</p>' if has_paths else ''}
    <p style="border-top:1px solid #dce3e9;padding-top:18px;font-size:12px;color:#526a7d">{footer}</p>
    </div></body></html>'''
    msg.add_alternative(html, subtype='html')
    return msg


def _response(code, phase):
    if code >= 400:
        raise MailFailure(f'SMTP recusou {phase} (código {code}).', transient=400 <= code < 500)


def send_email(settings, delivery, smtp_factory=None):
    if not settings.password:
        raise MailFailure('Senha SMTP não configurada no agendador.')
    if not settings.username:
        raise MailFailure('Usuário SMTP não configurado.')
    msg = message_for(delivery)
    client = None
    phase = 'connect'
    try:
        context = ssl.create_default_context()
        if smtp_factory:
            client = smtp_factory()
        elif settings.security == 'SSL':
            client = smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout, context=context)
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)
        client.ehlo_or_helo_if_needed()
        if settings.security == 'STARTTLS':
            client.starttls(context=context)
            client.ehlo()
        client.login(settings.username, settings.password)
        code, _ = client.mail(REMETENTE)
        _response(code, 'o remetente')
        code, _ = client.rcpt(delivery['payload']['email'])
        _response(code, 'o destinatário')
        # Nunca iniciar outra tentativa automática se a conexão cair em DATA.
        phase = 'data'
        code, _ = client.data(msg.as_bytes())
        if code != 250:
            if code >= 400:
                _response(code, 'a mensagem')
            raise MailFailure('Resposta SMTP inesperada após DATA. Resultado não confirmado.', uncertain=True)
    except MailFailure:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise MailFailure(f'Autenticação SMTP recusada (código {exc.smtp_code}). Execute DIAGNOSTICAR_SMTP.bat no servidor para conferir a credencial carregada e o servidor configurado.', transient=400 <= exc.smtp_code < 500) from None
    except smtplib.SMTPResponseException as exc:
        # Resposta explícita 4xx/5xx significa que o servidor recusou a etapa.
        raise MailFailure(f'SMTP recusou o envio (código {exc.smtp_code}).', transient=400 <= exc.smtp_code < 500) from None
    except ssl.SSLCertVerificationError:
        raise MailFailure('O certificado TLS do servidor SMTP não pôde ser validado. Confira servidor, data e certificados do Windows.') from None
    except (OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPException) as exc:
        if phase == 'data':
            raise MailFailure('A conexão terminou durante o envio. Resultado não confirmado; confira com o destinatário.', uncertain=True) from None
        raise MailFailure(f'Não foi possível concluir a conexão SMTP ({type(exc).__name__}).', transient=True) from None
    finally:
        # QUIT/close não pode transformar um aceite 250 em falha e causar reenvio.
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
```

## apps/lembretes_tarefas/versao.py

```python
__version__ = '1.2.0'
```

## apps/lembretes_tarefas/calendar.py

```python
"""Calendário nacional de referência e complemento local, sem acesso à internet."""
from datetime import date, timedelta
from functools import lru_cache


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return date(year, n // 31, n % 31 + 1)


@lru_cache(maxsize=128)
def national_holidays(year):
    # Referência: calendário MGI de 2026; pontos facultativos não são incluídos.
    fixed = [(1, 1, 'Confraternização Universal'), (4, 21, 'Tiradentes'),
             (5, 1, 'Dia do Trabalho'), (9, 7, 'Independência do Brasil'),
             (10, 12, 'Nossa Senhora Aparecida'), (11, 2, 'Finados'),
             (11, 15, 'Proclamação da República'), (12, 25, 'Natal')]
    if year >= 2024:
        fixed.append((11, 20, 'Dia Nacional de Zumbi e da Consciência Negra'))
    result = {date(year, month, day).isoformat(): name for month, day, name in fixed}
    result[(easter(year) - timedelta(days=2)).isoformat()] = 'Paixão de Cristo'
    return result


class BusinessCalendar:
    def __init__(self, local=()):
        self.local = frozenset(local)

    def __contains__(self, day):
        year = date.fromisoformat(day).year
        return day in self.local or day in national_holidays(year) or day in sorriso_holidays(year)


def sorriso_holidays(year):
    # Prefeitura de Sorriso, Decreto 1.450/2026. Corpus Christi é ponto facultativo.
    return {date(year, 5, 13).isoformat(): 'Emancipação de Sorriso (MT)',
            date(year, 6, 29).isoformat(): 'São Pedro, padroeiro de Sorriso (MT)'}
```

## apps/lembretes_tarefas/clients.py

```python
"""Lê apenas nome/documento do inventário existente; não importa o app de certificados."""
import json
import sqlite3


def certificate_clients(root):
    path = (root / 'dados/apps/certificados/inventario.sqlite3').resolve()
    if not path.is_file():
        return [], 'Inventário de certificados indisponível. O cliente pode ser preenchido manualmente.'
    con = None
    try:
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)
        result = set()
        for (raw,) in con.execute('SELECT payload FROM certs WHERE seen=1'):
            try:
                item = json.loads(raw)
                name = ' '.join(str(item.get('cliente', '')).split())
                document = str(item.get('documento', '')).strip()
                if name:
                    label = name + (' · ' + document if document else '')
                    if len(label) <= 240:
                        result.add(label)
            except (ValueError, TypeError, AttributeError):
                continue
        return sorted(result, key=str.casefold), ''
    except sqlite3.Error:
        return [], 'Não foi possível consultar o inventário. O cliente pode ser preenchido manualmente.'
    finally:
        if con is not None:
            con.close()
```

## apps/lembretes_tarefas/migrations.py

```python
"""Migração aditiva v3: preserva IDs, fila, histórico e programação legada."""
from datetime import datetime, timezone
from contextlib import closing
import sqlite3
import uuid

TASK_COLUMNS = {
    'business_day_policy': "TEXT NOT NULL DEFAULT 'keep' CHECK(business_day_policy IN ('keep','previous','next'))",
    'priority': "TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('NORMAL','ALTA','CRITICA'))",
    'department': "TEXT NOT NULL DEFAULT ''",
    'client': "TEXT NOT NULL DEFAULT ''",
    'deadline_ts': 'INTEGER',
    'completed_at': 'INTEGER',
}


def backup_before_upgrade(path):
    if not path.is_file():
        return
    with closing(sqlite3.connect(path, timeout=20)) as source:
        version = source.execute('PRAGMA user_version').fetchone()[0]
        exists = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
        if not exists or version >= 3:
            return
        folder = path.parent / 'backups_migracao'
        folder.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        target = folder / f'antes_v3_{stamp}_{uuid.uuid4().hex[:8]}.sqlite3'
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Falha ao conferir o backup antes da migração.')
        finally:
            destination.close()


def upgrade(con):
    columns = {row[1] for row in con.execute('PRAGMA table_info(tasks)')}
    for name, definition in TASK_COLUMNS.items():
        if name not in columns:
            con.execute(f'ALTER TABLE tasks ADD COLUMN {name} {definition}')
    if 'purpose' not in {row[1] for row in con.execute('PRAGMA table_info(deliveries)')}:
        con.execute("ALTER TABLE deliveries ADD COLUMN purpose TEXT NOT NULL DEFAULT 'REMINDER' CHECK(purpose IN ('REMINDER','ESCALATION'))")
    con.execute('CREATE INDEX IF NOT EXISTS tasks_deadline ON tasks(priority, completed_at, deadline_ts)')
    con.execute('CREATE INDEX IF NOT EXISTS tasks_categories ON tasks(department, client)')
    con.execute('PRAGMA user_version=3')
```

## apps/lembretes_tarefas/static/app.js

```javascript
'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const contactData = document.querySelector('#collaborator-data');
  if (contactData && window.ICCColaboradores) {
    window.ICCColaboradores.bind({
      name: document.querySelector('#name'), email: document.querySelector('#email'),
      id: document.querySelector('#collaborator-id'), feedback: document.querySelector('#colaborador-feedback')
    }, JSON.parse(contactData.textContent));
  }
  const links = document.querySelector('#links');
  const addLink = document.querySelector('#add-link');
  if (addLink) {
    const add = () => {
      if (links.children.length >= 20) { window.alert('São permitidos até 20 links.'); return; }
      links.append(document.querySelector('#link-template').content.cloneNode(true));
    };
    addLink.addEventListener('click', add);
    if (!links.children.length) add();
    links.addEventListener('click', event => {
      if (event.target.classList.contains('remove-link')) event.target.closest('.link-row').remove();
    });
  }
  const kind = document.querySelector('#kind');
  const mode = document.querySelector('#custom_mode');
  if (kind && mode) {
    const update = () => {
      document.querySelector('#custom-options').hidden = kind.value !== 'custom';
      document.querySelectorAll('[data-custom-mode]').forEach(element => {
        const enabled = kind.value === 'custom' && element.dataset.customMode === mode.value;
        element.hidden = !enabled;
        element.querySelectorAll('input').forEach(input => { input.disabled = !enabled; });
      });
    };
    kind.addEventListener('change', update); mode.addEventListener('change', update); update();
  }
  const priority = document.querySelector('#priority');
  if (priority) {
    const updateDeadline = () => { document.querySelector('#deadline').required = priority.value === 'CRITICA'; };
    priority.addEventListener('change', updateDeadline); updateDeadline();
  }
  const modelSelect = document.querySelector('#task-model');
  const modelData = document.querySelector('#task-model-data');
  if (modelSelect && modelData) {
    const models = JSON.parse(modelData.textContent);
    const applyModel = () => {
      const model = models.find(item => String(item.id) === modelSelect.value);
      if (!model) return;
      document.querySelector('#title').value = model.title;
      document.querySelector('#description').value = model.description;
      links.replaceChildren();
      model.links.forEach(link => {
        const row = document.querySelector('#link-template').content.cloneNode(true);
        row.querySelector('[name="link_label"]').value = link.label;
        row.querySelector('[name="link_value"]').value = link.value;
        links.append(row);
      });
      const rule = model.rule;
      kind.value = rule.kind;
      mode.value = rule.mode || 'days';
      document.querySelector('#interval').value = rule.interval || 1;
      document.querySelector('#monthday').value = rule.monthday || 10;
      document.querySelector('#end_date').value = rule.end_date || '';
      document.querySelector('#max_count').value = rule.max_count || '';
      document.querySelectorAll('[name="weekdays"]').forEach(input => {
        input.checked = (rule.weekdays || []).includes(Number(input.value));
      });
      kind.dispatchEvent(new Event('change'));
      document.querySelector('#model-feedback').textContent = 'Modelo aplicado. Confira as datas e salve a tarefa.';
    };
    modelSelect.addEventListener('change', applyModel);
    const selected = new URLSearchParams(window.location.search).get('model');
    // Não sobrescrever valores reapresentados após um erro de validação.
    if (selected && !document.querySelector('.notice.error')) {
      modelSelect.value = selected; applyModel();
    }
  }
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('.copy-path').forEach(button => {
    button.addEventListener('click', async () => {
      const feedback = document.querySelector('.copy-feedback');
      try {
        await navigator.clipboard.writeText(button.dataset.path);
        feedback.textContent = 'Caminho copiado. Cole no Explorador de Arquivos do Windows.';
      } catch (_) {
        const range = document.createRange();
        range.selectNodeContents(button.parentElement.querySelector('code'));
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        feedback.textContent = 'Caminho selecionado. Pressione Ctrl+C para copiar.';
      }
    });
  });
});
```

## apps/lembretes_tarefas/templates/base.html

```html
<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Lembretes de Tarefas{% endblock %} | ICC</title>
<link rel="stylesheet" href="{{ url_for('static',filename='app.css',v=version) }}">
<script src="{{ url_for('static',filename='colaboradores.js',v=version) }}" defer></script>
<script src="{{ url_for('static',filename='app.js',v=version) }}" defer></script></head>
<body><div class="app-shell"><header class="topbar"><a class="brand" href="{{ url_for('index') }}"><span class="brand-icon" aria-hidden="true">✓</span><span>ICC <small>CONTABILIDADE</small></span></a>
<nav aria-label="Navegação do aplicativo"><a href="{{ url_for('index') }}">Lembretes</a><a href="{{ url_for('collaborators') }}">Colaboradores</a><a href="{{ url_for('history') }}">Histórico</a><a href="{{ url_for('models') }}">Modelos</a><a href="{{ url_for('holidays') }}">Feriados</a>{% if g.usuario and g.usuario.admin %}<a href="{{ url_for('test_email') }}">Teste de e-mail</a>{% endif %}<a href="/" target="_top">Portal</a></nav>
<span class="user">{{ g.usuario.name if g.usuario else '' }}</span></header><main>
{% for category,message in get_flashed_messages(with_categories=true) %}<div class="notice {{ category }}" role="status">{{ message }}</div>{% endfor %}
{% block content %}{% endblock %}</main><footer>ICC Contabilidade · Lembretes de Tarefas <span>v{{ version }}</span></footer></div></body></html>
```

## apps/lembretes_tarefas/templates/form.html

```html
{% extends 'base.html' %}{% block content %}<div class="heading"><div><p class="eyebrow">CADASTRO</p><h1>{{ 'Editar tarefa' if task else 'Nova tarefa' }}</h1><p>Informe quem deve receber o lembrete e quando enviar.</p></div><a class="button secondary" href="{{ url_for('detail',task_id=task.id) if task else url_for('index') }}">Voltar</a></div>
{% if error %}<p class="notice error" role="alert">{{ error }}</p>{% endif %}
<form method="post" class="task-form"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="revision" value="{{ form.get('revision',0) }}">
{% if not task %}<section class="panel form-section"><label for="task-model">Usar modelo de tarefa</label><select id="task-model"><option value="">Preencher manualmente</option>{% for model in models %}<option value="{{ model.id }}">{{ model.name }}</option>{% endfor %}</select><small>Selecionar um modelo substitui título, descrição, links e repetição. Confira os dados antes de salvar.</small><p id="model-feedback" role="status"></p><a href="{{ url_for('models') }}">Ver modelos disponíveis</a></section>{% endif %}
<section class="panel form-section"><h2><span class="step">1</span> Colaborador e tarefa</h2><div class="form-grid">
<div><label for="name">Nome do colaborador *</label><input id="name" name="name" required maxlength="380" value="{{ form.get('name','') }}" list="colaborador-opcoes" autocomplete="off" placeholder="Digite o nome e selecione o colaborador" aria-describedby="colaborador-feedback"><input id="collaborator-id" type="hidden" name="collaborator_id" value="{{ form.get('collaborator_id','') }}"><datalist id="colaborador-opcoes">{% for contact in collaborators %}<option value="{{ contact.name }} · {{ contact.email }}"></option>{% endfor %}</datalist><small id="colaborador-feedback" role="status">{% if collaborators %}Selecione um cadastro para preencher o e-mail automaticamente.{% else %}Nenhum colaborador ativo cadastrado. Você pode preencher os dados manualmente.{% endif %}</small></div>
<div><label for="email">E-mail do colaborador *</label><input id="email" name="email" type="email" required maxlength="254" value="{{ form.get('email','') }}" autocomplete="email"></div>
<p class="footnote wide contact-hint">O cadastro está disponível no menu <a href="{{ url_for('collaborators') }}">Colaboradores</a>. Dados preenchidos manualmente valem somente para esta tarefa.</p>
<div class="wide"><label for="title">Título da tarefa *</label><input id="title" name="title" required maxlength="200" value="{{ form.get('title','') }}" placeholder="Ex.: Conferir certificados próximos do vencimento"></div>
<div class="wide"><label for="description">Descrição da tarefa</label><textarea id="description" name="description" rows="5" maxlength="10000" placeholder="Orientações para executar a tarefa">{{ form.get('description','') }}</textarea></div></div></section>
<section class="panel form-section"><h2>Classificação e prazo</h2><div class="form-grid">
<div><label for="department">Departamento</label><input id="department" name="department" maxlength="160" value="{{ form.get('department','') }}" placeholder="Ex.: Fiscal"></div>
<div><label for="client">Cliente</label><input id="client" name="client" maxlength="240" list="client-options" value="{{ form.get('client','') }}" placeholder="Selecione ou digite o cliente"><datalist id="client-options">{% for client in clients %}<option value="{{ client }}"></option>{% endfor %}</datalist><small>{{ client_notice or 'Sugestões do inventário de certificados. Também é possível preencher manualmente.' }}</small></div>
<div><label for="priority">Prioridade</label><select id="priority" name="priority">{% for value,label in priorities.items() %}<option value="{{ value }}" {{ 'selected' if form.get('priority','NORMAL')==value }}>{{ label }}</option>{% endfor %}</select></div>
<div><label for="deadline">Prazo final</label><input id="deadline" name="deadline" type="datetime-local" value="{{ form.get('deadline','') }}"><small>Obrigatório para prioridade Crítica. Fuso: {{ timezone }}.</small></div></div><p class="notice info top-gap">O dono da tarefa é o colaborador informado acima. Tarefas críticas ainda não concluídas geram um alerta para esse e-mail 24 horas antes do prazo final. O prazo não é deslocado pelo calendário de dias úteis.</p></section>
<section class="panel form-section"><h2><span class="step">2</span> Links relacionados</h2><p class="muted">Adicione até 20 links de planilhas, documentos, sistemas ou caminhos de rede.</p><div id="links">
{% for link in form.get('links',[]) %}<div class="link-row"><div><label>Descrição do link<input name="link_label" value="{{ link.label }}" maxlength="150" aria-label="Descrição do link"></label></div><div><label>URL ou caminho<input name="link_value" value="{{ link.value }}" maxlength="2048" aria-label="URL ou caminho"></label></div><button class="secondary remove-link" type="button" aria-label="Remover link">Remover</button></div>{% endfor %}</div>
<button id="add-link" class="secondary" type="button">+ Adicionar link</button><p class="footnote">Caminhos como \\servidor\pasta são permitidos. O destinatário precisa ter acesso à rede e à pasta.</p>
<template id="link-template"><div class="link-row"><div><label>Descrição do link<input name="link_label" maxlength="150" placeholder="Planilha de controle" aria-label="Descrição do link"></label></div><div><label>URL ou caminho<input name="link_value" maxlength="2048" placeholder="https://... ou \\servidor\pasta" aria-label="URL ou caminho"></label></div><button class="secondary remove-link" type="button">Remover</button></div></template></section>
<section class="panel form-section"><h2><span class="step">3</span> Programação do lembrete</h2><div class="form-grid three">
<div><label for="start_date">Data de execução inicial *</label><input id="start_date" name="start_date" type="date" required value="{{ form.get('start_date','') }}"></div>
<div><label for="clock">Horário do lembrete *</label><input id="clock" name="clock" type="time" required value="{{ form.get('clock','') }}"><small>Fuso: {{ timezone }}</small></div>
<div><label for="kind">Repetição *</label><select id="kind" name="kind">{% for value,label in kinds.items() %}<option value="{{ value }}" {{ 'selected' if form.get('kind','none')==value }}>{{ label }}</option>{% endfor %}</select></div></div>
<div id="custom-options" class="inset" {{ 'hidden' if form.get('kind','none')!='custom' }}><label for="custom_mode">Como repetir</label><select id="custom_mode" name="custom_mode"><option value="days" {{ 'selected' if form.get('custom_mode')=='days' }}>Intervalo de dias</option><option value="weekdays" {{ 'selected' if form.get('custom_mode')=='weekdays' }}>Dias específicos da semana</option><option value="monthday" {{ 'selected' if form.get('custom_mode')=='monthday' }}>Dia específico do mês</option></select>
<div data-custom-mode="days"><label for="interval">A cada quantos dias?</label><input id="interval" name="interval" type="number" min="1" max="3650" value="{{ form.get('interval',1) }}"></div>
<fieldset data-custom-mode="weekdays"><legend>Dias da semana</legend><div class="weekday-list">{% for day in weekdays %}<label><input type="checkbox" name="weekdays" value="{{ loop.index0 }}" {{ 'checked' if loop.index0|string in form.get('weekdays',[]) }}>{{ day }}</label>{% endfor %}</div></fieldset>
<div data-custom-mode="monthday"><label for="monthday">Dia do mês</label><input id="monthday" name="monthday" type="number" min="1" max="31" value="{{ form.get('monthday',10) }}"></div></div>
<div class="limits"><label for="business_day_policy">Quando cair em fim de semana ou feriado</label><select id="business_day_policy" name="business_day_policy">{% for value,label in business_days.items() %}<option value="{{ value }}" {{ 'selected' if form.get('business_day_policy','keep')==value }}>{{ label }}</option>{% endfor %}</select><small>Calendário nacional e Sorriso/MT. O horário e a âncora da repetição são preservados. <a href="{{ url_for('holidays') }}">Consultar feriados</a></small></div>
<div class="form-grid limits"><div><label for="end_date">Data de término <small>opcional</small></label><input id="end_date" name="end_date" type="date" value="{{ form.get('end_date','') }}"></div><div><label for="max_count">Máximo de ocorrências <small>opcional</small></label><input id="max_count" name="max_count" type="number" min="1" max="100000" value="{{ form.get('max_count','') }}"><small>Inclui a primeira. Não conta envios manuais.</small></div></div>
<p class="notice info">Nas regras personalizadas, a primeira ocorrência será na primeira data compatível com a regra, a partir da data inicial. Dias 29, 30 ou 31 usam o último dia disponível quando necessário.</p>
{% if task %}<p class="footnote">Editar apenas o conteúdo preserva a próxima execução. Alterar a regra ou a data inicia uma nova programação. Envios ainda na fila serão cancelados e o histórico será mantido.</p>{% endif %}</section>
<div class="form-actions"><span>Campos com * são obrigatórios.</span><button type="submit">Salvar tarefa</button></div></form><script id="collaborator-data" type="application/json">{{ collaborators|tojson }}</script><script id="task-model-data" type="application/json">{{ models|tojson }}</script>{% endblock %}
```

## apps/lembretes_tarefas/templates/index.html

```html
{% extends 'base.html' %}{% block content %}
<div class="heading"><div><p class="eyebrow">ORGANIZAÇÃO DA ROTINA</p><h1>Lembretes de tarefas</h1><p>Programe a tarefa. O lembrete chega por e-mail.</p></div><a class="button" href="{{ url_for('edit') }}">+ Nova tarefa</a></div>
<div class="service"><span class="dot {{ 'green' if online and worker.smtp_ready else 'amber' }}"></span>
{% if online and worker.smtp_ready %}<strong>Agendador ativo</strong><span>Última verificação: {{ worker.heartbeat|dt }}. Credencial carregada; valide o SMTP pelo teste de e-mail.</span>
{% elif online %}<strong>SMTP pendente</strong><span>{{ worker.last_error }} Os envios aguardam na fila.</span>
{% else %}<strong>Agendador sem sinal recente</strong><span>As tarefas serão salvas. A TI precisa iniciar ou verificar o agendador no servidor.</span>{% endif %}<span class="timezone">{{ timezone }}</span></div>
<div class="metrics">
{% for key,label,hint in [('active','Lembretes ativos','Programações em andamento'),('today','Lembretes para hoje','Pendentes na data de hoje'),('late','Lembretes atrasados','Horário programado já passou'),('sent','Lembretes enviados','Agendados e manuais aceitos'),('errors','Lembretes com erro','Tarefas que precisam de atenção')] %}
<section class="metric {{ key }}"><p>{{ label }}</p><strong>{{ metrics[key] }}</strong><small>{{ hint }}</small></section>{% endfor %}</div>
<section class="panel"><div class="panel-heading"><div><h2>{{ 'Tarefas da equipe' if g.usuario.admin else 'Minhas tarefas cadastradas' }}</h2><p>{{ total }} tarefa(s) encontrada(s)</p></div><a class="text-link" href="{{ url_for('history') }}">Ver histórico →</a></div>
<form method="get" class="filters"><div class="search"><label for="q">Pesquisar</label><input id="q" name="q" value="{{ filters.get('q','') }}" placeholder="Tarefa ou colaborador"></div>
<div><label for="status">Status</label><select id="status" name="status"><option value="">Todos</option>{% for value,label in statuses.items() %}<option value="{{ value }}" {{ 'selected' if filters.get('status')==value }}>{{ label }}</option>{% endfor %}</select></div>
<div><label for="priority-filter">Prioridade</label><select id="priority-filter" name="priority"><option value="">Todas</option>{% for value,label in priorities.items() %}<option value="{{ value }}" {{ 'selected' if filters.get('priority')==value }}>{{ label }}</option>{% endfor %}</select></div><div><label for="completion">Conclusão da tarefa</label><select id="completion" name="completion"><option value="">Todas</option><option value="open" {{ 'selected' if filters.get('completion')=='open' }}>Não concluída manualmente</option><option value="done" {{ 'selected' if filters.get('completion')=='done' }}>Concluída manualmente</option></select></div><div><label for="kind">Repetição</label><select id="kind" name="kind"><option value="">Todas</option>{% for value,label in kinds.items() %}<option value="{{ value }}" {{ 'selected' if filters.get('kind')==value }}>{{ label }}</option>{% endfor %}</select></div>
<div><label for="from_date">Próxima execução: de</label><input type="date" id="from_date" name="from_date" value="{{ filters.get('from_date','') }}"></div>
<div><label for="to_date">Até</label><input type="date" id="to_date" name="to_date" value="{{ filters.get('to_date','') }}"></div><button type="submit">Filtrar</button><a class="button secondary" href="{{ url_for('index') }}">Limpar</a>
<details class="wide"><summary>Filtrar por campos específicos</summary><div class="form-grid specific">{% for name,label in [('name','Colaborador'),('email','E-mail'),('title','Título da tarefa'),('department','Departamento'),('client','Cliente')] %}<div><label for="filter-{{ name }}">{{ label }}</label><input id="filter-{{ name }}" name="{{ name }}" value="{{ filters.get(name,'') }}"></div>{% endfor %}</div></details></form>
<div class="table-wrap"><table><thead><tr><th>Colaborador</th><th>Tarefa</th><th>Próxima execução</th><th>Repetição</th><th>Status</th><th>Último envio</th><th>Ações</th></tr></thead><tbody>
{% for task in tasks %}<tr><td><strong>{{ task.name }}</strong><small>{{ task.email }}</small></td><td><a href="{{ url_for('detail',task_id=task.id) }}">{{ task.title }}</a><small>{{ priorities[task.priority] }} · {{ task.department or 'Sem departamento' }}</small><small>{{ task.client or 'Sem cliente' }}</small>{% if task.deadline_ts %}<small>Prazo: {{ task.deadline_ts|dt(task.timezone) }}</small>{% endif %}{% if task.last_error %}<small class="error-text">Envio requer atenção</small>{% endif %}</td><td class="nowrap">{{ task.next_ts|dt(task.timezone) }}{% if task.next_ts and task.next_ts < now_ts and task.status=='ATIVO' %}<small class="error-text">Atrasado</small>{% endif %}</td><td>{{ describe(task.rule) }}</td><td><span class="badge {{ task.status|lower }}">{{ 'Tarefa concluída' if task.completed_at else statuses[task.status] }}</span></td><td class="nowrap">{{ task.last_sent|dt(task.timezone) if task.last_sent else 'Ainda não enviado' }}</td><td><details class="row-actions"><summary>Ações</summary><a href="{{ url_for('detail',task_id=task.id) }}">Visualizar</a>{% if task.status!='CANCELADO' and not task.completed_at %}<a href="{{ url_for('edit',task_id=task.id) }}">Editar</a><a href="{{ url_for('action',task_id=task.id,action='send') }}">Enviar agora</a>{% if task.status=='ATIVO' %}<a href="{{ url_for('action',task_id=task.id,action='pause') }}">Pausar</a>{% elif task.status=='PAUSADO' %}<a href="{{ url_for('action',task_id=task.id,action='resume') }}">Reativar</a>{% endif %}<a href="{{ url_for('action',task_id=task.id,action='complete') }}">Concluir tarefa</a><a class="error-text" href="{{ url_for('action',task_id=task.id,action='cancel') }}">Cancelar</a>{% endif %}</details></td></tr>
{% else %}<tr><td colspan="7"><div class="empty"><div class="empty-icon">✓</div><h3>Nenhuma tarefa por aqui</h3><p>Cadastre o primeiro lembrete ou ajuste os filtros.</p><a class="button" href="{{ url_for('edit') }}">Cadastrar tarefa</a></div></td></tr>{% endfor %}</tbody></table></div>{% include 'pager.html' %}</section>
<p class="footnote">Os indicadores consideram {{ 'todos os lembretes' if g.usuario.admin else 'os lembretes criados por você' }}. Os filtros se aplicam à tabela. “Enviado” indica aceite pelo servidor de e-mail.</p>
{% endblock %}
```

## apps/lembretes_tarefas/templates/detail.html

```html
{% extends 'base.html' %}{% block content %}<div class="heading"><div><p class="eyebrow">TAREFA #{{ task.id }}</p><h1>{{ task.title }}</h1><p>{{ task.name }} · {{ task.email }}</p></div><div class="actions">{% if task.status!='CANCELADO' and not task.completed_at %}<a class="button" href="{{ url_for('action',task_id=task.id,action='send') }}">Enviar agora</a><a class="button secondary" href="{{ url_for('edit',task_id=task.id) }}">Editar</a>{% endif %}<a class="button secondary" href="{{ url_for('index') }}">Voltar</a></div></div>
<div class="detail-grid"><section class="panel form-section"><h2>Informações da tarefa</h2><dl><dt>Prioridade</dt><dd>{{ priorities[task.priority] }}</dd><dt>Departamento</dt><dd>{{ task.department or 'Não informado' }}</dd><dt>Cliente</dt><dd>{{ task.client or 'Não informado' }}</dd><dt>Prazo final</dt><dd>{{ task.deadline_ts|dt(task.timezone) }}</dd><dt>Conclusão manual</dt><dd>{{ task.completed_at|dt(task.timezone) if task.completed_at else 'Ainda não concluída' }}</dd></dl>{% if task.priority=='CRITICA' %}<p class="notice info">Alerta crítico para {{ task.email }}, 24 horas antes do prazo. Encerrar a programação de lembretes não conclui a tarefa. A pausa dos lembretes mantém o alerta; concluir ou cancelar a tarefa impede novos envios.</p>{% endif %}<p class="preserve">{{ task.description or 'Sem descrição.' }}</p><h3>Links relacionados</h3><ul class="links-list">{% for link in task.links %}<li><strong>{{ link.label }}</strong>{% if link.kind=='web' %}<a href="{{ link.href }}" target="_blank" rel="noopener noreferrer">{{ link.value }}</a>{% else %}<code>{{ link.value }}</code><button type="button" class="secondary small copy-path" data-path="{{ link.value }}">Copiar caminho</button>{% endif %}</li>{% else %}<li class="muted">Nenhum link cadastrado.</li>{% endfor %}</ul><div class="copy-feedback" role="status"></div><p class="footnote">Caminhos de rede devem ser abertos pelo Explorador de Arquivos do Windows.</p></section>
<section class="panel form-section"><h2>Programação</h2><dl><dt>Status</dt><dd><span class="badge {{ task.status|lower }}">{{ 'Tarefa concluída' if task.completed_at else statuses[task.status] }}</span></dd><dt>Próxima execução</dt><dd>{{ task.next_ts|dt(task.timezone) }}</dd><dt>Dias não úteis</dt><dd>{{ business_days[task.business_day_policy] }}</dd><dt>Repetição</dt><dd>{{ describe(task.rule) }}</dd><dt>Primeira data</dt><dd>{{ task.start_date }} às {{ task.clock }}</dd><dt>Fuso</dt><dd>{{ task.timezone }}</dd><dt>Término</dt><dd>{{ task.rule.get('end_date','Sem término definido') }}</dd><dt>Limite de ocorrências</dt><dd>{{ task.rule.get('max_count','Sem limite definido') }}</dd><dt>Último envio</dt><dd>{{ task.last_sent|dt(task.timezone) }}</dd><dt>Envios aceitos</dt><dd>{{ task.send_count }} ({{ task.scheduled_count }} agendados)</dd><dt>Ocorrências puladas</dt><dd>{{ task.skipped_count }}</dd><dt>Criada por</dt><dd>{{ task.created_by_name }} em {{ task.created_at|dt }}</dd></dl>
<div class="actions">{% if task.status=='ATIVO' %}<a class="button secondary" href="{{ url_for('action',task_id=task.id,action='pause') }}">Pausar</a>{% elif task.status=='PAUSADO' %}<a class="button secondary" href="{{ url_for('action',task_id=task.id,action='resume') }}">Reativar</a>{% endif %}{% if task.status!='CANCELADO' and not task.completed_at %}<a class="button secondary" href="{{ url_for('action',task_id=task.id,action='complete') }}">Concluir tarefa</a><a class="button secondary error-text" href="{{ url_for('action',task_id=task.id,action='cancel') }}">Cancelar tarefa</a>{% endif %}</div></section></div>
{% include 'pending.html' %}<section class="panel"><div class="panel-heading"><h2>Últimas tentativas de envio</h2><a href="{{ url_for('history') }}">Histórico completo →</a></div>{% include 'history_table.html' %}</section>
<section class="panel form-section"><details><summary>Registro de alterações</summary><ul class="audit-list">{% for item in audits %}<li><strong>{{ item.at|dt }}</strong> · {{ item.actor_name }} · {{ item.action }}{% if item.detail %}<small>{{ item.detail }}</small>{% endif %}</li>{% endfor %}</ul></details></section>{% endblock %}
```

## apps/lembretes_tarefas/templates/confirm.html

```html
{% extends 'base.html' %}{% block content %}<section class="panel confirm-card"><p class="eyebrow">CONFIRMAÇÃO</p><h1>{{ label }}</h1><h2>{{ task.title }}</h2><p>{{ task.name }}<br><strong>{{ task.email }}</strong></p>
{% if action=='send' %}<p>Será colocado na fila um lembrete adicional para envio assim que o agendador processar a solicitação.</p><p class="notice info">A próxima execução permanece em {{ task.next_ts|dt(task.timezone) }}. O envio manual ficará registrado no histórico.</p>
{% elif action=='complete' %}<p>A tarefa será marcada como concluída. Lembretes e alertas ainda aguardando serão cancelados; o histórico será preservado.</p>{% elif action=='cancel' %}<p>Esta tarefa deixará de enviar lembretes. Os registros e o histórico serão preservados. Para programar novos lembretes após o cancelamento, cadastre outra tarefa.</p>
{% elif action=='pause' %}<p>Os lembretes ficarão suspensos até a reativação. O alerta de tarefa crítica continua ativo até a conclusão ou cancelamento da tarefa.</p>
{% else %}<p>O sistema retomará a partir da primeira ocorrência futura. Datas que passaram durante a pausa não serão enviadas.</p>{% endif %}
<form method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="action_token" value="{{ token }}"><div class="actions"><button class="{{ 'danger' if action=='cancel' else '' }}" type="submit">Confirmar: {{ label|lower }}</button><a class="button secondary" href="{{ url_for('detail',task_id=task.id) }}">Voltar</a></div></form></section>{% endblock %}
```

## apps/lembretes_tarefas/templates/pending.html

```html
{% if pending %}<section class="panel"><div class="panel-heading"><h2>Fila e ocorrências que precisam de atenção</h2></div><div class="pending-list">{% for item in pending %}<article class="pending-item"><div><span class="badge {{ 'error' if item.state in ['ERROR','UNKNOWN'] else 'paused' }}">{{ delivery_status[item.state] }}</span><strong>{{ item.payload.title }}</strong><small>{{ item.payload.email }} · {{ 'Alerta crítico ao dono' if item.purpose=='ESCALATION' else delivery_kinds[item.kind] }} · {{ item.created_at|dt }}</small>{% if item.error %}<p class="error-text">{{ item.error }}</p>{% endif %}{% if item.state=='WAITING' and item.error %}<p class="muted">Nova tentativa prevista: {{ item.available_at|dt }}</p>{% endif %}</div>
{% if item.state in ['ERROR','UNKNOWN'] %}<div class="actions">{% if item.state=='ERROR' %}<form method="post" action="{{ url_for('resolve',delivery_id=item.id,action='retry') }}" data-confirm="Tentar novamente este envio recusado pelo SMTP?"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button class="secondary">Tentar novamente</button></form>{% endif %}
<form method="post" action="{{ url_for('resolve',delivery_id=item.id,action='confirm_sent') }}" data-confirm="Você conferiu com o destinatário que este e-mail foi recebido? Esta ação registra sua confirmação e não envia outra mensagem."><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button class="secondary">Confirmar como enviado</button></form>
<form method="post" action="{{ url_for('resolve',delivery_id=item.id,action='discard') }}" data-confirm="Encerrar esta ocorrência sem reenviar? Se for recorrente, a tarefa seguirá para a próxima data futura."><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button class="secondary">Encerrar sem reenviar</button></form></div>{% endif %}</article>{% endfor %}</div></section>{% endif %}
```

## apps/lembretes_tarefas/templates/history_table.html

```html
<div class="table-wrap"><table><thead><tr><th>Data/hora</th><th>Colaborador</th><th>Tarefa</th><th>Origem</th><th>Resultado</th><th>Detalhe</th></tr></thead><tbody>{% for item in history %}<tr><td class="nowrap">{{ item.at|dt }}</td><td><strong>{{ item.payload.name }}</strong><small>{{ item.payload.email }}</small></td><td>{% if item.task_id %}<a href="{{ url_for('detail',task_id=item.task_id) }}">{{ item.payload.title }}</a>{% else %}{{ item.payload.title }}{% endif %}</td><td>{{ 'Alerta crítico ao dono' if item.purpose=='ESCALATION' else delivery_kinds[item.kind] }}</td><td><span class="badge {{ 'ativo' if item.result=='ENVIADO' else 'error' }}">{{ item.result }}</span></td><td>{{ item.detail }}</td></tr>{% else %}<tr><td colspan="6"><div class="empty"><h3>Nenhum envio registrado</h3><p>O histórico aparecerá após o processamento do agendador.</p></div></td></tr>{% endfor %}</tbody></table></div>
```

## apps/lembretes_tarefas/templates/models.html

```html
{% extends 'base.html' %}{% block content %}
<div class="heading"><div><p class="eyebrow">CADASTRO</p><h1>Modelos de tarefas</h1><p>Preencha novas tarefas com instruções e repetições já definidas.</p></div>{% if g.usuario.admin %}<a class="button" href="{{ url_for('model_edit') }}">+ Novo modelo</a>{% endif %}</div>
<section class="panel"><div class="table-wrap"><table><thead><tr><th>Modelo</th><th>Título</th><th>Repetição</th><th>Situação</th><th>Ações</th></tr></thead><tbody>
{% for model in models %}<tr><td>{{ model.name }}</td><td>{{ model.title }}</td><td>{{ describe(model.rule) }}</td><td>{{ 'Ativo' if model.active else 'Inativo' }}</td><td>{% if model.active %}<a href="{{ url_for('edit',model=model.id) }}">Usar modelo</a>{% endif %}{% if g.usuario.admin %} <a href="{{ url_for('model_edit',model_id=model.id) }}">Editar</a>{% endif %}</td></tr>{% else %}<tr><td colspan="5"><div class="empty">Nenhum modelo cadastrado. A administração pode criar modelos compartilhados.</div></td></tr>{% endfor %}</tbody></table></div></section>
<p class="footnote">O modelo é copiado para o formulário. Alterar ou inativar um modelo não modifica tarefas existentes.</p>{% endblock %}
```

## apps/lembretes_tarefas/templates/model_form.html

```html
{% extends 'base.html' %}{% block content %}
<div class="heading"><div><p class="eyebrow">MODELOS COMPARTILHADOS</p><h1>{{ 'Editar modelo' if model else 'Novo modelo' }}</h1><p>Ao selecionar este modelo, título, descrição, links e repetição serão copiados para a nova tarefa.</p></div><a class="button secondary" href="{{ url_for('models') }}">Voltar</a></div>
{% if error %}<p class="notice error" role="alert">{{ error }}</p>{% endif %}
<form method="post" class="task-form"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="revision" value="{{ form.get('revision',0) }}">
<section class="panel form-section"><div class="form-grid">
<div><label for="model_name">Nome do modelo *</label><input id="model_name" name="model_name" required maxlength="120" value="{{ form.get('model_name','') }}"></div>
<div><label for="active">Situação</label><select id="active" name="active"><option value="1" {{ 'selected' if form.get('active',1)|string=='1' }}>Ativo</option><option value="0" {{ 'selected' if form.get('active',1)|string=='0' }}>Inativo</option></select></div>
<div class="wide"><label for="title">Título da tarefa *</label><input id="title" name="title" required maxlength="200" value="{{ form.get('title','') }}"></div>
<div class="wide"><label for="description">Descrição</label><textarea id="description" name="description" rows="5" maxlength="10000">{{ form.get('description','') }}</textarea></div></div></section>
<section class="panel form-section"><h2><span class="step">2</span> Links relacionados</h2><p class="muted">Adicione até 20 links de planilhas, documentos, sistemas ou caminhos de rede.</p><div id="links">
{% for link in form.get('links',[]) %}<div class="link-row"><div><label>Descrição do link<input name="link_label" value="{{ link.label }}" maxlength="150" aria-label="Descrição do link"></label></div><div><label>URL ou caminho<input name="link_value" value="{{ link.value }}" maxlength="2048" aria-label="URL ou caminho"></label></div><button class="secondary remove-link" type="button" aria-label="Remover link">Remover</button></div>{% endfor %}</div>
<button id="add-link" class="secondary" type="button">+ Adicionar link</button><p class="footnote">Caminhos como \\servidor\pasta são permitidos. O destinatário precisa ter acesso à rede e à pasta.</p>
<template id="link-template"><div class="link-row"><div><label>Descrição do link<input name="link_label" maxlength="150" placeholder="Planilha de controle" aria-label="Descrição do link"></label></div><div><label>URL ou caminho<input name="link_value" maxlength="2048" placeholder="https://... ou \\servidor\pasta" aria-label="URL ou caminho"></label></div><button class="secondary remove-link" type="button">Remover</button></div></template></section>
<section class="panel form-section"><h2>Regra de repetição</h2><div><label for="kind">Repetição *</label><select id="kind" name="kind">{% for value,label in kinds.items() %}<option value="{{ value }}" {{ 'selected' if form.get('kind','none')==value }}>{{ label }}</option>{% endfor %}</select></div>
<div id="custom-options" class="inset" {{ 'hidden' if form.get('kind','none')!='custom' }}><label for="custom_mode">Como repetir</label><select id="custom_mode" name="custom_mode"><option value="days" {{ 'selected' if form.get('custom_mode')=='days' }}>Intervalo de dias</option><option value="weekdays" {{ 'selected' if form.get('custom_mode')=='weekdays' }}>Dias específicos da semana</option><option value="monthday" {{ 'selected' if form.get('custom_mode')=='monthday' }}>Dia específico do mês</option></select>
<div data-custom-mode="days"><label for="interval">A cada quantos dias?</label><input id="interval" name="interval" type="number" min="1" max="3650" value="{{ form.get('interval',1) }}"></div>
<fieldset data-custom-mode="weekdays"><legend>Dias da semana</legend><div class="weekday-list">{% for day in weekdays %}<label><input type="checkbox" name="weekdays" value="{{ loop.index0 }}" {{ 'checked' if loop.index0|string in form.get('weekdays',[]) }}>{{ day }}</label>{% endfor %}</div></fieldset>
<div data-custom-mode="monthday"><label for="monthday">Dia do mês</label><input id="monthday" name="monthday" type="number" min="1" max="31" value="{{ form.get('monthday',10) }}"></div></div>
<div class="form-grid limits"><div><label for="end_date">Data de término <small>opcional</small></label><input id="end_date" name="end_date" type="date" value="{{ form.get('end_date','') }}"></div><div><label for="max_count">Máximo de ocorrências <small>opcional</small></label><input id="max_count" name="max_count" type="number" min="1" max="100000" value="{{ form.get('max_count','') }}"><small>Inclui a primeira. Não conta envios manuais.</small></div></div>
<p class="footnote">Data inicial, horário, responsável, cliente, prioridade e prazo final serão definidos na tarefa. Limites absolutos de término devem ser conferidos ao aplicar o modelo.</p></section><div class="form-actions"><button>Salvar modelo</button></div></form>{% endblock %}
```

## apps/lembretes_tarefas/templates/holidays.html

```html
{% extends 'base.html' %}{% block content %}
<div class="heading"><div><p class="eyebrow">CALENDÁRIO</p><h1>Feriados · Sorriso/MT</h1><p>Finais de semana e feriados são considerados ao antecipar ou postergar os lembretes.</p></div></div>
<section class="panel form-section"><h2>Calendário nacional e municipal</h2><form method="get" class="inline-form"><label for="year">Ano</label><input id="year" name="year" type="number" min="1900" max="9998" value="{{ year }}" required><button>Consultar</button></form><p class="footnote">Regras de referência conferidas no calendário oficial de 2026. As datas móveis são calculadas anualmente. Pontos facultativos não são incluídos automaticamente; a TI pode cadastrá-los abaixo se forem adotados pelo escritório.</p>
<div class="table-wrap"><table><thead><tr><th>Data</th><th>Feriado</th><th>Abrangência</th></tr></thead><tbody>{% for item in defaults %}<tr><td>{{ item.day }}</td><td>{{ item.name }}</td><td>{{ item.scope }}</td></tr>{% endfor %}</tbody></table></div></section>
<section class="panel form-section"><h2>Datas adicionais do escritório</h2>
{% if g.usuario.admin %}<form method="post" class="form-grid"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><div><label for="day">Data *</label><input id="day" name="day" type="date" required></div><div><label for="holiday-name">Nome *</label><input id="holiday-name" name="name" maxlength="160" required></div><div><button>Salvar data adicional</button></div></form><p class="footnote">Cada data adicional vale para aquele ano. Salvar uma data já cadastrada altera sua descrição. A atualização recalcula as próximas ocorrências ainda não enviadas. Resolva envios em andamento ou sem confirmação antes de alterar um calendário que os afete.</p>{% endif %}
<div class="table-wrap"><table><thead><tr><th>Data</th><th>Descrição</th>{% if g.usuario.admin %}<th>Ações</th>{% endif %}</tr></thead><tbody>{% for item in holidays %}<tr><td>{{ item.day }}</td><td>{{ item.name }}</td>{% if g.usuario.admin %}<td><form method="post" data-confirm="Remover esta data adicional e recalcular próximas ocorrências?"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="day" value="{{ item.day }}"><input type="hidden" name="action" value="remove"><button class="secondary">Remover</button></form></td>{% endif %}</tr>{% else %}<tr><td colspan="3">Nenhuma data adicional cadastrada.</td></tr>{% endfor %}</tbody></table></div></section>{% endblock %}
```
