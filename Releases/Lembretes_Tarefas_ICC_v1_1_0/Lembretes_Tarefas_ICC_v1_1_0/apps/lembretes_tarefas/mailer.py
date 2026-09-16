"""SMTP com classificação conservadora de falhas antes/depois de DATA."""
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr
from html import escape
import smtplib
import ssl
from zoneinfo import ZoneInfo
from .settings import REMETENTE


class MailFailure(Exception):
    def __init__(self, message, transient=False, uncertain=False):
        super().__init__(message)
        self.transient = transient
        self.uncertain = uncertain


def message_for(delivery):
    payload = delivery['payload']
    when = datetime.fromtimestamp(payload['scheduled_ts'], ZoneInfo(payload['timezone']))
    subject = 'Teste de e-mail: Lembretes de Tarefas' if delivery['kind'] == 'TEST' else 'Lembrete de tarefa: '+payload['title']
    msg = EmailMessage(policy=SMTP)
    msg['From'] = formataddr(('ICC Contabilidade | Lembretes', REMETENTE))
    msg['To'] = payload['email']
    msg['Subject'] = subject
    msg['Message-ID'] = delivery['message_id']
    msg['Date'] = format_datetime(datetime.now(timezone.utc))
    parts = [f"Olá, {payload['name']}.", 'Este é um lembrete referente à tarefa abaixo:',
             f"Tarefa: {payload['title']}", f"Data: {when:%d/%m/%Y}", f"Horário: {when:%H:%M} ({payload['timezone']})",
             payload['description'] or 'Sem descrição.', 'Links relacionados:']
    for link in payload['links']:
        parts.append(f"{link['label']}: {link['value']}")
    footer = 'Este é um lembrete automático enviado pelo Portal de Aplicações da ICC Contabilidade.'
    parts.append(footer)
    msg.set_content('\n\n'.join(parts))
    links = ''.join('<li style="margin:10px 0"><a href="'+escape(link['href'], quote=True)+'">'+escape(link['label'])+'</a><br><span style="font-size:13px;word-break:break-all">'+escape(link['value'])+'</span></li>' for link in payload['links'])
    has_paths = any(link['kind'] == 'path' for link in payload['links'])
    html = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><body style="margin:0;background:#f2f4f6;font:15px Arial,sans-serif;color:#243547">
    <div style="max-width:640px;margin:24px auto;background:white;border:1px solid #dce3e9;padding:30px">
    <p style="color:#526a7d;font-size:12px;letter-spacing:1px">ICC CONTABILIDADE · LEMBRETE DE TAREFA</p>
    <p>Olá, {escape(payload['name'])}.</p><p>Este é um lembrete referente à tarefa abaixo:</p>
    <h1 style="font-size:23px;color:#1f4e78">{escape(payload['title'])}</h1>
    <p><strong>Data:</strong> {when:%d/%m/%Y}<br><strong>Horário:</strong> {when:%H:%M} ({escape(payload['timezone'])})</p>
    <p><strong>Descrição:</strong></p><p style="line-height:1.6">{escape(payload['description'] or 'Sem descrição.').replace(chr(10), '<br>')}</p>
    {('<p><strong>Links relacionados:</strong></p><ul>'+links+'</ul>') if links else ''}
    {'<p style="font-size:13px">Se um caminho de rede não abrir pelo e-mail, copie o endereço e cole no Explorador de Arquivos do Windows. O acesso depende das permissões e da conexão à rede da empresa.</p>' if has_paths else ''}
    <p style="border-top:1px solid #dce3e9;padding-top:18px;font-size:12px;color:#526a7d">{footer}</p>
    </div></body></html>'''
    msg.add_alternative(html, subtype='html')
    return msg


def _response(code, phase):
    if code >= 400:
        raise MailFailure(f'SMTP recusou {phase} (código {code}).', transient=400 <= code < 500)


def send_email(settings, delivery, smtp_factory=None):
    if not settings.password:
        raise MailFailure('Senha SMTP não configurada no agendador.')
    if not settings.username:
        raise MailFailure('Usuário SMTP não configurado.')
    msg = message_for(delivery)
    client = None
    phase = 'connect'
    try:
        context = ssl.create_default_context()
        if smtp_factory:
            client = smtp_factory()
        elif settings.security == 'SSL':
            client = smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout, context=context)
        else:
            client = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)
        client.ehlo_or_helo_if_needed()
        if settings.security == 'STARTTLS':
            client.starttls(context=context)
            client.ehlo()
        client.login(settings.username, settings.password)
        code, _ = client.mail(REMETENTE)
        _response(code, 'o remetente')
        code, _ = client.rcpt(delivery['payload']['email'])
        _response(code, 'o destinatário')
        # Nunca iniciar outra tentativa automática se a conexão cair em DATA.
        phase = 'data'
        code, _ = client.data(msg.as_bytes())
        if code != 250:
            if code >= 400:
                _response(code, 'a mensagem')
            raise MailFailure('Resposta SMTP inesperada após DATA. Resultado não confirmado.', uncertain=True)
    except MailFailure:
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise MailFailure(f'Autenticação SMTP recusada (código {exc.smtp_code}). Execute DIAGNOSTICAR_SMTP.bat no servidor para conferir a credencial carregada e o servidor configurado.', transient=400 <= exc.smtp_code < 500) from None
    except smtplib.SMTPResponseException as exc:
        # Resposta explícita 4xx/5xx significa que o servidor recusou a etapa.
        raise MailFailure(f'SMTP recusou o envio (código {exc.smtp_code}).', transient=400 <= exc.smtp_code < 500) from None
    except ssl.SSLCertVerificationError:
        raise MailFailure('O certificado TLS do servidor SMTP não pôde ser validado. Confira servidor, data e certificados do Windows.') from None
    except (OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPException) as exc:
        if phase == 'data':
            raise MailFailure('A conexão terminou durante o envio. Resultado não confirmado; confira com o destinatário.', uncertain=True) from None
        raise MailFailure(f'Não foi possível concluir a conexão SMTP ({type(exc).__name__}).', transient=True) from None
    finally:
        # QUIT/close não pode transformar um aceite 250 em falha e causar reenvio.
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
