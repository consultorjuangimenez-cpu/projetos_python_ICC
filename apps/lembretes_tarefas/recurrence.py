"""Recorrência calculada pela âncora original, sem materializar datas futuras."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KINDS = {'none': 'Não repetir', 'daily': 'Diariamente', 'weekly': 'Semanalmente',
         'monthly': 'Mensalmente', 'yearly': 'Anualmente', 'custom': 'Personalizado'}
WEEKDAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
BUSINESS_DAYS = {'keep': 'Manter', 'previous': 'Antecipar para dia útil', 'next': 'Postergar para dia útil'}


def business_date(day, policy='keep', holidays=()):
    if policy not in BUSINESS_DAYS:
        raise ValueError('Selecione uma regra válida para dias não úteis.')
    if policy == 'keep':
        return day
    step = timedelta(days=-1 if policy == 'previous' else 1)
    try:
        while day.weekday() >= 5 or day.isoformat() in holidays:
            day += step
    except OverflowError:
        raise ValueError('O ajuste de dia útil excede o calendário suportado.') from None
    return day


def integer(value, label, low, high):
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label}: informe um número inteiro.') from None
    if not low <= result <= high:
        raise ValueError(f'{label}: informe um valor de {low} a {high}.')
    return result


def parse_rule(form):
    kind = form.get('kind', 'none')
    if kind not in KINDS:
        raise ValueError('Selecione uma repetição válida.')
    rule = {'kind': kind}
    if kind == 'custom':
        mode = form.get('custom_mode', 'days')
        if mode not in {'days', 'weekdays', 'monthday'}:
            raise ValueError('Repetição personalizada inválida.')
        rule['mode'] = mode
        if mode == 'days':
            rule['interval'] = integer(form.get('interval'), 'Intervalo de dias', 1, 3650)
        elif mode == 'weekdays':
            values = form.getlist('weekdays') if hasattr(form, 'getlist') else form.get('weekdays', [])
            rule['weekdays'] = sorted({integer(x, 'Dia da semana', 0, 6) for x in values})
            if not rule['weekdays']:
                raise ValueError('Selecione pelo menos um dia da semana.')
        else:
            rule['monthday'] = integer(form.get('monthday'), 'Dia do mês', 1, 31)
    if form.get('end_date'):
        try:
            rule['end_date'] = date.fromisoformat(form['end_date']).isoformat()
        except ValueError:
            raise ValueError('Data de término inválida.') from None
    if form.get('max_count'):
        rule['max_count'] = integer(form['max_count'], 'Máximo de ocorrências', 1, 100000)
    return rule


def occurrence_date(start, rule, index):
    """Dia 31 usa o último dia do mês; 29/02 usa 28/02 em ano comum."""
    kind = rule['kind']
    if index < 0 or index >= rule.get('max_count', 100000):
        return None
    try:
        if kind == 'none':
            result = start if index == 0 else None
        elif kind in {'daily', 'weekly'} or (kind == 'custom' and rule['mode'] == 'days'):
            interval = 1 if kind == 'daily' else 7 if kind == 'weekly' else rule['interval']
            result = start + timedelta(days=index * interval)
        elif kind == 'custom' and rule['mode'] == 'weekdays':
            days = rule['weekdays']
            monday = start - timedelta(days=start.weekday())
            first = [d for d in days if d >= start.weekday()]
            if index < len(first):
                result = monday + timedelta(days=first[index])
            else:
                week, offset = divmod(index - len(first), len(days))
                result = monday + timedelta(days=7 * (week + 1) + days[offset])
        elif kind == 'yearly':
            year = start.year + index
            result = date(year, start.month, min(start.day, monthrange(year, start.month)[1]))
        else:
            day = rule.get('monthday', start.day)
            first_day = min(day, monthrange(start.year, start.month)[1])
            offset = int(kind == 'custom' and first_day < start.day)
            year, month0 = divmod(start.year * 12 + start.month - 1 + index + offset, 12)
            result = date(year, month0 + 1, min(day, monthrange(year, month0 + 1)[1]))
    except (ValueError, OverflowError):
        return None
    if result and rule.get('end_date') and result > date.fromisoformat(rule['end_date']):
        return None
    return result


def local_timestamp(day, clock, zone):
    naive = datetime.combine(day, time.fromisoformat(clock))
    # Horário inexistente no início do DST avança até o primeiro minuto válido.
    # Horário ambíguo usa a primeira ocorrência (fold=0).
    for minute in range(181):
        candidate = (naive + timedelta(minutes=minute)).replace(tzinfo=ZoneInfo(zone), fold=0)
        if candidate.astimezone(timezone.utc).astimezone(candidate.tzinfo).replace(tzinfo=None) == candidate.replace(tzinfo=None):
            return int(candidate.timestamp())
    raise ValueError('Não foi possível resolver o horário no fuso configurado.')


def slot(start_date, clock, zone, rule, index, policy='keep', holidays=()):
    day = occurrence_date(date.fromisoformat(start_date), rule, index)
    return local_timestamp(business_date(day, policy, holidays), clock, zone) if day else None


def next_slot(start_date, clock, zone, rule, after, minimum_index=0, policy='keep', holidays=()):
    """Primeira ocorrência >= after. Busca binária, inclusive após longas paradas."""
    low, high = minimum_index, rule.get('max_count', 100000)
    if rule['kind'] == 'none':
        high = min(high, 1)
    while low < high:
        mid = (low + high) // 2
        value = slot(start_date, clock, zone, rule, mid, policy, holidays)
        if value is None or value >= after:
            high = mid
        else:
            low = mid + 1
    value = slot(start_date, clock, zone, rule, low, policy, holidays)
    return (value, low) if value is not None and value >= after else (None, low)


def describe(rule):
    text = KINDS[rule['kind']]
    if rule['kind'] == 'custom':
        if rule['mode'] == 'days':
            text = f"A cada {rule['interval']} dia(s)"
        elif rule['mode'] == 'weekdays':
            text = ', '.join(WEEKDAYS[d] for d in rule['weekdays'])
        else:
            text = f"Dia {rule['monthday']} de cada mês"
    return text
