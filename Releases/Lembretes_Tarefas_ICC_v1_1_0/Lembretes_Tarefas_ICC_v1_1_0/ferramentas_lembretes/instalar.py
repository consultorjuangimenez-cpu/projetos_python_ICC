"""Adiciona somente este módulo ao catálogo real. Nunca substitui o portal."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid

PACKAGE = Path(__file__).resolve().parent.parent
ENTRY = {'nome':'Lembretes de Tarefas','descricao':'Agendamento e envio de lembretes por e-mail',
         'rota':'/lembretes','modulo':'apps.lembretes_tarefas.app','ativo':True}


def install(root):
    root = Path(root).resolve()
    if not all((root/p).is_file() for p in ['servidor.py','aplicativos.json','portal/catalogo.py','portal/acesso.py']):
        raise ValueError('A pasta informada não contém a estrutura esperada do Portal_Apps.')
    if root == PACKAGE:
        raise ValueError('Extraia o pacote fora da pasta do portal e execute novamente.')
    if os.name == 'nt':
        import ctypes
        if str(root).startswith('\\\\') or ctypes.windll.kernel32.GetDriveTypeW(root.anchor) == 4:
            raise ValueError('Instale no disco local do servidor. SQLite não deve ficar em compartilhamento de rede.')
    access = (root/'portal/acesso.py').read_text(encoding='utf-8-sig')
    catalog_code = (root/'portal/catalogo.py').read_text(encoding='utf-8-sig')
    if 'def configure_access(' not in access or 'g.usuario' not in access or 'csrf' not in access or 'import_module' not in catalog_code:
        raise ValueError('O padrão de autenticação/catálogo mudou. Envie esses dois arquivos para adaptar a integração.')
    catalog_path = root/'aplicativos.json'
    original = catalog_path.read_bytes()
    items = json.loads(original.decode('utf-8-sig'))
    if not isinstance(items,list) or any(not isinstance(item,dict) for item in items):
        raise ValueError('O catálogo deve conter uma lista de aplicativos.')
    matched = [item for item in items if item.get('modulo')==ENTRY['modulo'] or item.get('rota')==ENTRY['rota']]
    if any(item.get('modulo')!=ENTRY['modulo'] or item.get('rota')!=ENTRY['rota'] for item in matched) or len(matched)>1:
        raise ValueError('A rota /lembretes ou o módulo já existe com outro cadastro. Nenhum cadastro será substituído.')
    if not matched:
        items.append(ENTRY)
    # Se já existe, preservar nome, descrição, posição e escolha ativo/inativo.
    new_catalog = (json.dumps(items,ensure_ascii=False,indent=2)+'\n').encode('utf-8') if not matched else original
    sys.path.insert(0,str(PACKAGE))
    from apps.lembretes_tarefas.worker import ProcessLock, AlreadyRunning
    data = root/'dados/apps/lembretes_tarefas'
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    backup = root/'Releases/lembretes_tarefas'/stamp
    stage = root/'apps'/('.lembretes_stage_'+uuid.uuid4().hex)
    target = root/'apps/lembretes_tarefas'
    with ProcessLock(data/'agendador.lock'):
        backup.mkdir(parents=True)
        (backup/'aplicativos.json').write_bytes(original)
        # A API de backup inclui transações confirmadas que ainda estão no WAL.
        # Não copiar somente o arquivo .sqlite3 de uma base que já foi aberta.
        database = data/'lembretes.sqlite3'
        if database.exists():
            source_db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=20)
            backup_db = sqlite3.connect(backup/'lembretes.sqlite3', timeout=20)
            try:
                source_db.backup(backup_db)
                if backup_db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('O banco precisa ser verificado antes da atualização.')
            finally:
                source_db.close()
                backup_db.close()
        old_existed = target.exists()
        if old_existed:
            shutil.copytree(target,backup/'app_anterior',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(PACKAGE/'apps/lembretes_tarefas',stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        replaced = False
        try:
            if catalog_path.read_bytes()!=original:
                raise ValueError('O catálogo mudou durante a instalação. Execute novamente.')
            if old_existed:
                shutil.rmtree(target)
            stage.replace(target)
            replaced = True
            for source in (PACKAGE/'ferramentas_lembretes').iterdir():
                if source.is_file():
                    destination = root/'ferramentas_lembretes'/source.name
                    destination.parent.mkdir(exist_ok=True)
                    if destination.exists():
                        previous = backup/'ferramentas_lembretes'/source.name
                        previous.parent.mkdir(exist_ok=True)
                        shutil.copy2(destination,previous)
                    shutil.copy2(source,destination)
            shutil.copy2(PACKAGE/'requirements-lembretes.txt',root/'requirements-lembretes.txt')
            docs = root/'docs/lembretes_tarefas'
            docs.mkdir(parents=True,exist_ok=True)
            for name in ['LEIA-ME.md','docs/ARQUITETURA.md','docs/VALIDACAO.md']:
                source = PACKAGE/name
                if source.exists():
                    shutil.copy2(source,docs/source.name)
            if not (data/'config.ini').exists():
                shutil.copy2(PACKAGE/'apps/lembretes_tarefas/config.exemplo.ini',data/'config.ini')
            if catalog_path.read_bytes()!=original:
                raise ValueError('O catálogo mudou durante a cópia. Integração do aplicativo revertida.')
            with tempfile.NamedTemporaryFile(dir=root,prefix='lembretes_catalogo_',suffix='.tmp',delete=False) as out:
                temporary = Path(out.name)
                out.write(new_catalog)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary,catalog_path)
        except BaseException:
            if replaced and target.exists():
                shutil.rmtree(target)
            if replaced and old_existed:
                shutil.copytree(backup/'app_anterior',target)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        print('Integração concluída. Módulo: apps.lembretes_tarefas.app | Rota: /lembretes')
        print('Backup dos arquivos alterados: '+str(backup))
        print('Banco e credenciais existentes foram preservados. Reinicie o portal e o agendador para carregar esta versão.')
    return backup


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portal',required=True)
    args=parser.parse_args()
    try:
        install(args.portal)
    except Exception as exc:
        print(f'Instalação interrompida: {exc}',file=sys.stderr)
        raise SystemExit(1)
