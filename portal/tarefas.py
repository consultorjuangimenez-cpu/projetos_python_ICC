"""Execuções isoladas por usuário; somente módulos cadastrados pela TI são executados."""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from flask import Flask, abort, g, redirect, render_template_string, request, send_file, url_for
from .settings import BASE_DIR

_locks = {}
_lock_guard = threading.Lock()
_active = set()
_capacity = threading.BoundedSemaphore(3)

def salvar_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

def pasta_execucao(slug, token):
    if not re.fullmatch(r'[a-f0-9]{32}', token):
        abort(404)
    return BASE_DIR / 'dados' / 'execucoes' / slug / token

def arquivo_enviado(req, field, destination, suffixes, required=True):
    uploaded = req.files.get(field)
    if not uploaded or not uploaded.filename:
        if required:
            raise ValueError('Selecione o arquivo solicitado.')
        return None
    ext = Path(uploaded.filename).suffix.lower()
    if ext not in suffixes:
        raise ValueError('Formato inválido. Aceitos: ' + ', '.join(suffixes))
    path = destination.with_suffix(ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    uploaded.save(path)
    if path.stat().st_size == 0:
        raise ValueError('O arquivo enviado está vazio.')
    return str(path)

def iniciar(slug, module, owner, prepare):
    with _lock_guard:
        lock = _locks.setdefault(slug, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ValueError('Este aplicativo já está processando uma solicitação. Aguarde a conclusão e tente novamente.')
    if not _capacity.acquire(blocking=False):
        lock.release()
        raise ValueError('O servidor já está processando três solicitações. Aguarde uma conclusão e tente novamente.')
    folder = None
    try:
        token = uuid.uuid4().hex
        folder = pasta_execucao(slug, token)
        (folder / 'saida').mkdir(parents=True)
        params = prepare(folder)
        salvar_json(folder / 'parametros.json', params)
        meta = {'id': token, 'owner': owner, 'status': 'processando',
                'criado_em': datetime.now().isoformat(timespec='seconds'),
                'mensagem': 'Processando. Você pode continuar usando os outros aplicativos.'}
        salvar_json(folder / 'execucao.json', meta)
        _active.add(token)
        def run():
            try:
                env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
                with (folder / 'processamento.log').open('w', encoding='utf-8') as log:
                    result = subprocess.run([sys.executable, '-m', module, str(folder)],
                        cwd=BASE_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
                        timeout=7200, check=False)
                output = folder / 'resultado.json'
                info = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
                if result.returncode:
                    raise RuntimeError('Não foi possível concluir. Consulte o registro desta execução.')
                meta.update(status='concluido', mensagem=info.get('mensagem', 'Processamento concluído.'))
            except subprocess.TimeoutExpired:
                meta.update(status='erro', mensagem='O limite de duas horas foi atingido. Confira o registro e eventuais arquivos parciais antes de repetir.')
            except Exception as exc:
                meta.update(status='erro', mensagem=str(exc))
            finally:
                meta['finalizado_em'] = datetime.now().isoformat(timespec='seconds')
                salvar_json(folder / 'execucao.json', meta)
                _active.discard(token)
                lock.release()
                _capacity.release()
        threading.Thread(target=run, daemon=False, name=f'portal-{slug}').start()
        return token
    except Exception:
        if folder:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)
        lock.release()
        _capacity.release()
        raise

STYLE = '''body{font:16px 'Segoe UI',Arial,sans-serif;background:#edf2f7;color:#203246;margin:0;padding:28px}.card{max-width:820px;margin:auto;background:white;border:1px solid #d7e1ea;border-radius:12px;padding:28px}h1{font-size:25px;margin-top:0;color:#1f4e78}p{line-height:1.55}label{display:block;margin:16px 0 6px;font-weight:600}input,select,textarea{font:inherit;box-sizing:border-box;width:100%;padding:10px;border:1px solid #aebfcd;border-radius:6px}input[type=checkbox]{width:auto}button,.button{display:inline-block;padding:12px 18px;background:#245778;color:white;border:0;border-radius:6px;font:inherit;text-decoration:none;cursor:pointer;margin-top:18px}a{color:#245778}li{margin:12px 0}.error{background:#fff0ec;padding:14px;border-radius:6px;color:#982f1c}.note{background:#edf5fc;padding:14px;border-radius:6px}small{color:#506477}'''

def criar_app(name, slug, title, description, fields, prepare, module):
    app = Flask(name)
    app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
    def owned(token):
        folder = pasta_execucao(slug, token)
        try:
            meta = json.loads((folder / 'execucao.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            abort(404)
        if meta['owner'] != g.usuario['id']:
            abort(404)
        if meta['status'] == 'processando' and token not in _active:
            meta = {**meta, 'status': 'interrompido', 'mensagem': 'O portal foi reiniciado durante a execução. Confira os arquivos e o registro antes de repetir.'}
        return folder, meta

    @app.route('/', methods=['GET', 'POST'])
    def index():
        error = None
        if request.method == 'POST':
            try:
                token = iniciar(slug, module, g.usuario['id'], lambda folder: prepare(request, folder))
                return redirect(url_for('execucao', token=token), code=303)
            except ValueError as exc:
                error = str(exc)
            except Exception:
                app.logger.exception('Falha ao preparar execução de %s', slug)
                error = 'Não foi possível ler os dados enviados. Confira o arquivo e as configurações do aplicativo.'
        history = []
        base = BASE_DIR / 'dados' / 'execucoes' / slug
        if base.exists():
            for path in base.glob('*/execucao.json'):
                try:
                    item = json.loads(path.read_text(encoding='utf-8'))
                    if item['owner'] == g.usuario['id']:
                        history.append(item)
                except (OSError, ValueError, KeyError):
                    continue
        history.sort(key=lambda x: x['criado_em'], reverse=True)
        return render_template_string('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }}</title><style>{{ style }}</style><div class="card"><h1>{{ title }}</h1><p>{{ description }}</p>{% if error %}<p class="error">{{ error }}</p>{% endif %}<form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'''+fields+'''<button type="submit">Iniciar processamento</button></form><p><small>Uma execução por vez neste aplicativo. Cada usuário acessa somente seus resultados.</small></p>{% if history %}<h2>Minhas últimas execuções</h2><ul>{% for item in history %}<li><a href="{{ url_for('execucao', token=item.id) }}">{{ item.criado_em }} · {{ item.status }}</a></li>{% endfor %}</ul>{% endif %}</div></html>''', title=title, description=description, style=STYLE, error=error, history=history[:20]), (400 if error else 200)

    @app.get('/execucoes/<token>')
    def execucao(token):
        folder, meta = owned(token)
        files = [] if meta['status'] == 'processando' else sorted(p.name for p in (folder/'saida').iterdir() if p.is_file())
        return render_template_string('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">{% if meta.status == 'processando' %}<meta http-equiv="refresh" content="3">{% endif %}<title>{{ title }}</title><style>{{ style }}</style><div class="card"><h1>{{ title }}</h1><p class="note">{{ meta.mensagem }}</p>{% if files %}<h2>Arquivos desta execução</h2><ul>{% for file in files %}<li><a href="{{ url_for('download', token=meta.id, filename=file) }}">Baixar {{ file }}</a></li>{% endfor %}</ul>{% endif %}{% if meta.status != 'processando' %}<p><a href="{{ url_for('registro', token=meta.id) }}">Baixar registro do processamento</a></p>{% endif %}<a class="button" href="{{ url_for('index') }}">Voltar</a></div></html>''',title=title, style=STYLE, meta=meta, files=files)

    @app.get('/execucoes/<token>/arquivos/<filename>')
    def download(token, filename):
        folder, meta = owned(token)
        if meta['status'] == 'processando':
            abort(409)
        root = (folder/'saida').resolve()
        path = (root/filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True)

    @app.get('/execucoes/<token>/registro')
    def registro(token):
        folder, meta = owned(token)
        if meta['status'] == 'processando':
            abort(409)
        path = folder/'processamento.log'
        if not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True, download_name='processamento.txt')
    return app
