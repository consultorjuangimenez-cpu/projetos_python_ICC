"""Verificação da origem HTTPS já validada pelo servidor WSGI, sem ler headers brutos."""
from urllib.parse import urlsplit

VERSAO='https-20260911-2'

def origem(url):
    try:
        p=urlsplit(url)
        if p.scheme.lower()!='https' or not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment:
            return None
        port=p.port if p.port is not None else 443
        if not 1 <= port <= 65535:return None
        return p.hostname.lower(),port
    except (ValueError,TypeError):return None


def diagnostico(request,url_publica,verificar_caminho=True):
    configured=origem(url_publica)
    received=origem('https://'+request.host)
    try:path=urlsplit(url_publica).path.rstrip('/')
    except (ValueError,TypeError):path=''
    checks={
        'url_configurada_valida':configured is not None,
        'python_recebe_https':bool(request.is_secure),
        'host_e_porta_conferem':configured is not None and configured==received,
        'caminho_confere':not verificar_caminho or path==request.script_root.rstrip('/'),
    }
    reasons=[]
    if not checks['url_configurada_valida']:reasons.append('url_publica não é uma URL HTTPS válida.')
    if not checks['python_recebe_https']:reasons.append('O Python recebeu HTTP; confira o repasse de HTTPS pelo proxy/backend em execução.')
    if not checks['host_e_porta_conferem']:reasons.append('Host ou porta recebidos diferem de url_publica.')
    if not checks['caminho_confere']:reasons.append('O caminho de montagem do módulo difere do caminho em url_publica.')
    return {
        'versao_verificacao':VERSAO,
        'instalacao_https':all(checks.values()),
        'motivo':'Conexão aceita para instalação.' if not reasons else ' '.join(reasons),
        'verificacoes':checks,
        'esquema_recebido':request.scheme,
        'host_recebido':request.host,
        'caminho_montagem':request.script_root,
        'origem_configurada':list(configured) if configured else None,
        'caminho_configurado':path,
    }
