"""Testes de comportamento sem SMTP real, credenciais ou dados de produção."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import smtplib
import sys
import tempfile
import unittest
from werkzeug.datastructures import MultiDict

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from apps.lembretes_tarefas.mailer import MailFailure, message_for, send_email
from apps.lembretes_tarefas.recurrence import next_slot, slot
from apps.lembretes_tarefas.settings import Settings
from apps.lembretes_tarefas.store import Store, Conflict
from apps.lembretes_tarefas.validation import email, related_link, task_input
from apps.lembretes_tarefas.worker import ProcessLock, AlreadyRunning, run_cycle

ADMIN = {'id':1,'name':'Admin teste','admin':True,'routes':['/lembretes']}
USER = {'id':2,'name':'Usuário teste','admin':False,'routes':['/lembretes']}
OTHER = {'id':3,'name':'Outro usuário','admin':False,'routes':['/lembretes']}


def ts(text):
    return int(datetime.fromisoformat(text).timestamp())


NOW = ts('2026-09-15T08:00:00-04:00')


def form(**changes):
    value = MultiDict({'name':'Colaborador teste','email':'pessoa@example.com','title':'Conferir planilha',
        'description':'Teste sem envio real','start_date':'2026-09-15','clock':'09:00','kind':'none'})
    value.update(changes)
    # MultiDict.update adiciona valores; substituir explicitamente alterações.
    for key, item in changes.items():
        if isinstance(item,list): value.setlist(key,item)
        else: value[key]=item
    return value


class RecurrenceTests(unittest.TestCase):
    def test_month31_does_not_drift(self):
        rule={'kind':'monthly'}
        dates=[datetime.fromtimestamp(slot('2026-01-31','08:00','America/Cuiaba',rule,i),Settings().zone).date().isoformat() for i in range(4)]
        self.assertEqual(dates,['2026-01-31','2026-02-28','2026-03-31','2026-04-30'])

    def test_leap_year_preserves_anchor(self):
        rule={'kind':'yearly'}
        values=[datetime.fromtimestamp(slot('2024-02-29','08:00','America/Cuiaba',rule,i),Settings().zone).date().isoformat() for i in [1,4]]
        self.assertEqual(values,['2025-02-28','2028-02-29'])

    def test_weekdays_respects_start(self):
        rule={'kind':'custom','mode':'weekdays','weekdays':[0,4]}
        values=[datetime.fromtimestamp(slot('2026-09-15','09:00','America/Cuiaba',rule,i),Settings().zone).date().isoformat() for i in range(3)]
        self.assertEqual(values,['2026-09-18','2026-09-21','2026-09-25'])

    def test_custom_monthday_after_start(self):
        value,_=next_slot('2026-09-15','08:00','America/Cuiaba',{'kind':'custom','mode':'monthday','monthday':10},NOW)
        self.assertEqual(value,ts('2026-10-10T08:00:00-04:00'))

    def test_every_fifteen_days(self):
        value,index=next_slot('2026-09-15','08:00','America/Cuiaba',{'kind':'custom','mode':'days','interval':15},ts('2026-09-30T08:01:00-04:00'))
        self.assertEqual((value,index),(ts('2026-10-15T08:00:00-04:00'),2))

    def test_end_date_inclusive_and_limit_include_first(self):
        rule={'kind':'daily','end_date':'2026-09-17','max_count':2}
        self.assertEqual(next_slot('2026-09-15','08:00','America/Cuiaba',rule,ts('2026-09-16T08:00:00-04:00'))[1],1)
        self.assertIsNone(next_slot('2026-09-15','08:00','America/Cuiaba',rule,ts('2026-09-16T08:00:01-04:00'))[0])

    def test_daily_years_later_no_future_materialization(self):
        value,index=next_slot('2026-09-15','08:00','America/Cuiaba',{'kind':'daily'},ts('2046-09-15T08:00:00-04:00'))
        self.assertEqual(value,ts('2046-09-15T08:00:00-04:00'))
        self.assertEqual(index,7305)

    def test_dst_gap_and_fold(self):
        self.assertEqual(slot('2026-03-08','02:30','America/New_York',{'kind':'none'},0),ts('2026-03-08T03:00:00-04:00'))
        self.assertEqual(slot('2026-11-01','01:30','America/New_York',{'kind':'none'},0),ts('2026-11-01T01:30:00-04:00'))


class ValidationTests(unittest.TestCase):
    def test_required_and_email_header_injection(self):
        for change in [{'name':''},{'email':''},{'email':'a@example.com\nBcc: evil@example.com'}, {'title':''}, {'start_date':''},{'clock':''}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                task_input(form(**change),'America/Cuiaba',NOW)

    def test_same_day_past_time_rejected(self):
        with self.assertRaises(ValueError): task_input(form(clock='07:59'),'America/Cuiaba',NOW)

    def test_unsafe_links_rejected_and_unc_allowed(self):
        for value in ['javascript:alert(1)','data:text/html,abc','https://user:pass@example.com','https://example.com\nX:1']:
            with self.subTest(value=value),self.assertRaises(ValueError): related_link('Link',value)
        unc=related_link('Pasta',r'\\servidor\pasta\arquivo com espaço.xlsx')
        self.assertEqual(unc['kind'],'path')
        self.assertTrue(unc['href'].startswith('file://servidor/pasta/'))
        self.assertEqual(related_link('Disco',r'F:\Documentos\Planilha.xlsx')['kind'],'path')

    def test_multiple_links_preserved(self):
        data=task_input(form(link_label=['Web','Rede'],link_value=['https://example.com',r'\\servidor\pasta']),'America/Cuiaba',NOW)
        self.assertEqual(len(data['links']),2)

    def test_invalid_custom_and_limits(self):
        for change in [{'kind':'custom','custom_mode':'weekdays','weekdays':[]},{'kind':'custom','custom_mode':'days','interval':'0'}, {'kind':'monthly','end_date':'2026-09-01'},{'max_count':'0'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):task_input(form(**change),'America/Cuiaba',NOW)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=Settings(root=Path(self.temp.name),password='test-secret-not-real')
        self.store=Store(self.settings.db_path)

    def tearDown(self): self.temp.cleanup()

    def create(self,owner=USER,**changes):
        data=task_input(form(**changes),'America/Cuiaba',NOW)
        return self.store.save(data,owner,now=NOW)

    def due(self,kind='none'):
        task_id=self.create(kind=kind)
        when=NOW+3600
        self.store.queue_due(when)
        return task_id,when,self.store.claim(when)

    def test_exact_one_reservation_concurrent(self):
        self.create()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:self.store.queue_due(NOW+3600),range(16)))
            claimed=list(pool.map(lambda _:self.store.claim(NOW+3600),range(16)))
        self.assertEqual(sum(x is not None for x in claimed),1)
        with self.store.db() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],1)

    def test_non_recurring_concludes_and_no_duplicate_after_restart(self):
        task_id,when,delivery=self.due()
        self.store.success(delivery,when)
        restarted=Store(self.settings.db_path)
        restarted.queue_due(when+100)
        self.assertIsNone(restarted.claim(when+100))
        task=restarted.get(task_id,USER)
        self.assertEqual((task['status'],task['send_count']),('CONCLUIDO',1))

    def test_monthly_advances_after_success(self):
        task_id,when,delivery=self.due('monthly')
        self.store.success(delivery,when)
        self.assertEqual(self.store.get(task_id,USER)['next_ts'],ts('2026-10-15T09:00:00-04:00'))

    def test_manual_idempotency_and_future_preserved(self):
        task_id=self.create(kind='daily')
        first=self.store.queue_manual(task_id,USER,'manual:abc',NOW,1)
        second=self.store.queue_manual(task_id,USER,'manual:abc',NOW,1)
        self.assertEqual(first,second)
        delivery=self.store.claim(NOW)
        self.store.success(delivery,NOW)
        task=self.store.get(task_id,USER)
        self.assertEqual((task['next_ts'],task['scheduled_count'],task['send_count']),(NOW+3600,0,1))

    def test_limit_not_consumed_by_manual(self):
        task_id=self.create(kind='daily',max_count='1')
        self.store.queue_manual(task_id,USER,'manual:x',NOW,1)
        self.store.success(self.store.claim(NOW),NOW)
        self.store.queue_due(NOW+3600)
        self.store.success(self.store.claim(NOW+3600),NOW+3600)
        task=self.store.get(task_id,USER)
        self.assertEqual((task['send_count'],task['status']),(2,'CONCLUIDO'))

    def test_late_single_send_and_skip_intervening(self):
        task_id=self.create(kind='daily')
        when=ts('2026-09-20T10:00:00-04:00')
        self.store.queue_due(when)
        self.store.success(self.store.claim(when),when)
        task=self.store.get(task_id,USER)
        self.assertEqual((task['send_count'],task['skipped_count']),(1,5))
        self.assertEqual(task['next_ts'],ts('2026-09-21T09:00:00-04:00'))

    def test_interrupted_sending_never_retried_automatically(self):
        task_id,when,delivery=self.due('daily')
        self.store.recover_interrupted(when+300)
        self.store.queue_due(when+300)
        self.assertIsNone(self.store.claim(when+300))
        with self.assertRaises(ValueError):self.store.resolve(delivery['id'],'retry',USER,when+300)
        self.store.resolve(delivery['id'],'confirm_sent',USER,when+300)
        self.assertEqual(self.store.get(task_id,USER)['send_count'],1)

    def test_retry_transient_three_then_stop(self):
        task_id,when,delivery=self.due('daily')
        self.store.failure(delivery,when,'temporário',transient=True)
        self.assertIsNone(self.store.claim(when+59))
        second=self.store.claim(when+60)
        self.store.failure(second,when+60,'temporário',transient=True)
        third=self.store.claim(when+360)
        self.store.failure(third,when+360,'temporário',transient=True)
        self.assertIsNone(self.store.claim(when+9999))
        self.assertEqual(self.store.pending(USER)[0]['state'],'ERROR')
        self.assertEqual(self.store.get(task_id,USER)['next_ts'],when)

    def test_pause_cancels_waiting_resume_future_only(self):
        task_id=self.create(kind='daily')
        self.store.queue_due(NOW+3600)
        self.store.change_status(task_id,'pause',USER,1,NOW+3601)
        self.assertIsNone(self.store.claim(NOW+3602))
        self.store.change_status(task_id,'resume',USER,2,NOW+86400+7200)
        self.assertEqual(self.store.get(task_id,USER)['next_ts'],ts('2026-09-17T09:00:00-04:00'))

    def test_edit_optimistic_lock_and_ownership(self):
        task_id=self.create()
        with self.assertRaises(LookupError):self.store.get(task_id,OTHER)
        data=task_input(form(title='Novo título'),'America/Cuiaba',NOW,self.store.get(task_id,USER))
        self.store.save(data,USER,task_id,1,NOW)
        with self.assertRaises(Conflict):self.store.save(data,USER,task_id,1,NOW)
        self.assertEqual(self.store.list_tasks(OTHER)[1],0)
        self.assertEqual(self.store.list_tasks(ADMIN)[1],1)

    def test_edit_cancels_old_payload_then_sends_new(self):
        task_id=self.create(kind='daily')
        self.store.queue_due(NOW+3600)
        old=self.store.get(task_id,USER)
        data=task_input(form(kind='daily',title='Alterado'),'America/Cuiaba',NOW+3601,old)
        self.store.save(data,USER,task_id,1,NOW+3601)
        self.store.queue_due(NOW+3601)
        delivery=self.store.claim(NOW+3601)
        self.assertEqual(delivery['payload']['title'],'Alterado')

    def test_sending_blocks_edit_cancel_and_pause(self):
        task_id,when,delivery=self.due()
        for action in ['pause','cancel']:
            with self.assertRaises(Conflict):self.store.change_status(task_id,action,USER,1,when)

    def test_cancel_preserves_history_and_historical_snapshot(self):
        task_id,when,delivery=self.due('daily')
        self.store.success(delivery,when)
        self.store.change_status(task_id,'cancel',USER,1,when+1)
        history,total=self.store.history(USER)
        self.assertEqual((total,history[0]['payload']['title']),(1,'Conferir planilha'))

    def test_discard_unknown_advances_without_sending(self):
        task_id,when,delivery=self.due('daily')
        self.store.recover_interrupted(when+1)
        self.store.resolve(delivery['id'],'discard',USER,when+2)
        task=self.store.get(task_id,USER)
        self.assertEqual((task['send_count'],task['skipped_count']),(0,1))
        self.assertGreater(task['next_ts'],when)

    def test_no_smtp_secret_no_transmission(self):
        self.create()
        calls=[]
        run_cycle(self.store,replace(self.settings,password=''),sender=lambda *a:calls.append(a),clock=lambda:NOW+3600)
        self.assertEqual(calls,[])
        self.assertFalse(self.store.worker_info()['smtp_ready'])

    def test_transaction_reservation_precedes_sender(self):
        self.create()
        calls=[]
        def sender(settings,delivery):
            with self.store.db() as con:self.assertEqual(con.execute('SELECT state FROM deliveries WHERE id=?',(delivery['id'],)).fetchone()[0],'SENDING')
            calls.append(delivery['id'])
        run_cycle(self.store,self.settings,sender=sender,clock=lambda:NOW+3600)
        run_cycle(self.store,self.settings,sender=sender,clock=lambda:NOW+3600)
        self.assertEqual(len(calls),1)

    def test_process_lock_excludes_another_open(self):
        lock=self.settings.data_dir/'test.lock'
        with ProcessLock(lock):
            with self.assertRaises(AlreadyRunning):
                with ProcessLock(lock):pass
        with ProcessLock(lock):pass

    def test_test_message_admin_only_and_history(self):
        with self.assertRaises(PermissionError):self.store.queue_test('pessoa@example.com',USER,'test:x',NOW,'America/Cuiaba')
        self.store.queue_test('pessoa@example.com',ADMIN,'test:x',NOW,'America/Cuiaba')
        self.store.success(self.store.claim(NOW),NOW)
        self.assertEqual(self.store.history(ADMIN)[0][0]['kind'],'TEST')

    def test_filters_and_metrics_owner_scope(self):
        self.create(owner=USER)
        self.create(owner=OTHER,title='Outra tarefa')
        self.assertEqual(self.store.list_tasks(ADMIN,{'q':'Outra'})[1],1)
        self.assertEqual(self.store.list_tasks(USER,{'email':'pessoa@','status':'ATIVO','kind':'none'})[1],1)
        self.assertEqual(self.store.dashboard(USER,NOW,Settings().zone)['active'],1)

    def test_manual_success_does_not_hide_scheduled_error(self):
        task_id,when,delivery=self.due('daily')
        self.store.failure(delivery,when,'Recusa de destinatário')
        self.store.queue_manual(task_id,USER,'manual:after-error',when+1,1)
        self.store.success(self.store.claim(when+1),when+1)
        self.assertEqual(self.store.get(task_id,USER)['last_error'],'Recusa de destinatário')
        self.assertEqual(self.store.dashboard(USER,when+1,Settings().zone)['errors'],1)


class FakeSMTP:
    def __init__(self, failure=None, code=250, close_error=False): self.failure=failure; self.code=code; self.close_error=close_error; self.tls=False
    def ehlo_or_helo_if_needed(self): pass
    def ehlo(self): pass
    def starttls(self,context): self.tls=True
    def login(self,user,password):
        if self.failure=='login':raise smtplib.SMTPAuthenticationError(535,b'password refused')
        if self.failure=='connect':raise OSError('offline')
    def mail(self,sender):return 250,b'ok'
    def rcpt(self,recipient):return (550,b'rejected') if self.failure=='recipient' else (250,b'ok')
    def data(self,data):
        if self.failure=='data':raise smtplib.SMTPServerDisconnected('lost after accept')
        if self.failure=='rejected':raise smtplib.SMTPDataError(451,b'temporary')
        return self.code,b'ok'
    def close(self):
        if self.close_error:raise OSError('connection closed')


class MailTests(unittest.TestCase):
    def setUp(self):
        self.settings=Settings(password='test-secret-not-real')
        self.delivery={'kind':'MANUAL','message_id':'<fixed@example.com>','payload':{'name':'Pessoa','email':'pessoa@example.com','title':'Teste <script>alert(1)</script>',
            'description':'Linha 1\nLinha 2','links':[related_link('Rede',r'\\server\share')],'scheduled_ts':NOW,'timezone':'America/Cuiaba'}}

    def test_message_html_escape_plaintext_and_identifier(self):
        msg=message_for(self.delivery)
        html=msg.get_body(('html',)).get_content()
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertIn('Explorador de Arquivos',html)
        self.assertIn('Linha 1',msg.get_body(('plain',)).get_content())
        self.assertEqual(msg['Message-ID'],'<fixed@example.com>')

    def test_accepted_then_close_error_is_success(self):
        send_email(self.settings,self.delivery,lambda:FakeSMTP(close_error=True))

    def test_starttls_applied(self):
        smtp=FakeSMTP()
        send_email(replace(self.settings,security='STARTTLS'),self.delivery,lambda:smtp)
        self.assertTrue(smtp.tls)

    def test_disconnect_data_is_uncertain_no_retry(self):
        with self.assertRaises(MailFailure) as result:send_email(self.settings,self.delivery,lambda:FakeSMTP('data'))
        self.assertTrue(result.exception.uncertain)
        self.assertFalse(result.exception.transient)

    def test_explicit_451_can_retry(self):
        with self.assertRaises(MailFailure) as result:send_email(self.settings,self.delivery,lambda:FakeSMTP('rejected'))
        self.assertFalse(result.exception.uncertain)
        self.assertTrue(result.exception.transient)

    def test_auth_and_recipient_errors_safe_permanent(self):
        for failure in ['login','recipient']:
            with self.subTest(failure=failure),self.assertRaises(MailFailure) as result:send_email(self.settings,self.delivery,lambda:FakeSMTP(failure))
            self.assertFalse(result.exception.uncertain)
            self.assertFalse(result.exception.transient)
            self.assertNotIn(self.settings.password,str(result.exception))

    def test_pre_data_network_error_can_retry(self):
        with self.assertRaises(MailFailure) as result:send_email(self.settings,self.delivery,lambda:FakeSMTP('connect'))
        self.assertTrue(result.exception.transient)
        self.assertFalse(result.exception.uncertain)


if __name__=='__main__':unittest.main()
