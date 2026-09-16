"""Migração aditiva v3: preserva IDs, fila, histórico e programação legada."""
from datetime import datetime, timezone
from contextlib import closing
import sqlite3
import uuid

TASK_COLUMNS = {
    'business_day_policy': "TEXT NOT NULL DEFAULT 'keep' CHECK(business_day_policy IN ('keep','previous','next'))",
    'priority': "TEXT NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('NORMAL','ALTA','CRITICA'))",
    'department': "TEXT NOT NULL DEFAULT ''",
    'client': "TEXT NOT NULL DEFAULT ''",
    'deadline_ts': 'INTEGER',
    'completed_at': 'INTEGER',
}


def backup_before_upgrade(path):
    if not path.is_file():
        return
    with closing(sqlite3.connect(path, timeout=20)) as source:
        version = source.execute('PRAGMA user_version').fetchone()[0]
        exists = source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()
        if not exists or version >= 3:
            return
        folder = path.parent / 'backups_migracao'
        folder.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        target = folder / f'antes_v3_{stamp}_{uuid.uuid4().hex[:8]}.sqlite3'
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Falha ao conferir o backup antes da migração.')
        finally:
            destination.close()


def upgrade(con):
    columns = {row[1] for row in con.execute('PRAGMA table_info(tasks)')}
    for name, definition in TASK_COLUMNS.items():
        if name not in columns:
            con.execute(f'ALTER TABLE tasks ADD COLUMN {name} {definition}')
    if 'purpose' not in {row[1] for row in con.execute('PRAGMA table_info(deliveries)')}:
        con.execute("ALTER TABLE deliveries ADD COLUMN purpose TEXT NOT NULL DEFAULT 'REMINDER' CHECK(purpose IN ('REMINDER','ESCALATION'))")
    con.execute('CREATE INDEX IF NOT EXISTS tasks_deadline ON tasks(priority, completed_at, deadline_ts)')
    con.execute('CREATE INDEX IF NOT EXISTS tasks_categories ON tasks(department, client)')
    con.execute('PRAGMA user_version=3')
