CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, title TEXT NOT NULL,
 description TEXT NOT NULL, links TEXT NOT NULL, start_date TEXT NOT NULL, clock TEXT NOT NULL,
 timezone TEXT NOT NULL, rule TEXT NOT NULL, next_ts INTEGER, next_index INTEGER NOT NULL DEFAULT 0,
 last_sent INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
 created_by INTEGER NOT NULL, created_by_name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ATIVO','PAUSADO','CONCLUIDO','CANCELADO')),
 send_count INTEGER NOT NULL DEFAULT 0, scheduled_count INTEGER NOT NULL DEFAULT 0,
 skipped_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(status, next_ts);
CREATE INDEX IF NOT EXISTS tasks_owner ON tasks(created_by);
CREATE TABLE IF NOT EXISTS deliveries (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 task_id INTEGER REFERENCES tasks(id), kind TEXT NOT NULL CHECK(kind IN ('SCHEDULED','MANUAL','TEST')),
 generation INTEGER, ordinal INTEGER, scheduled_ts INTEGER NOT NULL,
 payload TEXT NOT NULL, actor_id INTEGER NOT NULL, actor_name TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('WAITING','SENDING','SENT','ERROR','UNKNOWN','CANCELED','DISCARDED')),
 available_at INTEGER NOT NULL, created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
 attempts INTEGER NOT NULL DEFAULT 0, error TEXT, message_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS deliveries_queue ON deliveries(state, available_at);
CREATE INDEX IF NOT EXISTS deliveries_task ON deliveries(task_id, generation, scheduled_ts);
CREATE TABLE IF NOT EXISTS history (
 id INTEGER PRIMARY KEY, delivery_id INTEGER NOT NULL REFERENCES deliveries(id), at INTEGER NOT NULL,
 result TEXT NOT NULL CHECK(result IN ('ENVIADO','ERRO')), detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS history_at ON history(at);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES tasks(id), at INTEGER NOT NULL,
 actor_id INTEGER, actor_name TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS worker_state (
 id INTEGER PRIMARY KEY CHECK(id=1), heartbeat INTEGER NOT NULL, pid INTEGER NOT NULL,
 smtp_ready INTEGER NOT NULL, last_error TEXT NOT NULL
);
PRAGMA user_version=1;
