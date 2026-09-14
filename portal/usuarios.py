"""Usuários, permissões e sessões persistentes em SQLite local."""
import hashlib
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

class Usuarios:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / 'usuarios.sqlite3'
        key = directory / 'chave_sessao.txt'
        try:
            with key.open('x', encoding='ascii') as out:
                out.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        self.secret = key.read_text(encoding='ascii').strip()
        if len(self.secret) < 64:
            raise ValueError('Chave de sessão inválida em dados/chave_sessao.txt.')
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL, password TEXT NOT NULL,
                    admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS permissions (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    route TEXT NOT NULL, PRIMARY KEY(user_id, route));
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS failures (username TEXT, ip TEXT, occurred REAL);
                CREATE INDEX IF NOT EXISTS failures_time ON failures(occurred);
            ''')
    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()
    @staticmethod
    def validate(username, name, password=None):
        username = username.strip().lower()
        name = name.strip()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,63}', username):
            raise ValueError('Login: use de 3 a 64 letras sem acento, números, ponto, hífen ou sublinhado.')
        if not 1 <= len(name) <= 100:
            raise ValueError('Informe um nome com até 100 caracteres.')
        if password is not None and not 4 <= len(password) <= 128:
            raise ValueError('A senha precisa ter entre 4 e 128 caracteres.')
        return username, name
    def has_admin(self):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM users WHERE admin=1 AND active=1').fetchone())
    def bootstrap(self, username, name, password):
        username, name = self.validate(username, name, password)
        hashed = generate_password_hash(password)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users').fetchone():
                raise ValueError('Já existem usuários. Use a tela de administração do portal.')
            db.execute('INSERT INTO users(username,name,password,admin) VALUES(?,?,?,1)',(username,name,hashed))
    def list(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT id,username,name,admin,active FROM users ORDER BY name COLLATE NOCASE')]
    def get(self, uid):
        with self.db() as db:
            row = db.execute('SELECT id,username,name,admin,active FROM users WHERE id=?',(uid,)).fetchone()
            if not row:
                return None
            user = dict(row)
            user['routes'] = [r[0] for r in db.execute('SELECT route FROM permissions WHERE user_id=?',(uid,))]
            return user
    def save(self, uid, username, name, password, admin, active, routes, actor_id):
        username, name = self.validate(username, name, password if password or uid is None else None)
        hashed = generate_password_hash(password) if password else None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if uid is None:
                if not hashed:
                    raise ValueError('Informe a senha do novo usuário.')
                uid = db.execute('INSERT INTO users(username,name,password,admin,active) VALUES(?,?,?,?,?)',
                                 (username,name,hashed,int(admin),int(active))).lastrowid
            else:
                old = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not old:
                    raise ValueError('Usuário não encontrado.')
                if uid == actor_id and (not active or not admin):
                    raise ValueError('Você não pode desativar sua própria conta ou retirar sua administração.')
                if old['admin'] and old['active'] and (not admin or not active):
                    count = db.execute('SELECT COUNT(*) FROM users WHERE admin=1 AND active=1').fetchone()[0]
                    if count <= 1:
                        raise ValueError('Mantenha pelo menos um administrador ativo.')
                db.execute('UPDATE users SET username=?,name=?,admin=?,active=? WHERE id=?',
                           (username,name,int(admin),int(active),uid))
                if hashed:
                    db.execute('UPDATE users SET password=? WHERE id=?',(hashed,uid))
                if hashed or not active:
                    db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            db.execute('DELETE FROM permissions WHERE user_id=?',(uid,))
            db.executemany('INSERT INTO permissions(user_id,route) VALUES(?,?)',[(uid,r) for r in set(routes)])
        return uid
    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()
    def authenticate(self, username, password, ip):
        username = username.strip().lower()[:128]
        now = time.time()
        with self.db() as db:
            db.execute('DELETE FROM failures WHERE occurred<?',(now-900,))
            account_count = db.execute('SELECT COUNT(*) FROM failures WHERE username=?',(username,)).fetchone()[0]
            ip_count = db.execute('SELECT COUNT(*) FROM failures WHERE ip=?',(ip,)).fetchone()[0]
            if account_count >= 5 or ip_count >= 30:
                return None, 'Muitas tentativas. Aguarde 15 minutos antes de tentar novamente.'
            row = db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        valid = bool(row and row['active'] and len(password) <= 128 and check_password_hash(row['password'],password))
        if not valid:
            with self.db() as db:
                db.execute('INSERT INTO failures VALUES(?,?,?)',(username,ip,now))
            return None, 'Usuário ou senha inválidos.'
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            current = db.execute('SELECT password,active FROM users WHERE id=?',(row['id'],)).fetchone()
            if not current or not current['active'] or current['password'] != row['password']:
                return None, 'Usuário ou senha inválidos.'
            db.execute('DELETE FROM failures WHERE username=? AND ip=?',(username,ip))
            db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(self.digest(token),row['id'],now+8*3600))
        return token, None
    def resolve(self, token):
        if not isinstance(token, str) or len(token) > 128:
            return None
        with self.db() as db:
            row = db.execute('SELECT u.id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1',
                             (self.digest(token),time.time())).fetchone()
        return self.get(row['id']) if row else None
    def logout(self, token):
        if isinstance(token,str):
            with self.db() as db:
                db.execute('DELETE FROM sessions WHERE token=?',(self.digest(token),))
    def change_password(self, uid, current, password):
        self.validate('valid', 'valid', password)
        with self.db() as db:
            row=db.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()
        if not row or len(current)>128 or not check_password_hash(row['password'],current):
            raise ValueError('Senha atual incorreta.')
        hashed=generate_password_hash(password)
        with self.db() as db:
            db.execute('UPDATE users SET password=? WHERE id=?',(hashed,uid))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
