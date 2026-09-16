from contextlib import closing
"""Calendário, migração, alertas e telas em bancos temporários; sem SMTP real."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_core as core
from test_core import ADMIN, USER, OTHER, NOW, form, ts
import test_integracao as integration
from apps.lembretes_tarefas.calendar import BusinessCalendar, national_holidays
from apps.lembretes_tarefas.clients import certificate_clients
from apps.lembretes_tarefas.mailer import message_for
from apps.lembretes_tarefas.recurrence import business_date, next_slot, slot
from apps.lembretes_tarefas.store import Store, Conflict
from apps.lembretes_tarefas.validation import task_input
from apps.lembretes_tarefas.worker import run_cycle


class CalendarTests(unittest.TestCase):
    def test_national_and_sorriso_exclude_optional_days(self):
        calendar = BusinessCalendar()
        for day in ['2026-04-03','2026-05-13','2026-06-29','2026-11-20','2027-03-26']:
            self.assertIn(day, calendar)
        for day in ['2026-02-17','2026-06-04','2026-10-28']:
            self.assertNotIn(day, calendar)
        self.assertEqual(len(national_holidays(2026)), 10)

    def test_advance_and_postpone_cross_weekend_and_holiday(self):
        calendar = BusinessCalendar(['2026-09-08'])
        day = date(2026,9,6)
        self.assertEqual(business_date(day,'keep',calendar), day)
        self.assertEqual(business_date(day,'previous',calendar),date(2026,9,4))
        self.assertEqual(business_date(day,'next',calendar),date(2026,9,9))

    def test_monthly_anchor_and_year_boundary(self):
        cal = BusinessCalendar()
        self.assertEqual(slot('2026-05-31','09:00','America/Cuiaba',{'kind':'monthly'},0,'next',cal),ts('2026-06-01T09:00:00-04:00'))
        self.assertEqual(slot('2026-05-31','09:00','America/Cuiaba',{'kind':'monthly'},1,'next',cal),ts('2026-06-30T09:00:00-04:00'))
        self.assertEqual(business_date(date(2027,1,1),'previous',cal),date(2026,12,31))

    def test_adjustment_does_not_extend_nominal_count(self):
        rule={'kind':'daily','max_count':1,'end_date':'2026-09-06'}
        value,index=next_slot('2026-09-06','09:00','America/Cuiaba',rule,0,policy='next',holidays=BusinessCalendar())
        self.assertEqual((value,index),(ts('2026-09-08T09:00:00-04:00'),0))
        self.assertIsNone(next_slot('2026-09-06','09:00','America/Cuiaba',rule,value+1,policy='next',holidays=BusinessCalendar())[0])

    def test_adjusted_past_initial_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'passado'):
            task_input(form(start_date='2026-09-20',business_day_policy='previous'),'America/Cuiaba',ts('2026-09-18T10:00:00-04:00'),holidays=BusinessCalendar())


class ImprovementStoreTests(unittest.TestCase):
    setUp=core.StoreTests.setUp
    tearDown=core.StoreTests.tearDown
    create=core.StoreTests.create

    def critical(self, **changes):
        return self.create(priority='CRITICA',deadline='2026-09-17T09:00',**changes)

    def test_escalation_boundary_recipient_and_idempotency(self):
        ident=self.critical()
        alert_time=ts('2026-09-16T09:00:00-04:00')
        self.assertEqual(self.store.queue_escalations(alert_time-1),0)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(self.store.queue_escalations,[alert_time]*8)),1)
        delivery=self.store.claim(alert_time)
        self.assertEqual(delivery['purpose'],'ESCALATION')
        self.assertEqual(delivery['payload']['email'],'pessoa@example.com')
        msg=message_for(delivery)
        self.assertIn('crítica',str(msg['Subject']))
        self.assertIn('17/09/2026 09:00',msg.get_body(preferencelist=('plain',)).get_content())
        self.store.success(delivery,alert_time)
        self.assertEqual(Store(self.settings.db_path).queue_escalations(alert_time+100),0)
        self.assertEqual(self.store.get(ident,USER)['send_count'],0)

    def test_worker_escalation_uses_existing_queue(self):
        ident=self.critical()
        now=ts('2026-09-16T09:00:00-04:00'); sent=[]
        run_cycle(self.store,self.settings,sender=lambda settings,item:sent.append(item),clock=lambda:now)
        self.assertEqual(sent[0]['purpose'],'ESCALATION')
        self.assertEqual(sum(x['purpose']=='ESCALATION' for x in sent),1)
        self.assertEqual(self.store.get(ident,USER)['send_count'],1)

    def test_normal_and_high_do_not_alert(self):
        for priority in ('NORMAL','ALTA'):
            self.create(priority=priority,deadline='2026-09-17T09:00')
        self.assertEqual(self.store.queue_escalations(ts('2026-09-20T09:00:00-04:00')),0)

    def test_conclusion_cancels_queued_alert_and_reminder(self):
        ident=self.critical(); now=ts('2026-09-16T09:00:00-04:00')
        self.store.queue_due(now); self.store.queue_escalations(now)
        self.store.change_status(ident,'complete',USER,1,now)
        self.assertIsNone(self.store.claim(now))
        self.assertEqual(self.store.queue_escalations(now+100),0)
        item=self.store.get(ident,USER)
        self.assertEqual((item['completed_at'],item['next_ts']),(now,None))
        with self.assertRaises(ValueError): self.store.queue_manual(ident,USER,'extra',now,2)

    def test_finished_schedule_is_not_manual_completion(self):
        ident=self.critical(); now=NOW+3600
        self.store.queue_due(now); self.store.success(self.store.claim(now),now)
        task=self.store.get(ident,USER)
        self.assertEqual(task['status'],'CONCLUIDO')
        self.assertIsNone(task['completed_at'])
        self.assertEqual(self.store.queue_escalations(ts('2026-09-16T09:00:00-04:00')),1)

    def test_paused_task_keeps_alert_but_cancel_suppresses(self):
        ident=self.critical()
        self.store.change_status(ident,'pause',USER,1,NOW)
        self.assertEqual(self.store.queue_escalations(NOW+86400*3),1)
        self.store.change_status(ident,'cancel',USER,2,NOW+1)
        self.assertIsNone(self.store.claim(NOW+86400*3))

    def test_unknown_alert_is_never_automatically_requeued(self):
        ident=self.critical(); now=NOW+86400*3
        self.store.queue_escalations(now); delivery=self.store.claim(now)
        self.store.recover_interrupted(now+1)
        self.assertEqual(self.store.queue_escalations(now+2),0)
        with self.assertRaises(Conflict): self.store.change_status(ident,'complete',USER,1,now+3)
        self.store.resolve(delivery['id'],'discard',USER,now+4)
        self.assertEqual(self.store.queue_escalations(now+5),0)

    def test_edit_title_does_not_repeat_sent_alert(self):
        ident=self.critical(); now=NOW+86400
        self.store.queue_escalations(now+3600); delivery=self.store.claim(now+3600)
        self.store.success(delivery,now+3600)
        task=self.store.get(ident,USER)
        data=task_input(form(priority='CRITICA',deadline='2026-09-17T09:00',title='Alterado'),'America/Cuiaba',now,task)
        self.store.save(data,USER,ident,task['revision'],now)
        self.assertEqual(self.store.queue_escalations(now+7200),0)

    def test_alert_retry_and_changed_deadline(self):
        ident=self.critical(); now=NOW+86400*3
        self.store.queue_escalations(now); delivery=self.store.claim(now)
        self.store.failure(delivery,now,'Recusado')
        self.store.resolve(delivery['id'],'retry',USER,now+1)
        self.store.success(self.store.claim(now+1),now+1)
        task=self.store.get(ident,USER)
        data=task_input(form(priority='CRITICA',deadline='2026-09-25T09:00'),'America/Cuiaba',now,task)
        self.store.save(data,USER,ident,task['revision'],now)
        self.assertEqual(self.store.queue_escalations(ts('2026-09-24T09:00:00-04:00')),1)

    def test_categories_filters_and_permissions(self):
        ident=self.create(department='Fiscal',client='Empresa <A>')
        self.create(owner=OTHER,department='Fiscal',client='Empresa <A>')
        self.assertEqual(self.store.list_tasks(USER,{'department':'Fiscal','client':'<A>'})[1],1)
        self.assertEqual(self.store.list_tasks(USER,{'department':'Pessoal'})[1],0)
        self.assertEqual(self.store.list_tasks(ADMIN,{'client':'<A>'})[1],2)
        with self.assertRaises(LookupError): self.store.change_status(ident,'complete',OTHER,1,NOW)

    def test_holiday_change_reschedules_pending_not_history(self):
        ident=self.create(start_date='2026-09-21',business_day_policy='next')
        self.store.queue_due(ts('2026-09-21T09:00:00-04:00'))
        self.store.save_holiday('2026-09-21','Feriado local',ADMIN,now=NOW)
        task=self.store.get(ident,USER)
        self.assertEqual(task['next_ts'],ts('2026-09-22T09:00:00-04:00'))
        self.assertEqual(self.store.pending(USER),[])
        self.store.save_holiday('2026-09-21','',ADMIN,remove=True,now=NOW)
        self.assertEqual(self.store.get(ident,USER)['next_ts'],ts('2026-09-21T09:00:00-04:00'))
        with self.assertRaises(PermissionError): self.store.save_holiday('2026-09-22','Teste',USER)

    def test_holiday_edit_rolls_back_when_delivery_in_flight(self):
        self.create(start_date='2026-09-21',business_day_policy='next')
        now=ts('2026-09-21T09:00:00-04:00'); self.store.queue_due(now); self.store.claim(now)
        with self.assertRaises(Conflict): self.store.save_holiday('2026-09-21','Feriado',ADMIN,now=now)
        self.assertEqual(self.store.holidays(),[])

    def test_models_snapshot_validation_and_optimistic_edit(self):
        source=form(model_name='Rotina',kind='custom',custom_mode='weekdays',weekdays=['0','4'],link_label=['Site'],link_value=['https://example.com'])
        model_id=self.store.save_model(source,ADMIN,now=NOW)
        model=self.store.get_model(model_id)
        self.assertEqual(model['rule']['weekdays'],[0,4])
        self.assertEqual(model['links'][0]['value'],'https://example.com')
        ident=self.create(title=model['title'])
        source['title']='Novo título'; self.store.save_model(source,ADMIN,model_id,1,NOW)
        self.assertNotEqual(self.store.get(ident,USER)['title'],self.store.get_model(model_id)['title'])
        with self.assertRaises(Conflict): self.store.save_model(source,ADMIN,model_id,1,NOW)
        with self.assertRaises(PermissionError): self.store.save_model(source,USER)
        source['link_value']='javascript:alert(1)'
        with self.assertRaises(ValueError): self.store.save_model(source,ADMIN)

    def test_migrate_actual_v2_keeps_rows_and_backup_and_is_idempotent(self):
        path=Path(self.temp.name)/'old.sqlite3'
        with closing(sqlite3.connect(path)) as con, con:
            con.executescript(Path(__file__).with_name('schema_v2.sql').read_text(encoding='utf-8'))
            con.execute("INSERT INTO tasks(id,name,email,title,description,links,start_date,clock,timezone,rule,created_at,updated_at,created_by,created_by_name,status,next_ts) VALUES(7,'Dono','dono@example.com','Legado','','[]','2026-09-15','09:00','America/Cuiaba','{\"kind\":\"none\"}',1,1,2,'Criador','ATIVO',12345)")
            con.execute("INSERT INTO deliveries(id,request_key,task_id,kind,scheduled_ts,payload,actor_id,actor_name,state,available_at,created_at,message_id) VALUES(4,'old',7,'SCHEDULED',12345,'{}',2,'Criador','SENT',12345,1,'<old>')")
            con.execute("INSERT INTO history VALUES(9,4,1,'ENVIADO','Preservar')")
        migrated=Store(path); Store(path)
        task=migrated.get(7,USER)
        self.assertEqual((task['priority'],task['business_day_policy'],task['next_ts']),('NORMAL','keep',12345))
        with migrated.db() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(con.execute('SELECT detail FROM history WHERE id=9').fetchone()[0],'Preservar')
            self.assertEqual(con.execute('SELECT purpose FROM deliveries WHERE id=4').fetchone()[0],'REMINDER')
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(len(list(path.parent.glob('backups_migracao/*.sqlite3'))),1)

    def test_new_columns_rollback_if_migration_fails(self):
        path=Path(self.temp.name)/'rollback.sqlite3'
        with closing(sqlite3.connect(path)) as con, con:
            con.executescript(Path(__file__).with_name('schema_v2.sql').read_text(encoding='utf-8'))
        from apps.lembretes_tarefas.migrations import upgrade
        def broken(con):
            upgrade(con)
            raise RuntimeError('Falha simulada')
        with patch('apps.lembretes_tarefas.store.upgrade',side_effect=broken),self.assertRaises(RuntimeError): Store(path)
        with closing(sqlite3.connect(path)) as con, con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0],2)
            self.assertNotIn('priority',{r[1] for r in con.execute('PRAGMA table_info(tasks)')})

    def test_clients_are_read_only_and_no_secrets_returned(self):
        path=Path(self.temp.name)/'dados/apps/certificados/inventario.sqlite3';path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(path)) as con, con:
            con.execute('CREATE TABLE certs(payload TEXT,seen INTEGER,password BLOB)')
            con.executemany('INSERT INTO certs VALUES(?,?,?)',[(json.dumps({'cliente':'Empresa','documento':'123','senha':'hidden'}),1,b'secret'),('{invalid',1,b'secret')])
        before=path.read_bytes()
        names,notice=certificate_clients(Path(self.temp.name))
        self.assertEqual(names,['Empresa · 123']);self.assertEqual(notice,'');self.assertEqual(path.read_bytes(),before)


class ImprovementIntegrationTests(unittest.TestCase):
    setUp=integration.PortalIntegrationTests.setUp
    tearDown=integration.PortalIntegrationTests.tearDown
    login=integration.PortalIntegrationTests.login
    csrf=integration.PortalIntegrationTests.csrf

    def test_new_screens_under_real_portal_auth(self):
        self.login()
        for route in ['/feriados','/modelos','/modelos/novo','/nova','/?department=Fiscal&client=Empresa']:
            response=self.client.get('/lembretes'+route)
            self.assertEqual(response.status_code,200,response.text)
        response=self.client.post('/lembretes/feriados',data={'day':'2026-09-22','name':'Feriado'})
        self.assertEqual(response.status_code,400)

    def test_ordinary_user_cannot_manage_models_or_calendar(self):
        self.login('membro');page=self.client.get('/lembretes/nova');token=self.csrf(page)
        self.assertEqual(self.client.get('/lembretes/modelos/novo').status_code,403)
        self.assertEqual(self.client.post('/lembretes/feriados',data={'csrf_token':token,'day':'2026-09-22','name':'Feriado'}).status_code,403)

    def test_critical_form_save_and_manual_completion(self):
        import time
        from datetime import datetime, timedelta
        self.login('membro');page=self.client.get('/lembretes/nova')
        when=datetime.fromtimestamp(time.time(),self.settings.zone)+timedelta(days=3)
        payload=form(start_date=when.date().isoformat(),clock='09:00',priority='CRITICA',deadline=(when+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),department='Fiscal',client='<Empresa>',business_day_policy='next')
        payload['csrf_token']=self.csrf(page)
        response=self.client.post('/lembretes/nova',data=payload)
        self.assertEqual(response.status_code,303,response.text)
        task=self.store.list_tasks(USER)[0][0]
        page=self.client.get(response.location);self.assertIn('&lt;Empresa&gt;',page.text)
        page=self.client.get('/lembretes/tarefas/'+str(task['id'])+'/editar')
        self.assertIn('value="Fiscal"',page.text)
        page=self.client.get('/lembretes/tarefas/'+str(task['id'])+'/acao/complete')
        import re
        token=re.search(r'name="action_token" value="([^"]+)"',page.text)[1]
        response=self.client.post('/lembretes/tarefas/'+str(task['id'])+'/acao/complete',data={'csrf_token':self.csrf(page),'action_token':token})
        self.assertEqual(response.status_code,303)
        self.assertIsNotNone(self.store.get(task['id'],USER)['completed_at'])


if __name__ == '__main__':
    unittest.main()
