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
