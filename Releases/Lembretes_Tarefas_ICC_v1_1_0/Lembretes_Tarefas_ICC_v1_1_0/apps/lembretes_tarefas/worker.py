"""Processo independente, iniciado pelo Agendador de Tarefas do Windows."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import time
from .mailer import MailFailure, send_email
from .settings import load_settings
from .store import Store


class AlreadyRunning(RuntimeError):
    pass


class ProcessLock:
    """Lock do SO, liberado também quando o processo morre. Nunca apagar o arquivo."""
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        if self.file.seek(0, 2) == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise AlreadyRunning('Já existe um agendador ativo para este banco.') from None
        return self

    def __exit__(self, *args):
        if self.file:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_UN)
            self.file.close()


def run_cycle(store, settings, sender=send_email, clock=time.time, limit=50):
    now = int(clock())
    ready = bool(settings.password and settings.username)
    store.heartbeat(now, os.getpid(), ready, '' if ready else 'Configure a credencial SMTP e reinicie o agendador.')
    store.queue_due(now)
    if not ready:
        return 0
    processed = 0
    for _ in range(limit):
        now = int(clock())
        delivery = store.claim(now)
        if not delivery:
            break
        try:
            sender(settings, delivery)
        except MailFailure as exc:
            store.failure(delivery, int(clock()), str(exc), exc.transient, exc.uncertain)
            logging.warning('Envio %s: %s', delivery['id'], str(exc))
        except Exception as exc:
            # Uma falha inesperada pode ocorrer depois do aceite remoto.
            store.failure(delivery, int(clock()), f'Falha inesperada ({type(exc).__name__}). Resultado não confirmado.', uncertain=True)
            logging.error('Envio %s: falha inesperada %s', delivery['id'], type(exc).__name__)
        else:
            # Falha ao gravar o sucesso encerra o processo. A retomada marca UNKNOWN.
            store.success(delivery, int(clock()))
            logging.info('Envio %s aceito pelo SMTP; tipo=%s', delivery['id'], delivery['kind'])
        processed += 1
        store.heartbeat(int(clock()), os.getpid(), ready)
    return processed


def main(argv=None):
    parser = argparse.ArgumentParser(description='Agendador de lembretes ICC')
    parser.add_argument('--once', action='store_true', help='Processa uma rodada e encerra; pode enviar mensagens reais.')
    parser.add_argument('--check', action='store_true', help='Valida configuração e banco sem conectar ao SMTP ou enviar e-mail.')
    args = parser.parse_args(argv)
    settings = load_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if args.check:
        Store(settings.db_path)
        print('Banco e fuso válidos. Credencial SMTP: '+('disponível' if settings.password else 'ausente neste processo')+'. Nenhum e-mail enviado.')
        return 0
    try:
        with ProcessLock(settings.data_dir / 'agendador.lock'):
            logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                handlers=[RotatingFileHandler(settings.log_dir/'agendador.log', maxBytes=2_000_000, backupCount=5, encoding='utf-8'), logging.StreamHandler()])
            store = Store(settings.db_path)
            store.recover_interrupted(int(time.time()))
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            logging.info('Agendador iniciado; fuso=%s; verificação=%ss', settings.timezone, settings.poll)
            while not stop.is_set():
                run_cycle(store, settings)
                if args.once:
                    break
                stop.wait(settings.poll)
            logging.info('Agendador encerrado.')
            return 0
    except AlreadyRunning as exc:
        print(str(exc))
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Não registrar variáveis de ambiente, credenciais, mensagens ou traceback SMTP.
        print(f'Falha no agendador ({type(exc).__name__}). Confira configuração, permissões e banco.', file=sys.stderr)
        raise SystemExit(1)
