"""Acrescenta o cadastro/configuração dos novos apps sem substituir os existentes."""
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path
import io
import json
import os
import re
import shutil
import uuid


def pacote(nome):
    match = re.match(r'\s*([A-Za-z0-9_.-]+)', nome)
    return re.sub(r'[-_.]+', '-', match.group(1)).lower() if match else None


def aplicar(base):
    base = Path(base).resolve()
    if not (base/'servidor.py').is_file() or not (base/'portal/acesso.py').is_file():
        raise ValueError('Copie o conteúdo da atualização para a raiz do portal COM LOGIN, junto de servidor.py.')
    for name in ('config.ini', 'aplicativos.json', 'requirements.txt', 'novos_aplicativos.json', 'config_apps.novos.ini', 'requirements_novos.txt'):
        if not (base/name).is_file():
            raise ValueError(f'Arquivo necessário não encontrado: {name}')

    atuais = json.loads((base/'aplicativos.json').read_text(encoding='utf-8-sig'))
    novos = json.loads((base/'novos_aplicativos.json').read_text(encoding='utf-8-sig'))
    if not isinstance(atuais, list) or not isinstance(novos, list):
        raise ValueError('Os cadastros de aplicativos devem conter listas JSON.')
    rotas, modulos = {}, {}
    for item in atuais:
        if not isinstance(item, dict) or not item.get('rota') or not item.get('modulo'):
            raise ValueError('Existe uma entrada inválida no cadastro atual.')
        if item['rota'] in rotas or item['modulo'] in modulos:
            raise ValueError('O cadastro atual contém rota ou módulo repetido. Corrija antes de atualizar.')
        rotas[item['rota']], modulos[item['modulo']] = item, item
    cadastro = list(atuais)
    adicionados = []
    for item in novos:
        modulo = item['modulo']
        if not re.fullmatch(r'apps\.[a-z][a-z0-9_]*\.app', modulo):
            raise ValueError('Módulo inválido no pacote de atualização.')
        if not (base.joinpath(*modulo.split('.')).with_suffix('.py')).is_file():
            raise ValueError(f'A pasta de {item["nome"]} não foi copiada corretamente.')
        por_rota, por_modulo = rotas.get(item['rota']), modulos.get(modulo)
        if por_rota or por_modulo:
            if por_rota and por_modulo and por_rota is por_modulo:
                continue  # Mantém nome, ativo e demais configurações já existentes.
            raise ValueError(f'Conflito no cadastro de {item["nome"]}: rota ou módulo já usado por outro cadastro. Nenhum cadastro foi alterado.')
        cadastro.append(item)
        rotas[item['rota']] = modulos[modulo] = item
        adicionados.append(item['nome'])

    atual = ConfigParser(interpolation=None)
    if (base/'config_apps.ini').exists():
        atual.read(base/'config_apps.ini', encoding='utf-8-sig')
    exemplo = ConfigParser(interpolation=None)
    exemplo.read(base/'config_apps.novos.ini', encoding='utf-8-sig')
    novas_config = 0
    for section in exemplo.sections():
        if not atual.has_section(section):
            atual.add_section(section)
        for key, value in exemplo.items(section):
            if not atual.has_option(section, key):
                atual.set(section, key, value)
                novas_config += 1

    requirements = (base/'requirements.txt').read_text(encoding='utf-8-sig')
    existentes = {pacote(line) for line in requirements.splitlines() if line.strip() and not line.lstrip().startswith(('#','-'))}
    extras = []
    for line in (base/'requirements_novos.txt').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if pacote(line) not in existentes:
            extras.append(line)
            existentes.add(pacote(line))

    alteracoes = {}
    if adicionados:
        alteracoes['aplicativos.json'] = json.dumps(cadastro, ensure_ascii=False, indent=2)+'\n'
    if novas_config or not (base/'config_apps.ini').exists():
        buf = io.StringIO()
        atual.write(buf)
        alteracoes['config_apps.ini'] = buf.getvalue()
    if extras:
        alteracoes['requirements.txt'] = requirements.rstrip()+'\n'+'\n'.join(extras)+'\n'

    if alteracoes:
        backup = base/'backups_atualizacao'/('cadastro_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True)
        originais = {}
        escritos = []
        for name in alteracoes:
            file = base/name
            originais[name] = file.read_bytes() if file.exists() else None
            if file.exists():
                shutil.copy2(file, backup/name)
        (backup/'ARQUIVOS_NOVOS.txt').write_text('\n'.join(name for name, data in originais.items() if data is None), encoding='utf-8')
        try:
            for name, text in alteracoes.items():
                file = base/name
                temp = file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    temp.write_text(text, encoding='utf-8')
                    os.replace(temp, file)
                    escritos.append(name)
                finally:
                    temp.unlink(missing_ok=True)
        except Exception:
            for name in escritos:
                if originais[name] is None:
                    (base/name).unlink(missing_ok=True)
                else:
                    (base/name).write_bytes(originais[name])
            raise
        print('Backup dos cadastros: '+str(backup))
    print(f'Aplicativos acrescentados: {len(adicionados)}.')
    for name in adicionados:
        print('  '+name)
    print('Cadastros existentes, config.ini e dados/ preservados.')
    print('Confira os caminhos em config_apps.ini antes de iniciar.')
    print('Senhas aceitas: 4 a 128 caracteres, incluindo 1234. Senhas atuais não foram trocadas.')
    return adicionados


if __name__ == '__main__':
    try:
        aplicar(Path(__file__).resolve().parent.parent)
    except Exception as exc:
        print('ERRO: '+str(exc))
        raise SystemExit(1)
