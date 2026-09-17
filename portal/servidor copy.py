"""Portal interno: menu e aplicaÃ§Ã£o PDF no mesmo endereÃ§o HTTP."""
import logging
import socket
import threading
import time
import urllib.request
import webbrowser

from flask import Flask, render_template, jsonify, g
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from .settings import PORT, CLIENTS_ROOT, BASE_DIR, CONFIG
from .usuarios import Usuarios
from .acesso import configure_access
from .catalogo import carregar_aplicativos
APLICATIVOS, MONTAGENS = carregar_aplicativos(BASE_DIR / "aplicativos.json")

portal = Flask(__name__)
portal.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
USUARIOS = Usuarios(BASE_DIR / "dados")
configure_access(portal, APLICATIVOS, MONTAGENS, USUARIOS, CONFIG.getboolean("seguranca", "cookie_https", fallback=False))

@portal.get('/')
def home():
    permitidos = [a for a in APLICATIVOS if g.usuario['admin'] or a['rota'] in g.usuario['routes']]
    return render_template('portal.html', aplicativos=permitidos)

@portal.get('/saude')
def health():
    return jsonify(servico='portal-python-teste', status='ok')

@portal.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

application = DispatcherMiddleware(portal, MONTAGENS)

def open_when_ready():
    # SÃ³ este processo abre o navegador, uma vez, depois da resposta HTTP.
    for _ in range(30):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/saude', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(f'http://127.0.0.1:{PORT}/')
                    return
        except OSError:
            time.sleep(0.5)

def main():
    from .primeiro_admin import configurar
    configurar(USUARIOS)
    from waitress import create_server

    try:
        server = create_server(
            application,
            host='127.0.0.1',
            port=PORT,
            threads=6,
            max_request_body_size=33 * 1024 * 1024,
            trusted_proxy='127.0.0.1',
            trusted_proxy_headers={
                'x-forwarded-proto',
                'x-forwarded-host',
            },
            clear_untrusted_proxy_headers=True,
        )
    except OSError:
        print(f'ERRO: nao foi possivel abrir a porta {PORT}. Verifique se o portal ja esta aberto.')
        raise
    print('\nPORTAL PYTHON | TESTE INTERNO')
    print(f'No notebook: http://127.0.0.1:{PORT}/')
    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
        for ip in ips:
            if not ip.startswith('127.'):
                print(f'Endereco candidato na rede: http://{ip}:{PORT}/')
    except OSError:
        pass
    print('Se houver varios enderecos, use o IPv4 da conexao da empresa (ipconfig).')
    print(f'Pasta de clientes: {CLIENTS_ROOT}')
    if not CLIENTS_ROOT.is_dir():
        print('ATENCAO: pasta inacessivel. Ajuste config.ini e reinicie o portal.')
    print('Login obrigatorio. Cadastre usuarios e permissoes em Gerenciar usuarios.')
    print('Mantenha esta janela aberta. CTRL+C encerra o servidor.\n', flush=True)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run()
    except KeyboardInterrupt:
        logging.info('Servidor encerrado pelo operador.')
    finally:
        server.close()

if __name__ == '__main__':
    main()

