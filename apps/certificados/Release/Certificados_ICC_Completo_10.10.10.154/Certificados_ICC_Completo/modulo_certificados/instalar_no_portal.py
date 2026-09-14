"""Instala somente o novo módulo; preserva catálogo, configuração e dados existentes."""
from __future__ import annotations
import argparse
import ast
import json
import os
import shutil
import uuid
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

SOURCE=Path(__file__).resolve().parent
ENTRY={'nome':'Certificados digitais','descricao':'Painel, filtros, validade e instalação no Windows',
       'rota':'/certificados','modulo':'apps.certificados.app','ativo':True}


def install(target):
    target=Path(target).resolve()
    catalog=target/'aplicativos.json'; cfgfile=target/'config_apps.ini'
    for rel in ['servidor.py','portal/catalogo.py','portal/acesso.py','portal/usuarios.py','apps']:
        if not (target/rel).exists(): raise ValueError(f'Pasta do portal inválida: não foi encontrado {rel}.')
    items=json.loads(catalog.read_text(encoding='utf-8-sig'))
    if not isinstance(items,list): raise ValueError('aplicativos.json não contém uma lista.')
    matches=[i for i in items if i.get('rota')==ENTRY['rota'] or i.get('modulo')==ENTRY['modulo']]
    if any(i.get('rota')!=ENTRY['rota'] or i.get('modulo')!=ENTRY['modulo'] for i in matches) or len(matches)>1:
        raise ValueError('Já existe um aplicativo diferente usando esta rota ou módulo. Nada foi alterado.')
    if not matches: items.append(ENTRY.copy())
    for py in (SOURCE/'apps/certificados').rglob('*.py'): ast.parse(py.read_text(encoding='utf-8'),filename=str(py))
    original=cfgfile.read_text(encoding='utf-8-sig') if cfgfile.exists() else ''
    config=ConfigParser(interpolation=None); config.read_string(original)
    if not config.has_section('certificados_painel'):
        original += '\n\n[certificados_painel]\n; Caminhos herdados de [monitora_certificados], se existentes.\n'
        original += '; Se necessario, informe pasta_cpf e pasta_cnpj nesta secao.\n'
        original += 'dias_proximo = 30\nintervalo_segundos = 300\nrecursivo = false\n'
        original += 'estado_legado = C:\\C\\Projetos_Phyton\\Certificados Digitais\\Monitora Certificados\\estado_certificados.json\n'
        original += 'planilha_correcoes = \\\\srvprosoft\\g\\programas\\Relatorio_Certificados.xlsx\n'
        original += '; Exemplo: https://portal.icccontabilidade.com.br/certificados\nurl_publica =\n'
    # Prepara antes de tocar no portal. Não altera usuários, senhas ou outros módulos.
    key=datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    backup=target/'backups_atualizacao'/('certificados_'+key); backup.mkdir(parents=True)
    for f in [catalog,cfgfile]:
        if f.exists(): shutil.copy2(f,backup/f.name)
    destination=target/'apps/certificados'
    existed=destination.exists()
    if existed: shutil.copytree(destination,backup/'certificados')
    staged=target/'apps'/('certificados_preparacao_'+key)
    shutil.copytree(SOURCE/'apps/certificados',staged,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    old_cfg_exists=cfgfile.exists()
    try:
        if destination.exists(): shutil.rmtree(destination)
        staged.rename(destination)
        for path,text in [(catalog,json.dumps(items,ensure_ascii=False,indent=2)+'\n'),(cfgfile,original)]:
            temp=path.with_name(path.name+'.novo_'+key)
            temp.write_text(text,encoding='utf-8'); os.replace(temp,path)
    except Exception:
        if destination.exists(): shutil.rmtree(destination)
        if existed: shutil.copytree(backup/'certificados',destination)
        shutil.copy2(backup/catalog.name,catalog)
        if old_cfg_exists: shutil.copy2(backup/cfgfile.name,cfgfile)
        elif cfgfile.exists(): cfgfile.unlink()
        raise
    finally:
        if staged.exists(): shutil.rmtree(staged)
    print('INSTALADO: apps.certificados.app | rota /certificados')
    print('Backup:',backup)
    print('Reinicie o portal e libere Certificados digitais em Gerenciar usuarios.')
    print('Confira as pastas em config_apps.ini. Para instalar nas estacoes, configure HTTPS e url_publica.')
    return backup

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('portal',nargs='?');args=parser.parse_args()
    path=args.portal or input(r'Pasta do portal [C:\C\Projetos_Phyton\Portal_Apps]: ').strip() or r'C:\C\Projetos_Phyton\Portal_Apps'
    try: install(path)
    except Exception as exc:
        print('ERRO:',exc);raise SystemExit(1)
