from configparser import ConfigParser
from pathlib import Path
from .settings import BASE_DIR

CONFIG_APPS = ConfigParser(interpolation=None)
CONFIG_APPS.read(BASE_DIR / 'config_apps.ini', encoding='utf-8-sig')

def caminho(secao, chave, padrao=''):
    valor = CONFIG_APPS.get(secao, chave, fallback=padrao).strip()
    if not valor:
        raise ValueError(f'Configure {secao}.{chave} em config_apps.ini.')
    p = Path(valor)
    return p if p.is_absolute() else BASE_DIR / p
