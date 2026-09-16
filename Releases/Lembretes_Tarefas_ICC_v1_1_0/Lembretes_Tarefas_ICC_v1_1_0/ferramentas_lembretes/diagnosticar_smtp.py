"""Somente conexao TLS e AUTH. Nunca executa MAIL, RCPT ou DATA."""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys


def diagnose(settings, client_factory=None):
    result = {'servidor':settings.host,'porta':settings.port,'seguranca':settings.security,
              'usuario_smtp':settings.username,'senha_disponivel':bool(settings.password),
              'conexao_tls':'NAO_TESTADA','autenticacao':'NAO_TESTADA',
              'codigo_smtp':None,'codigo_estendido':None,'nenhuma_mensagem_enviada':True}
    if not settings.password or not settings.username:
        result['orientacao']='Credencial ausente. Execute CONFIGURAR_SMTP.bat na conta Windows do agendador.'
        return result
    if settings.security not in {'SSL','STARTTLS'}:
        result['orientacao']='Configure SSL ou STARTTLS; o teste nao transmite senha sem TLS.'
        return result
    client = None
    stage = 'CONNECT'
    try:
        context = ssl.create_default_context()
        if client_factory:
            client = client_factory()
        elif settings.security == 'SSL':
            client = smtplib.SMTP_SSL(settings.host,settings.port,timeout=settings.timeout,context=context)
        else:
            client = smtplib.SMTP(settings.host,settings.port,timeout=settings.timeout)
        client.ehlo_or_helo_if_needed()
        if settings.security == 'STARTTLS':
            client.starttls(context=context)
            client.ehlo()
        result['conexao_tls']='OK'
        supported={'PLAIN','LOGIN','CRAM-MD5','XOAUTH2','OAUTHBEARER','NTLM','GSSAPI','SCRAM-SHA-1','SCRAM-SHA-256'}
        result['metodos_auth_anunciados']=[name for name in client.esmtp_features.get('auth','').upper().split() if name in supported]
        stage='AUTH'
        code,_ = client.login(settings.username,settings.password)
        result['codigo_smtp']=int(code)
        if code == 235:
            result['autenticacao']='OK'
            result['orientacao']='Credencial aceita. Reinicie o agendador para carregar o mesmo XML e use o teste de e-mail no portal.'
        else:
            result['autenticacao']='RESPOSTA_INESPERADA'
            result['orientacao']='O SMTP retornou um codigo inesperado. Envie este diagnostico para analise.'
    except smtplib.SMTPAuthenticationError as exc:
        result['autenticacao']='RECUSADA'
        result['codigo_smtp']=int(exc.smtp_code)
        # Extrair somente o codigo numerico, nunca a resposta bruta: um servidor
        # pode incluir dados da autenticacao em seu texto de erro.
        raw=exc.smtp_error if isinstance(exc.smtp_error,bytes) else str(exc.smtp_error).encode('utf-8')
        match=re.search(rb'\b([245]\.\d{1,3}\.\d{1,3})\b',raw)
        result['codigo_estendido']=match[1].decode('ascii') if match else None
        result['orientacao']='O par carregado foi recusado. Se a origem for XML, compare com TESTAR_SENHA_DIGITADA.bat. Se ambos falharem, confira o servidor SMTP da conta e solicite ao provedor o motivo da recusa.'
    except ssl.SSLCertVerificationError:
        result['conexao_tls']='CERTIFICADO_NAO_VALIDADO'
        result['orientacao']='Confira o nome do servidor SMTP, a data do Windows e a cadeia de certificados. A validacao TLS nao foi desativada.'
    except (OSError,smtplib.SMTPException) as exc:
        result['etapa_falha']=stage
        result['classe_erro']=type(exc).__name__
        result['orientacao']='Confira servidor, porta, SSL/STARTTLS e conectividade de saida do servidor.'
    finally:
        if client is not None:
            try:client.close()
            except Exception:pass
    return result


def main():
    root=Path(__file__).resolve().parent.parent
    sys.path.insert(0,str(root))
    result={'correcao':'SMTP-R1','data_hora':datetime.now().astimezone().isoformat(timespec='seconds')}
    for key in ['ORIGEM','CONTA_WINDOWS','DATA_XML','SENHA_AMBIENTE_PRESENTE','USUARIO_AMBIENTE_PRESENTE',
                'SENHA_AMBIENTE_DIFERENTE','USUARIO_AMBIENTE_DIFERENTE','TAREFA_ESTADO','TAREFA_CONTA']:
        result[key.lower()]=os.environ.get('LEMBRETES_DIAG_'+key,'Nao informado')
    try:
        from apps.lembretes_tarefas.settings import load_settings
        result.update(diagnose(load_settings(root)))
    except Exception as exc:
        result.update(autenticacao='NAO_TESTADA',classe_erro=type(exc).__name__,
                      orientacao='Nao foi possivel carregar a configuracao do modulo. Confira config.ini e o Python do portal.')
    text=json.dumps(result,ensure_ascii=False,indent=2)
    print(text)
    folder=root/'logs/lembretes_tarefas'
    try:
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/('diagnostico_smtp_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.txt')
        path.write_text(text+'\n',encoding='utf-8')
        print('\nRelatorio sem senha: '+str(path))
    except OSError:
        print('\nNao foi possivel salvar o relatorio. Copie somente a saida exibida acima.')
    return 0 if result.get('autenticacao')=='OK' else 1


if __name__=='__main__':
    raise SystemExit(main())
