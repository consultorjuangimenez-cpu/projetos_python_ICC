"""Cadastro local, editado pela TI. Carrega apenas módulos explicitamente registrados."""
import importlib
import json
import re


def carregar_aplicativos(path):
    items = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(items, list):
        raise ValueError('aplicativos.json deve conter uma lista.')
    active, mounts = [], {}
    for item in items:
        if not isinstance(item, dict) or type(item.get('ativo', True)) is not bool:
            raise ValueError('Cadastro inválido em aplicativos.json.')
        if not item.get('ativo', True):
            continue
        route = item.get('rota', '')
        module = item.get('modulo', '')
        if not re.fullmatch(r'/[a-z][a-z0-9-]*', route) or route in mounts or route in {'/saude','/login','/sair','/admin','/minha-senha','/static'}:
            raise ValueError(f'Rota inválida, reservada ou repetida: {route}')
        if not re.fullmatch(r'apps\.[a-z][a-z0-9_]*\.app', module):
            raise ValueError(f'Módulo inválido: {module}')
        if not isinstance(item.get('nome'), str) or not item['nome'].strip():
            raise ValueError('Informe o nome do aplicativo.')
        application = getattr(importlib.import_module(module), 'app', None)
        if not callable(application):
            raise ValueError(f'{module} não fornece uma aplicação WSGI chamada app.')
        active.append({**item, 'descricao': str(item.get('descricao', ''))})
        mounts[route] = application
    if not active:
        raise ValueError('Cadastre pelo menos um aplicativo ativo.')
    return active, mounts
