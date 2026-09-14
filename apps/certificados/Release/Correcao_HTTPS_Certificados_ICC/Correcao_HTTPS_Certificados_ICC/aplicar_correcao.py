"""Ajuste localizado no app.py atual. Não substitui o restante do módulo."""
import ast
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
MARKER='ICC_HTTPS_DIAGNOSTICO_V2'


def patch(source):
    if MARKER in source:return source
    tree=ast.parse(source)
    factory=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_app'),None)
    if not factory:raise ValueError('Estrutura diferente: create_app não encontrada. Nenhum arquivo alterado. Envie o app.py atual.')
    functions={n.name:n for n in factory.body if isinstance(n,ast.FunctionDef)}
    for name in ('ready_https','bridge_tls'):
        if name not in functions:raise ValueError('Estrutura diferente: '+name+' não encontrada. Nenhum arquivo alterado. Envie o app.py atual.')
    # Substitui somente duas funções, preservando as demais rotas, HTML, dados e configurações.
    ready='''    def ready_https():
        # ICC_HTTPS_DIAGNOSTICO_V2
        from .conexao_https import diagnostico
        return diagnostico(request, cfg['url'])['instalacao_https']

    @app.get('/api/diagnostico-https')
    def diagnostico_conexao_https():
        from .conexao_https import diagnostico
        user = getattr(g, 'usuario', None)
        if not user or not user.get('admin'):
            abort(403, description='Diagnóstico disponível somente ao administrador autenticado.')
        return jsonify(diagnostico(request, cfg['url']))
'''
    bridge='''    def bridge_tls():
        from .conexao_https import diagnostico
        result = diagnostico(request, cfg['url'], verificar_caminho=False)
        if not result['instalacao_https']:
            abort(403, description=result['motivo'])
'''
    lines=source.splitlines(keepends=True)
    for name,replacement in sorted([('ready_https',ready),('bridge_tls',bridge)],key=lambda pair:functions[pair[0]].lineno,reverse=True):
        n=functions[name]
        lines[n.lineno-1:n.end_lineno]=[replacement]
    result=''.join(lines);ast.parse(result)
    return result


def main(target):
    root=Path(target).resolve();app=root/'apps/certificados/app.py';helper=app.with_name('conexao_https.py')
    if not app.is_file():raise ValueError('app.py não encontrado em apps\\certificados. Confira a pasta informada.')
    original=app.read_bytes();updated=patch(original.decode('utf-8-sig'))
    ast.parse((HERE/'conexao_https.py').read_text(encoding='utf-8'))
    backup=root/'backups_atualizacao'/('correcao_https_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True);shutil.copy2(app,backup/'app.py')
    had_helper=helper.exists()
    if had_helper:shutil.copy2(helper,backup/helper.name)
    try:
        shutil.copy2(HERE/'conexao_https.py',helper)
        temp=app.with_name('app.py.https-novo');temp.write_text(updated,encoding='utf-8');temp.replace(app)
    except Exception:
        app.write_bytes(original)
        if had_helper:shutil.copy2(backup/helper.name,helper)
        elif helper.exists():helper.unlink()
        raise
    print('Ajuste aplicado. Backup: '+str(backup))
    print('Reinicie o portal pelo BAT HTTPS e atualize a pagina com Ctrl+F5.')
    print('Diagnostico, apos login de administrador:')
    print('https://10.10.10.154/certificados/api/diagnostico-https')

if __name__=='__main__':
    try:main(sys.argv[1] if len(sys.argv)>1 else r'C:\C\Projetos_Phyton\Portal_Apps')
    except Exception as exc:print('ERRO:',exc);raise SystemExit(1)
