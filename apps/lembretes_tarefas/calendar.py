"""Calendário nacional de referência e complemento local, sem acesso à internet."""
from datetime import date, timedelta
from functools import lru_cache


def easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return date(year, n // 31, n % 31 + 1)


@lru_cache(maxsize=128)
def national_holidays(year):
    # Referência: calendário MGI de 2026; pontos facultativos não são incluídos.
    fixed = [(1, 1, 'Confraternização Universal'), (4, 21, 'Tiradentes'),
             (5, 1, 'Dia do Trabalho'), (9, 7, 'Independência do Brasil'),
             (10, 12, 'Nossa Senhora Aparecida'), (11, 2, 'Finados'),
             (11, 15, 'Proclamação da República'), (12, 25, 'Natal')]
    if year >= 2024:
        fixed.append((11, 20, 'Dia Nacional de Zumbi e da Consciência Negra'))
    result = {date(year, month, day).isoformat(): name for month, day, name in fixed}
    result[(easter(year) - timedelta(days=2)).isoformat()] = 'Paixão de Cristo'
    return result


class BusinessCalendar:
    def __init__(self, local=()):
        self.local = frozenset(local)

    def __contains__(self, day):
        year = date.fromisoformat(day).year
        return day in self.local or day in national_holidays(year) or day in sorriso_holidays(year)


def sorriso_holidays(year):
    # Prefeitura de Sorriso, Decreto 1.450/2026. Corpus Christi é ponto facultativo.
    return {date(year, 5, 13).isoformat(): 'Emancipação de Sorriso (MT)',
            date(year, 6, 29).isoformat(): 'São Pedro, padroeiro de Sorriso (MT)'}
