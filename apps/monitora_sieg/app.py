"""Aplicativo Flask montado e protegido pelo Portal_Apps existente."""
from __future__ import annotations

import configparser
from pathlib import Path
import threading
import time

from flask import Flask, jsonify, render_template

if not __package__:
    raise SystemExit("Este aplicativo faz parte do Portal_Apps. Inicie pelo servidor.py do portal.")

from .confronto import montar_painel

BASE = Path(__file__).resolve().parent
PORTAL_ROOT = BASE.parents[1]
app = Flask(__name__, template_folder=str(BASE), static_folder=str(BASE / "static"))
_lock = threading.Lock()
_cache = None
_cache_time = 0.0
_signature = None


def configuracao():
    config_path = PORTAL_ROOT / "config_apps.ini"
    conf = configparser.ConfigParser(interpolation=None)
    if not conf.read(config_path, encoding="utf-8-sig"):
        raise ValueError("config_apps.ini não encontrado na raiz do Portal_Apps.")
    values = {}
    for key in ("pasta_sieg", "relatorio_icc"):
        value = conf.get("monitora_sieg", key, fallback="").strip()
        if not value:
            raise ValueError(f"Configure [monitora_sieg] {key} em config_apps.ini.")
        path = Path(value)
        values[key] = path if path.is_absolute() else PORTAL_ROOT / path
    return values


def assinatura(conf):
    arquivos = [PORTAL_ROOT / "config_apps.ini", conf["relatorio_icc"]]
    try:
        arquivos.extend(p for p in conf["pasta_sieg"].iterdir() if p.suffix.lower() == ".xlsx" and not p.name.startswith("~$"))
    except OSError:
        return None
    result = []
    for path in arquivos:
        try:
            st = path.stat()
            result.append((str(path), st.st_mtime_ns, st.st_size))
        except OSError:
            result.append((str(path), None, None))
    return (time.strftime("%Y-%m-%d"), tuple(sorted(result)))


def dados(forcar=False):
    global _cache, _cache_time, _signature
    with _lock:
        now = time.monotonic()
        if not forcar and _cache is not None and now - _cache_time < 10:
            return _cache
        conf = configuracao()
        signature = assinatura(conf)
        if not forcar and signature is not None and signature == _signature and _cache is not None and not _cache["erros"]:
            _cache_time = now
            return _cache
        snapshot = montar_painel(conf["pasta_sieg"], conf["relatorio_icc"])
        if signature != assinatura(conf):
            raise ValueError("Uma planilha mudou durante a leitura. Aguarde terminar a cópia e clique em Atualizar confronto.")
        _cache, _signature, _cache_time = snapshot, signature, now
        for key, error in snapshot["erros"].items():
            app.logger.warning("Monitor SIEG: fonte %s: %s", key, error)
        return snapshot


@app.get("/")
@app.get("/index.html")
def index():
    return render_template("index.html")


def resposta_dados(forcar=False):
    try:
        return jsonify(dados(forcar))
    except Exception as exc:
        app.logger.exception("Não foi possível atualizar o Monitor SIEG")
        return jsonify(erro=f"Não foi possível atualizar o confronto: {exc}"), 500


@app.get("/api/dados")
def api_dados():
    return resposta_dados()


@app.get("/api/atualizar")
def api_atualizar():
    return resposta_dados(forcar=True)


@app.get("/api/saude")
def saude():
    return jsonify(aplicacao="monitora_sieg", status="ok")


@app.after_request
def headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
    return response


if __name__ == "__main__":
    raise SystemExit("Este aplicativo faz parte do Portal_Apps. Inicie pelo servidor.py do portal.")
