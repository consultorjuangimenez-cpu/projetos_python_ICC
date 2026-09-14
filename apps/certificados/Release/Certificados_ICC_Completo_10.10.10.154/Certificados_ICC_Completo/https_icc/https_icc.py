"""Complemento HTTPS para o Portal_Apps de 10.10.10.154. Execute na pasta https_icc."""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
import zipfile
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

HERE=Path(__file__).resolve().parent
PORTAL=HERE.parent
IP='10.10.10.154'
URL='https://'+IP


def set_option(text,section,key,value):
    """Altera uma chave, preservando as outras linhas do INI."""
    parser=ConfigParser(interpolation=None);parser.read_string(text)
    lines=text.splitlines(keepends=True)
    headers=[(i,m.group(1).strip()) for i,line in enumerate(lines)
             if (m:=re.match(r'^\s*\[([^\]]+)\]\s*(?:[;#].*)?$',line.strip()))]
    found=next(((i,name) for i,name in headers if name==section),None)
    if found is None:
        return text.rstrip()+'\n\n['+section+']\n'+key+' = '+value+'\n'
    start=found[0];end=next((i for i,_ in headers if i>start),len(lines))
    for i in range(start+1,end):
        if re.match(r'^\s*'+re.escape(key)+r'\s*[:=]',lines[i],re.I):
            lines[i]=key+' = '+value+'\n'
            return ''.join(lines)
    lines.insert(end,key+' = '+value+'\n')
    if end>0 and not lines[end-1].endswith('\n'): lines[end-1]+='\n'
    return ''.join(lines)


def ensure_portal():
    for name in ['servidor.py','config.ini','config_apps.ini','portal/servidor.py','apps/certificados/app.py']:
        if not (PORTAL/name).is_file():
            raise RuntimeError('Extraia esta pasta como Portal_Apps\\https_icc e instale primeiro o modulo Certificados digitais. Falta: '+name)
    if not (HERE/'caddy.exe').is_file():
        raise RuntimeError('Baixe o Caddy para Windows amd64 em https://caddyserver.com/download e salve como https_icc\\caddy.exe.')


def caddy_config():
    storage=json.dumps((PORTAL/'dados/caddy_https').as_posix(),ensure_ascii=False)
    return '''{
    admin off
    auto_https disable_redirects
    skip_install_trust
    default_sni 10.10.10.154
    storage file_system STORAGE
    servers {
        protocols h1 h2
    }
}

https://10.10.10.154 {
    bind 10.10.10.154
    tls internal
    reverse_proxy 127.0.0.1:8081 {
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host 10.10.10.154
        header_up X-Forwarded-Port 443
    }
}
'''.replace('STORAGE',storage)


def configure():
    ensure_portal()
    # adapt valida a configuracao sem iniciar listeners nem alterar confianca TLS.
    staged=HERE/'Caddyfile.preparacao'
    staged.write_text(caddy_config(),encoding='utf-8')
    try:
        result=subprocess.run([str(HERE/'caddy.exe'),'adapt','--config',str(staged),'--adapter','caddyfile'],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('Caddy recusou a configuracao. Nenhum INI foi alterado.\n'+result.stderr)
        a=PORTAL/'config.ini';b=PORTAL/'config_apps.ini'
        original={a:a.read_bytes(),b:b.read_bytes()}
        changed={a:set_option(original[a].decode('utf-8-sig'),'seguranca','cookie_https','true'),
                 b:set_option(original[b].decode('utf-8-sig'),'certificados_painel','url_publica',URL+'/certificados')}
        for text in changed.values():
            check=ConfigParser(interpolation=None);check.read_string(text)
        backup=PORTAL/'backups_atualizacao'/('https_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
        backup.mkdir(parents=True)
        for path in original:shutil.copy2(path,backup/path.name)
        if (HERE/'Caddyfile').exists():shutil.copy2(HERE/'Caddyfile',backup/'Caddyfile')
        try:
            for path,text in changed.items():
                temp=path.with_name(path.name+'.https_tmp');temp.write_text(text,encoding='utf-8');os.replace(temp,path)
            os.replace(staged,HERE/'Caddyfile')
        except Exception:
            for path,data in original.items():path.write_bytes(data)
            raise
        print('Configurado para '+URL+'/')
        print('Backup dos INIs: '+str(backup))
        print('Agora use 2_INICIAR_HTTPS.bat. O login passa a exigir HTTPS.')
    finally:
        if staged.exists():staged.unlink()


def export_trust():
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    root=PORTAL/'dados/caddy_https/pki/authorities/local/root.crt'
    if not root.is_file():raise RuntimeError('Raiz ainda nao gerada. Inicie o HTTPS e tente novamente em alguns segundos.')
    cert=x509.load_pem_x509_certificate(root.read_bytes())
    der=cert.public_bytes(serialization.Encoding.DER)
    fingerprint=hashlib.sha256(der).hexdigest().upper()
    destination=HERE/'distribuir';destination.mkdir(exist_ok=True)
    helper=PORTAL/'apps/certificados/auxiliar'
    required=['Auxiliar.ps1','Configurar.ps1','Remover.ps1']
    for name in required:
        if not (helper/name).is_file():raise RuntimeError('Auxiliar nao encontrado: '+name+'. Confira o modulo de certificados instalado.')
    bat=(HERE/'estacao/INSTALAR_NESTE_COMPUTADOR.bat').read_text(encoding='ascii').replace('__SHA256__',fingerprint)
    instructions=f"""PREPARAR ESTACAO ICC - {URL}
1. Extraia este ZIP inteiro em uma pasta.
2. Execute INSTALAR_NESTE_COMPUTADOR.bat no usuario que utilizara o portal.
3. Se o Windows solicitar confirmacao de confianca, confira a procedencia com a TI.
4. Entre no portal com seu login e use o botao INSTALAR do certificado desejado.

O BAT instala a confianca HTTPS no usuario atual e configura o Auxiliar ICC.
Nao exige Python nem execucao como outro administrador. Repita para cada usuario do Windows.
Ele confere o SHA256 do certificado antes de importar:
{fingerprint}

A TI deve conferir esse valor com o exibido no servidor e entregar este pacote por um meio controlado.
A raiz importada e da autoridade HTTPS interna, nao e um certificado A1 de cliente.
Nao distribua chaves privadas nem a pasta dados/caddy_https.
Se os scripts forem bloqueados, a TI deve conferir a procedencia e a politica de assinatura.
Se houver a opcao Desbloquear nas propriedades do ZIP, a TI pode desbloquear antes de extrair.
Nao altere as politicas da empresa para executar este pacote.
"""
    with zipfile.ZipFile(destination/'Preparar_Estacao_ICC.zip','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('ICC-HTTPS.cer',der)
        z.writestr('LEIA_PRIMEIRO.txt',instructions.encode('utf-8-sig'))
        z.writestr('INSTALAR_NESTE_COMPUTADOR.bat',bat.replace('\n','\r\n').encode('ascii'))
        z.writestr('config.json',json.dumps({'url':URL+'/certificados'},indent=2))
        for name in required:z.write(helper/name,name)
    print('SHA256 para conferir nas estacoes: '+fingerprint)
    print('Distribua somente: '+str(destination/'Preparar_Estacao_ICC.zip'))


def run():
    ensure_portal()
    if not (HERE/'Caddyfile').is_file():raise RuntimeError('Execute primeiro 1_CONFIGURAR_HTTPS.bat.')
    # Exige parada do portal antigo; evita uso simultaneo de sessoes HTTP e HTTPS.
    with socket.socket() as s:
        s.settimeout(.5)
        if s.connect_ex(('127.0.0.1',8080))==0:
            raise RuntimeError('O portal antigo ainda esta na porta 8080. Encerre-o antes de iniciar HTTPS.')
    for host,port in [(IP,443),('127.0.0.1',8081)]:
        with socket.socket() as s:
            try:s.bind((host,port))
            except OSError:raise RuntimeError(f'Nao foi possivel usar {host}:{port}. Confira IP e processo ocupando a porta.')
    processes=[]
    logs=HERE/'logs';logs.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    env=os.environ.copy();env['PYTHONPATH']=str(PORTAL)+os.pathsep+env.get('PYTHONPATH','')
    try:
        with (logs/f'python_{stamp}.log').open('ab') as pylog,(logs/f'caddy_{stamp}.log').open('ab') as clog:
            backend=subprocess.Popen([sys.executable,'-u',str(HERE/'backend.py')],cwd=PORTAL,env=env,stdout=pylog,stderr=subprocess.STDOUT)
            processes.append(backend)
            proxy=subprocess.Popen([str(HERE/'caddy.exe'),'run','--config',str(HERE/'Caddyfile'),'--adapter','caddyfile'],cwd=HERE,stdout=clog,stderr=subprocess.STDOUT)
            processes.append(proxy)
            print('Iniciando portal em '+URL+'/')
            print('Mantenha esta janela aberta. CTRL+C encerra ambos os processos.')
            print('Logs: '+str(logs))
            print('Na primeira execucao, use 3_EXPORTAR_CONFIANCA.bat em outra janela.')
            while all(p.poll() is None for p in processes):time.sleep(.5)
            raise RuntimeError('Um processo encerrou. Confira os logs acima; o outro sera encerrado tambem.')
    except KeyboardInterrupt: print('\nEncerrando portal HTTPS.')
    finally:
        for p in reversed(processes):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=8)
                except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('acao',choices=['configurar','iniciar','exportar']);a=p.parse_args()
    try:{'configurar':configure,'iniciar':run,'exportar':export_trust}[a.acao]()
    except Exception as exc:print('ERRO:',exc);sys.exit(1)
