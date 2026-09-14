"""Configuração compartilhada do piloto interno."""
from configparser import ConfigParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = ConfigParser(interpolation=None)
if not CONFIG.read(BASE_DIR / 'config.ini', encoding='utf-8-sig'):
    raise RuntimeError('Arquivo config.ini não encontrado junto ao servidor.py.')
CLIENTS_ROOT = Path(CONFIG.get('documentos', 'pasta_clientes'))
if not CLIENTS_ROOT.is_absolute():
    CLIENTS_ROOT = BASE_DIR / CLIENTS_ROOT
PORT = CONFIG.getint('servidor', 'porta', fallback=8080)
if not 1024 <= PORT <= 65535:
    raise ValueError('A porta deve estar entre 1024 e 65535.')
