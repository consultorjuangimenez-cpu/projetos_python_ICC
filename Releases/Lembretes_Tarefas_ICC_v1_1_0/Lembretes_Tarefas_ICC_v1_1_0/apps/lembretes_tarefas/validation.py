import json
import re
import unicodedata
from datetime import date, time
from urllib.parse import quote, urlsplit
from .recurrence import parse_rule, next_slot, local_timestamp, integer


def search_key(value):
    text = unicodedata.normalize('NFKD', ' '.join(value.split()).casefold())
    return ''.join(c for c in text if not unicodedata.combining(c))


def collaborator_input(form):
    name = ' '.join(form.get('name', '').split())
    if not name or len(name) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in form.get('name', '')):
        raise ValueError('Informe o nome do colaborador com até 120 caracteres.')
    address = email(form.get('email', ''))
    active = form.get('active', '1')
    if active not in {'0', '1'}:
        raise ValueError('Selecione uma situação válida para o colaborador.')
    return {'name': name, 'name_key': search_key(name), 'email': address,
            'email_key': address.casefold(), 'active': int(active)}


def email(value):
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise ValueError('Informe um único endereço de e-mail válido, sem nome ou separadores.')
    labels = value.rsplit('@', 1)[1].split('.')
    if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in labels):
        raise ValueError('Domínio de e-mail inválido.')
    return value


def related_link(label, value):
    label, value = label.strip(), value.strip()
    if not label and not value:
        return None
    if not label or len(label) > 150 or not value or len(value) > 2048:
        raise ValueError('Cada link precisa de descrição (até 150 caracteres) e endereço (até 2048).')
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('O endereço de um link contém caracteres inválidos.')
    if value.startswith('\\\\'):
        parts = [p for p in value[2:].split('\\') if p]
        if len(parts) < 2 or any(c in value for c in ['<', '>', '"', '|', '*', '?']):
            raise ValueError('Caminho UNC inválido. Exemplo: \\\\servidor\\pasta\\arquivo.xlsx')
        href = 'file://' + '/'.join(quote(p, safe='') for p in parts)
        kind = 'path'
    elif re.match(r'^[A-Za-z]:[\\/]', value):
        href = 'file:///' + quote(value.replace('\\', '/'), safe='/:')
        kind = 'path'
    else:
        try:
            parsed = urlsplit(value)
            parsed.port
            if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value) or '\\' in value:
                raise ValueError()
        except ValueError:
            raise ValueError('Use uma URL http/https ou um caminho Windows/UNC válido.') from None
        href, kind = value, 'web'
    return {'label': label, 'value': value, 'href': href, 'kind': kind}


def task_input(form, zone, now, old=None):
    name, title = form.get('name', '').strip(), form.get('title', '').strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError('Informe o nome do colaborador com até 120 caracteres.')
    if not title or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise ValueError('Informe o título da tarefa com até 200 caracteres.')
    description = form.get('description', '').strip()
    if len(description) > 10000:
        raise ValueError('A descrição deve ter até 10.000 caracteres.')
    try:
        start = date.fromisoformat(form.get('start_date', '')).isoformat()
        clock = time.fromisoformat(form.get('clock', ''))
        if clock.tzinfo or clock.second or clock.microsecond:
            raise ValueError()
        clock = clock.strftime('%H:%M')
    except ValueError:
        raise ValueError('Informe data e horário válidos, com hora e minuto.') from None
    rule = parse_rule(form)
    if rule.get('end_date') and rule['end_date'] < start:
        raise ValueError('O término deve ser igual ou posterior à primeira data.')
    labels, values = form.getlist('link_label'), form.getlist('link_value')
    if len(labels) != len(values) or len(labels) > 20:
        raise ValueError('Informe até 20 links, cada um com descrição e endereço.')
    links = [link for label, value in zip(labels, values) if (link := related_link(label, value))]
    unchanged = old and (old['start_date'], old['clock'], old['rule'], old['timezone']) == (start, clock, rule, zone)
    first, idx = next_slot(start, clock, zone, rule, 0)
    if not unchanged:
        if local_timestamp(date.fromisoformat(start), clock, zone) < now:
            raise ValueError('A primeira data e horário devem estar no futuro. Ajuste também o horário do lembrete.')
        if first is None:
            raise ValueError('A regra não tem ocorrências dentro do período informado.')
    collaborator_id = integer(form['collaborator_id'], 'Colaborador', 1, 2147483647) if form.get('collaborator_id') else None
    return {'name': name, 'email': email(form.get('email', '')), 'title': title,
            'collaborator_id': collaborator_id,
            'description': description, 'links': links, 'start_date': start, 'clock': clock,
            'rule': rule, 'timezone': zone, 'next_ts': old['next_ts'] if unchanged else first,
            'next_index': old['next_index'] if unchanged else idx, 'schedule_changed': not unchanged}
