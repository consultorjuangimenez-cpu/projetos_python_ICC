import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client
from werkzeug.wrappers import Response

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apps.lembretes_tarefas.app import create_app
from apps.lembretes_tarefas.settings import Settings
from apps.lembretes_tarefas.store import Store
from test_core import form,ADMIN,USER,NOW
from apps.lembretes_tarefas.validation import task_input

REFERENCE=Path(os.environ.get('LEMBRETES_PORTAL_REFERENCIA',str(ROOT)))


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


@unittest.skipUnless((REFERENCE/'portal/acesso.py').exists(),'Defina LEMBRETES_PORTAL_REFERENCIA com a pasta do portal real para validar a integração.')
class PortalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=Settings(root=Path(self.temp.name))
        self.store=Store(self.settings.db_path)
        self.app=create_app(self.settings,self.store)
        access=module(REFERENCE/'portal/acesso.py','ref_access')
        usuarios=module(REFERENCE/'portal/usuarios.py','ref_users')
        self.users=usuarios.Usuarios(Path(self.temp.name)/'portal_dados')
        self.users.bootstrap('admin','Admin teste','teste123')
        self.users.save(None,'membro','Usuário teste','teste123',False,True,['/lembretes'],1)
        self.users.save(None,'negado','Sem permissão','teste123',False,True,[],1)
        self.portal=Flask('portal_test',template_folder=str(REFERENCE/'portal/templates'))
        access.configure_access(self.portal,[],{'/lembretes':self.app},self.users)
        self.client=Client(DispatcherMiddleware(self.portal,{'/lembretes':self.app}),Response)

    def tearDown(self):self.temp.cleanup()

    def login(self,user='admin'):
        page=self.client.get('/login')
        match=re.search(r'name="csrf_token" value="([^"]+)"',page.text)
        self.assertIsNotNone(match,page.text)
        result=self.client.post('/login',data={'csrf_token':match[1],'username':user,'password':'teste123'})
        self.assertEqual(result.status_code,302)

    def csrf(self,page):return re.search(r'name="csrf_token" value="([^"]+)"',page.text)[1]

    def test_anonymous_redirect_and_standalone_fail_closed(self):
        self.assertEqual(self.client.get('/lembretes/').location,'/login')
        standalone=create_app(self.settings,self.store).test_client()
        self.assertEqual(standalone.get('/').status_code,401)

    def test_permission_denied_at_direct_url(self):
        self.login('negado')
        self.assertEqual(self.client.get('/lembretes/').status_code,403)

    def test_csrf_is_required(self):
        self.login()
        response=self.client.post('/lembretes/nova',data=form())
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.store.list_tasks(ADMIN)[1],0)

    def test_all_screens_mount_and_no_double_prefix(self):
        self.login()
        task_id=self.store.save(task_input(form(),'America/Cuiaba',NOW),USER,now=NOW)
        for route in ['/','/nova',f'/tarefas/{task_id}',f'/tarefas/{task_id}/editar',f'/tarefas/{task_id}/acao/send','/historico','/teste-email','/colaboradores','/colaboradores/novo']:
            with self.subTest(route=route):
                page=self.client.get('/lembretes'+route)
                self.assertEqual(page.status_code,200,page.text)
                self.assertIn('/lembretes/static/app.css',page.text)
                self.assertNotIn('/lembretes/lembretes/',page.text)

    def test_form_post_and_multiple_links(self):
        self.login('membro')
        page=self.client.get('/lembretes/nova')
        future=time.time()+86400
        from datetime import datetime
        when=datetime.fromtimestamp(future,self.settings.zone)
        payload=form(start_date=when.date().isoformat(),clock=when.strftime('%H:%M'),link_label=['Rede','Site'],link_value=[r'\\servidor\pasta','https://example.com'])
        payload['csrf_token']=self.csrf(page)
        response=self.client.post('/lembretes/nova',data=payload)
        self.assertEqual(response.status_code,303,response.text)
        result=self.client.get(response.location)
        self.assertIn('Copiar caminho',result.text)
        self.assertEqual(self.store.list_tasks(USER)[1],1)

    def test_owner_isolation_and_test_admin_only(self):
        self.store.save(task_input(form(),'America/Cuiaba',NOW),ADMIN,now=NOW)
        self.login('membro')
        self.assertEqual(self.client.get('/lembretes/tarefas/1').status_code,404)
        self.assertEqual(self.client.get('/lembretes/teste-email').status_code,403)
        self.assertNotIn('Conferir planilha',self.client.get('/lembretes/').text)

    def test_manual_confirmation_post_replay(self):
        task_id=self.store.save(task_input(form(),'America/Cuiaba',NOW),USER,now=NOW)
        self.login('membro')
        page=self.client.get(f'/lembretes/tarefas/{task_id}/acao/send')
        token=re.search(r'name="action_token" value="([^"]+)"',page.text)[1]
        payload={'csrf_token':self.csrf(page),'action_token':token}
        for _ in range(2):self.assertEqual(self.client.post(f'/lembretes/tarefas/{task_id}/acao/send',data=payload).status_code,303)
        with self.store.db() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],1)

    def test_current_catalog_can_import_new_app(self):
        catalog=module(REFERENCE/'portal/catalogo.py','ref_catalog')
        path=Path(self.temp.name)/'aplicativos.json'
        path.write_text(json.dumps([{'nome':'Lembretes de Tarefas','rota':'/lembretes','modulo':'apps.lembretes_tarefas.app','ativo':True}]),encoding='utf-8')
        apps,mounts=catalog.carregar_aplicativos(path)
        self.assertTrue(callable(mounts['/lembretes']))

    def test_admin_creates_contact_with_csrf_and_edits(self):
        self.login()
        page=self.client.get('/lembretes/colaboradores/novo')
        data={'name':'Maria Teste','email':'maria@example.com','active':'1'}
        self.assertEqual(self.client.post('/lembretes/colaboradores/novo',data=data).status_code,400)
        data['csrf_token']=self.csrf(page)
        self.assertEqual(self.client.post('/lembretes/colaboradores/novo',data=data).status_code,303)
        contact=self.store.active_collaborators()[0]
        path=f"/lembretes/colaboradores/{contact['id']}/editar"
        page=self.client.get(path)
        data.update(csrf_token=self.csrf(page),revision='1',active='0')
        self.assertEqual(self.client.post(path,data=data).status_code,303)
        self.assertEqual(self.store.active_collaborators(),[])

    def test_member_reads_contacts_but_cannot_modify(self):
        contact_id=self.store.save_collaborator({'name':'Maria Teste','email':'maria@example.com'},ADMIN)
        self.login('membro')
        page=self.client.get('/lembretes/colaboradores')
        self.assertEqual(page.status_code,200)
        self.assertIn('maria@example.com',page.text)
        self.assertNotIn('Novo colaborador',page.text)
        token=self.csrf(self.client.get('/lembretes/nova'))
        for route in ['/colaboradores/novo',f'/colaboradores/{contact_id}/editar']:
            self.assertEqual(self.client.get('/lembretes'+route).status_code,403)
            self.assertEqual(self.client.post('/lembretes'+route,data={'csrf_token':token,'name':'Intruso','email':'intruso@example.com'}).status_code,403)
        self.assertEqual(self.store.get_collaborator(contact_id)['email'],'maria@example.com')

    def test_selection_prefills_on_server_and_escapes_option_data(self):
        name='</script><script>alert(1)</script>'
        contact_id=self.store.save_collaborator({'name':name,'email':'maria@example.com'},ADMIN)
        self.login('membro')
        page=self.client.get('/lembretes/nova')
        self.assertNotIn(name,page.text)
        self.assertIn('\\u003c/script\\u003e',page.text)
        from datetime import datetime
        when=datetime.fromtimestamp(time.time()+86400,self.settings.zone)
        data=form(name='',email='',collaborator_id=str(contact_id),start_date=when.date().isoformat(),clock=when.strftime('%H:%M'))
        data['csrf_token']=self.csrf(page)
        self.assertEqual(self.client.post('/lembretes/nova',data=data).status_code,303)
        task=self.store.list_tasks(USER)[0][0]
        self.assertEqual((task['name'],task['email']),(name,'maria@example.com'))


@unittest.skipUnless((REFERENCE/'portal/acesso.py').exists(),'Portal de referência ausente.')
class InstallerTests(unittest.TestCase):
    def test_preserves_existing_catalog_core_and_database_on_rerun(self):
        from shutil import copy2
        installer=module(ROOT/'ferramentas_lembretes/instalar.py','tested_installer')
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)
            (target/'portal').mkdir()
            for name in ['acesso.py','catalogo.py']:copy2(REFERENCE/'portal'/name,target/'portal'/name)
            (target/'servidor.py').write_text('ORIGINAL',encoding='utf-8')
            original=[{'nome':'Certificados atuais','rota':'/certificados','modulo':'apps.certificados.app','ativo':True}]
            (target/'aplicativos.json').write_text(json.dumps(original),encoding='utf-8')
            installer.install(target)
            data=target/'dados/apps/lembretes_tarefas'
            # Manter a conexão aberta para comprovar que o backup inclui o WAL.
            database=sqlite3.connect(data/'lembretes.sqlite3')
            self.addCleanup(database.close)
            database.execute('PRAGMA journal_mode=WAL')
            database.execute('PRAGMA wal_autocheckpoint=0')
            database.execute('CREATE TABLE preservar (valor TEXT)')
            database.execute("INSERT INTO preservar VALUES ('tarefa e histórico anteriores')")
            database.commit()
            self.assertTrue((data/'lembretes.sqlite3-wal').is_file())
            (data/'smtp_credencial.xml').write_bytes(b'CREDENCIAL_FICTICIA_NAO_ALTERAR')
            (data/'config.ini').write_text('[lembretes]\nsmtp_porta=587',encoding='utf-8')
            current=json.loads((target/'aplicativos.json').read_text(encoding='utf-8'))
            current[-1]['ativo']=False
            (target/'aplicativos.json').write_text(json.dumps(current),encoding='utf-8')
            backup=installer.install(target)
            actual=json.loads((target/'aplicativos.json').read_text(encoding='utf-8'))
            self.assertEqual(actual[0],original[0])
            self.assertEqual(len(actual),2)
            self.assertFalse(actual[-1]['ativo'])
            self.assertEqual((target/'servidor.py').read_text(),'ORIGINAL')
            self.assertEqual((target/'portal/acesso.py').read_bytes(),(REFERENCE/'portal/acesso.py').read_bytes())
            self.assertEqual(database.execute('SELECT valor FROM preservar').fetchone()[0],'tarefa e histórico anteriores')
            with sqlite3.connect(backup/'lembretes.sqlite3') as restored:
                self.assertEqual(restored.execute('SELECT valor FROM preservar').fetchone()[0],'tarefa e histórico anteriores')
            self.assertEqual((data/'smtp_credencial.xml').read_bytes(),b'CREDENCIAL_FICTICIA_NAO_ALTERAR')
            self.assertIn('587',(data/'config.ini').read_text())
            database.close()

    def test_conflicting_route_fails_without_catalog_mutation(self):
        from shutil import copy2
        installer=module(ROOT/'ferramentas_lembretes/instalar.py','conflict_installer')
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary);(target/'portal').mkdir()
            for name in ['acesso.py','catalogo.py']:copy2(REFERENCE/'portal'/name,target/'portal'/name)
            (target/'servidor.py').write_text('original')
            content=json.dumps([{'nome':'Outro','rota':'/lembretes','modulo':'apps.outro.app','ativo':True}])
            (target/'aplicativos.json').write_text(content)
            with self.assertRaises(ValueError):installer.install(target)
            self.assertEqual((target/'aplicativos.json').read_text(),content)


if __name__=='__main__':unittest.main()
