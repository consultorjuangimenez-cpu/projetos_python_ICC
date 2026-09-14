"""Testes de regressão com certificados artificiais; não usa certificados da empresa."""
import io
import os
import json
import sys
import time
import zipfile
from datetime import timedelta
from pathlib import Path
import pytest
from flask import Flask
from werkzeug.test import Client
from werkzeug.wrappers import Response
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID,ObjectIdentifier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apps.certificados.core import Inventory,config,now,validade,digest
from apps.certificados.app import create_app


def pfx(path,days=90,password='1234',kind='CNPJ',start=-10,client='EMPRESA TESTE'):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,client+':12345678000190')])
    text='12345678000190' if kind=='CNPJ' else '01011990'+'12345678901'
    san=x509.OtherName(ObjectIdentifier('2.16.76.1.3.3' if kind=='CNPJ' else '2.16.76.1.3.1'),b'\x0c'+bytes([len(text)])+text.encode())
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now()+timedelta(days=start))
          .not_valid_after(now()+timedelta(days=days)).add_extension(x509.SubjectAlternativeName([san]),False).sign(key,hashes.SHA256()))
    data=pkcs12.serialize_key_and_certificates(b'teste',key,cert,None,serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption())
    path.write_bytes(data);return cert

@pytest.fixture
def inventory(tmp_path):
    for n in ['cnpj','cpf']: (tmp_path/n).mkdir()
    cfg=config(tmp_path)
    cfg.update(folders=[(tmp_path/'cnpj','CNPJ'),(tmp_path/'cpf','CPF')],data=tmp_path/'dados/apps/certificados',
               state=tmp_path/'legacy.json',sheet=tmp_path/'correcoes.xlsx',url='https://portal.test/certificados',interval=999999)
    return Inventory(cfg)


def populate(inv):
    root=inv.cfg['folders'][0][0]
    pfx(root/'CLIENTE SENHA 1234.pfx',days=90)
    pfx(root/'PERTO SENHA 1234.pfx',days=12)
    pfx(root/'VENCIDO SENHA 1234.pfx',days=-1)
    pfx(root/'FUTURO SENHA 1234.pfx',days=60,start=2)
    pfx(root/'ERRO SENHA errada.pfx',days=60)
    pfx(inv.cfg['folders'][1][0]/'PESSOA SENHA 1234.p12',days=45,kind='CPF')
    inv.scan();inv.last_started=time.time()


def test_read_counts_and_documents(inventory):
    populate(inventory); rows,c,meta=inventory.snapshot()
    assert c=={'valido':2,'proximo':1,'vencido':1,'erro':1,'futuro':1}
    assert next(r for r in rows if r['tipo']=='CPF')['documento']=='123.456.789-01'
    assert next(r for r in rows if r['tipo']=='CNPJ' and r['status']=='valido')['documento']=='12.345.678/0001-90'
    assert len(rows)==6 and all(p['acessivel'] for p in meta['pastas'])


def test_time_boundaries():
    t=now();row=dict(validacao='Sucesso',inicio=(t-timedelta(days=1)).isoformat())
    row['vencimento']=(t+timedelta(days=30)).isoformat();assert validade(row,t)==('proximo',30)
    row['vencimento']=(t+timedelta(days=30,seconds=1)).isoformat();assert validade(row,t)[0]=='valido'
    row['vencimento']=(t-timedelta(seconds=1)).isoformat();assert validade(row,t)[0]=='vencido'


def test_cache_removal_and_unavailable(inventory,monkeypatch):
    populate(inventory)
    def unexpected(*a,**kw): raise AssertionError('Não reabrir PKCS12 válido sem mudança')
    root=inventory.cfg['folders'][0][0]
    (root/'ERRO SENHA errada.pfx').unlink()
    monkeypatch.setattr(inventory,'_read',unexpected)
    inventory.scan();assert len(inventory.snapshot()[0])==5
    (root/'CLIENTE SENHA 1234.pfx').unlink();inventory.scan();assert len(inventory.snapshot()[0])==4
    root.rename(root.with_name('offline'));inventory.scan()
    rows,_,meta=inventory.snapshot();assert len(rows)==1 and rows[0]['tipo']=='CPF'
    assert not meta['pastas'][0]['acessivel']


def test_manual_password_and_no_plaintext(inventory):
    root=inventory.cfg['folders'][0][0];path=root/'CLIENTE SENHA errada.pfx'
    pfx(path,password='secreto-987!')
    inventory.scan();row=inventory.snapshot()[0][0];assert row['status']=='erro'
    with pytest.raises(ValueError): inventory.correct(row['id'],'nao-abre')
    inventory.correct(row['id'],'secreto-987!');inventory.scan()
    assert inventory.snapshot()[0][0]['status']=='valido'
    assert b'secreto-987!' not in inventory.path.read_bytes()
    assert 'senha_utilizada' not in json.dumps(inventory.snapshot())


def test_legacy_is_not_truth_and_preserves_password(inventory):
    root=inventory.cfg['folders'][0][0];path=root/'LEGADO.pfx';pfx(path,password='manual-x')
    inventory.cfg['state'].write_text(json.dumps({str(path):{'senha_manual_salva':'manual-x'},str(root/'REMOVIDO.pfx'):{'vencimento':'2099-01-01'}}))
    inventory.scan();rows,_,_=inventory.snapshot();assert len(rows)==1 and rows[0]['status']=='valido'
    inventory.cfg['state'].unlink();inventory.scan();assert inventory.snapshot()[0][0]['status']=='valido'


def test_no_stale_validity_after_change(inventory):
    populate(inventory);path=inventory.cfg['folders'][0][0]/'CLIENTE SENHA 1234.pfx';path.write_bytes(b'corrompido')
    inventory.scan();rows,_,_=inventory.snapshot();row=next(r for r in rows if r['id']==digest(str(path.resolve())))
    assert row['status']=='erro' and row['vencimento'] is None


def test_symlink_escape_ignored(inventory):
    root=inventory.cfg['folders'][0][0];outside=root.parent/'FORA SENHA 1234.pfx';pfx(outside)
    try: (root/'LINK SENHA 1234.pfx').symlink_to(outside)
    except OSError: pytest.skip('Ambiente sem symlink')
    inventory.scan();assert inventory.snapshot()[0]==[]

@pytest.fixture
def integration(inventory):
    # Use --portal-ref para o diretório de referência ou copie portal/ do portal real.
    reference=Path(os.environ.get('CERT_PORTAL_TEST_REF',str(Path(__file__).resolve().parents[3]/'test_portal')))
    if not reference.exists(): pytest.skip('Teste de integração exige referência local portal/acesso.py e usuarios.py.')
    sys.path.insert(0,str(reference))
    from portal.acesso import configure_access
    from portal.usuarios import Usuarios
    base=inventory.cfg['base']; users=Usuarios(base/'dados')
    users.bootstrap('admin','TI','test-password')
    users.save(None,'usuario','Usuário','test-password',False,True,['/certificados'],1)
    module=create_app(base,inventory); portal=Flask('testportal',template_folder=str(reference/'portal/templates'))
    portal.get('/')(lambda:'Portal')
    configure_access(portal,[dict(rota='/certificados',nome='Certificados')],{'/certificados':module},users,True)
    client=Client(DispatcherMiddleware(portal,{'/certificados':module}),Response)
    populate(inventory)
    def login(username='admin'):
        response=client.get('/login',base_url='https://portal.test')
        import re
        csrf=re.search(r'name="csrf_token" value="([^"]+)"',response.text).group(1)
        res=client.post('/login',data={'username':username,'password':'test-password','csrf_token':csrf},base_url='https://portal.test')
        assert res.status_code==302
        response=client.get('/certificados/',base_url='https://portal.test')
        csrf=re.search(r'name="csrf-token" content="([^"]+)"',response.text).group(1)
        return csrf
    return client,login,inventory,users


def test_auth_csrf_export_and_helper(integration):
    client,login,inv,users=integration
    assert client.get('/certificados/api/dados',base_url='https://portal.test').status_code==401
    csrf=login('usuario');headers={'X-CSRF-Token':csrf}
    assert client.post('/certificados/api/atualizar',json={},base_url='https://portal.test').status_code==400
    data=client.get('/certificados/api/dados',base_url='https://portal.test').json
    assert data['instalacao_https'] is True
    r=next(r for r in data['certificados'] if r['status']=='valido')
    detail=client.get('/certificados/api/certificados/'+r['id'],base_url='https://portal.test').json
    assert 'caminho' not in detail and 'arquivo_original' not in detail
    assert client.get('/certificados/auxiliar.zip',base_url='https://portal.test').status_code==403
    res=client.post('/certificados/api/exportar',json={'ids':[r['id']]},headers=headers,base_url='https://portal.test')
    assert res.status_code==200
    from openpyxl import load_workbook
    ws=load_workbook(io.BytesIO(res.data)).active
    assert ws.max_row==6 and ws['C6'].value==r['documento']


def request_install(client,csrf,inv):
    cert=next(r for r in inv.snapshot()[0] if r['status']=='valido')
    res=client.post('/certificados/api/instalar/'+cert['id'],json={},headers={'X-CSRF-Token':csrf},base_url='https://portal.test')
    assert res.status_code==200,res.text
    return res.json


def test_single_use_ticket_and_callback(integration):
    client,login,inv,users=integration;csrf=login();ticket=request_install(client,csrf,inv)
    payload={'token':ticket['uri'].rsplit('/',1)[-1],'maquina':'TESTE-PC'}
    agent=Client(client.application,Response)
    res=agent.post('/certificados/agente-api/resgatar',json=payload,base_url='https://portal.test')
    assert res.status_code==200,res.text
    data=res.json
    assert agent.post('/certificados/agente-api/resgatar',json=payload,base_url='https://portal.test').status_code==410
    assert agent.post('/certificados/agente-api/resultado',json={'callback':data['callback'],'estado':'instalado'},base_url='https://portal.test').status_code==200
    assert agent.post('/certificados/agente-api/resultado',json={'callback':data['callback'],'estado':'instalado'},base_url='https://portal.test').status_code==410
    assert client.get('/certificados/api/instalacao/'+ticket['id'],base_url='https://portal.test').json['estado']=='instalado'


def test_revoked_session_blocks_ticket(integration):
    client,login,inv,users=integration;csrf=login('usuario');ticket=request_install(client,csrf,inv)
    users.save(2,'usuario','Usuário','',False,True,[],1)
    res=client.post('/certificados/agente-api/resgatar',json={'token':ticket['uri'].rsplit('/',1)[-1],'maquina':'TESTE-PC'},base_url='https://portal.test')
    assert res.status_code==403


def test_expired_ticket_and_changed_file(integration):
    client,login,inv,users=integration;csrf=login();ticket=request_install(client,csrf,inv)
    with inv.db() as db: db.execute('UPDATE tickets SET expires=?',(time.time()-1,))
    res=client.post('/certificados/agente-api/resgatar',json={'token':ticket['uri'].rsplit('/',1)[-1],'maquina':'TESTE-PC'},base_url='https://portal.test')
    assert res.status_code==410
    ticket=request_install(client,csrf,inv)
    cert=next(r for r in inv.snapshot()[0] if r['status']=='valido')
    _,path,_=inv.get_file(cert['id']);path.write_bytes(b'trocado')
    res=client.post('/certificados/agente-api/resgatar',json={'token':ticket['uri'].rsplit('/',1)[-1],'maquina':'TESTE-PC'},base_url='https://portal.test')
    assert res.status_code==409


def test_http_bridge_rejected(integration):
    client,login,inv,users=integration
    res=client.post('/certificados/agente-api/resgatar',json={'token':'A'*43,'maquina':'TESTE-PC'},base_url='http://portal.test')
    assert res.status_code==403


def test_installer_backup_and_idempotency(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('installer',ROOT/'instalar_no_portal.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    portal=tmp_path/'portal';(portal/'portal').mkdir(parents=True);(portal/'apps').mkdir()
    for rel in ['servidor.py','portal/catalogo.py','portal/acesso.py','portal/usuarios.py']:(portal/rel).write_text('# referência')
    old=[dict(nome='Outro aplicativo',rota='/outro',modulo='apps.outro.app',ativo=True)]
    (portal/'aplicativos.json').write_text(json.dumps(old))
    oldcfg='[monitora_certificados]\npasta_cpf = teste\n';(portal/'config_apps.ini').write_text(oldcfg)
    b=mod.install(portal)
    assert json.loads((b/'aplicativos.json').read_text())==old
    current=json.loads((portal/'aplicativos.json').read_text());assert current[0]==old[0] and len(current)==2
    assert (portal/'config_apps.ini').read_text().startswith(oldcfg)
    mod.install(portal);assert len(json.loads((portal/'aplicativos.json').read_text()))==2
    assert (portal/'config_apps.ini').read_text().count('[certificados_painel]')==1
