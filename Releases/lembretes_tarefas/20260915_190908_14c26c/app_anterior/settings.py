"""Configuração isolada do aplicativo, sem alterar o config.ini do portal."""
from configparser import ConfigParser
from dataclasses import dataclass, field
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PORTAL_ROOT = Path(__file__).resolve().parents[2]
REMETENTE = 'ti@icccontabilidade.com.br'


@dataclass(frozen=True)
class Settings:
    root: Path = PORTAL_ROOT
    timezone: str = 'America/Cuiaba'
    host: str = 'smtp.kinghost.net'
    port: int = 465
    security: str = 'SSL'
    username: str = REMETENTE
    password: str = field(default='', repr=False)
    timeout: int = 30
    poll: int = 15

    @property
    def data_dir(self):
        return self.root / 'dados' / 'apps' / 'lembretes_tarefas'

    @property
    def db_path(self):
        return self.data_dir / 'lembretes.sqlite3'

    @property
    def log_dir(self):
        return self.root / 'logs' / 'lembretes_tarefas'

    @property
    def zone(self):
        return ZoneInfo(self.timezone)


def load_settings(root=None):
    root = Path(root or PORTAL_ROOT).resolve()
    config = ConfigParser(interpolation=None)
    config.read(root / 'dados/apps/lembretes_tarefas/config.ini', encoding='utf-8-sig')

    def get(key, default, env=None):
        return os.environ.get(env or ('LEMBRETES_' + key.upper()),
                              config.get('lembretes', key, fallback=str(default))).strip()

    try:
        settings = Settings(root=root,
            timezone=get('fuso', 'America/Cuiaba'),
            host=get('smtp_servidor', 'smtp.kinghost.net', 'PORTAL_SMTP_SERVIDOR'),
            port=int(get('smtp_porta', 465, 'PORTAL_SMTP_PORTA')),
            security=get('smtp_seguranca', 'SSL', 'PORTAL_SMTP_SEGURANCA').upper(),
            username=get('smtp_usuario', REMETENTE, 'PORTAL_SMTP_USUARIO'),
            password=os.environ.get('PORTAL_SMTP_SENHA', ''),
            timeout=int(get('smtp_timeout', 30)), poll=int(get('intervalo_verificacao', 15)))
        settings.zone
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError('Configuração inválida. Confira fuso, porta e intervalos; instale tzdata no Windows.') from exc
    if settings.security not in {'SSL', 'STARTTLS'}:
        raise ValueError('smtp_seguranca deve ser SSL ou STARTTLS.')
    if not 1 <= settings.port <= 65535 or not 5 <= settings.timeout <= 120 or not 5 <= settings.poll <= 60:
        raise ValueError('Confira a porta, timeout (5 a 120 s) e verificação (5 a 60 s).')
    if not settings.host or any(c.isspace() for c in settings.host):
        raise ValueError('Informe um servidor SMTP válido.')
    return settings
