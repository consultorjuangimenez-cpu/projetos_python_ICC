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


def _html_for(payload, when, alert, footer, test=False):
    """HTML de e-mail com tabelas e estilos inline, inclusive para Outlook."""
    accent = '#b45309' if alert else '#087f8c'
    tint = '#fff7ed' if alert else '#edf8f8'
    label = 'Atenção ao prazo' if alert else ('Teste de envio' if test else 'Lembrete de tarefa')
    intro = ('Esta tarefa crítica ainda não foi marcada como concluída. Confira o prazo e organize a conclusão.'
             if alert else ('Seu canal de lembretes está pronto. Este é um e-mail de teste.'
                            if test else 'Confira os detalhes e os acessos para realizar sua tarefa.'))
    deadline_html = ''
    if alert:
        deadline = datetime.fromtimestamp(payload['deadline_ts'], ZoneInfo(payload['timezone']))
        categories = ' &nbsp;&middot;&nbsp; '.join(escape(str(payload[key]))
            for key in ('department', 'client') if payload.get(key))
        deadline_html = f'''<tr><td style="padding:0 0 24px">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="{tint}" style="border:1px solid #fed7aa;border-radius:8px">
            <tr><td style="padding:18px 20px;color:{accent}">
              <p style="margin:0 0 6px;font-size:11px;font-weight:bold;letter-spacing:1px">PRIORIDADE CRÍTICA &nbsp;/&nbsp; PRAZO FINAL</p>
              <p style="margin:0;font-size:22px;line-height:30px;font-weight:bold">{deadline:%d/%m/%Y} &nbsp;às {deadline:%H:%M}</p>
              {('<p style="margin:8px 0 0;font-size:13px;line-height:20px;color:#785638">'+categories+'</p>') if categories else ''}
            </td></tr>
          </table></td></tr>'''
    links_html = ''
    for index, link in enumerate(payload['links']):
        path = link['kind'] == 'path'
        primary = index == 0 and not path
        bg, fg = ('#16354b', '#ffffff') if primary else ('#f5f8fa', '#16354b')
        caption = ('Acessar ' if path else 'Abrir ') + link['label']
        links_html += f'''<tr><td align="center" bgcolor="{bg}" style="border:1px solid {bg};border-radius:5px;mso-padding-alt:8px 12px">
          <a href="{escape(link['href'], quote=True)}" style="display:block;padding:8px 12px;color:{fg};font-size:13px;line-height:18px;font-weight:bold;text-decoration:none;word-wrap:break-word;overflow-wrap:anywhere">{escape(caption)}</a>
        </td></tr><tr><td height="12" style="height:12px;font-size:0;line-height:0">&nbsp;</td></tr>'''
    if links_html:
        # Uma única coluna compartilha a largura natural do maior botão.
        links_html = f'''<tr><td style="padding:8px 0 12px;color:#657588;font-size:11px;letter-spacing:1px;font-weight:bold">ACESSOS DA TAREFA</td></tr>
          <tr><td align="left"><table role="presentation" cellspacing="0" cellpadding="0" border="0" style="max-width:100%">{links_html}</table></td></tr>'''
    has_paths = any(link['kind'] == 'path' for link in payload['links'])
    path_hint = ('''<tr><td style="padding:0 0 20px;color:#657588;font-size:12px;line-height:19px">Se um caminho de rede não abrir pelo botão, consulte o endereço no cadastro da tarefa e acesse pelo Explorador de Arquivos do Windows. O acesso depende das permissões e da conexão à rede da empresa.</td></tr>''' if has_paths else '')
    alert_hint = ('<br>Alerta previsto para 24 horas antes do prazo. Em caso de indisponibilidade, o envio ocorre na retomada.' if alert else '')
    description = escape(payload['description'] or 'Sem descrição.').replace('\n', '<br>')
    return f'''<!doctype html>
<html lang="pt-BR" xmlns="http://www.w3.org/1999/xhtml"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>{escape(label)} | ICC Contabilidade</title>
<style>
body,table,td,a {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
table,td {{ mso-table-lspace:0pt; mso-table-rspace:0pt; }}
@media only screen and (max-width:620px) {{
  .outer {{ padding:16px 8px !important; }}
  .content {{ padding:26px 22px 12px !important; }}
  .brand {{ padding:22px !important; }}
  .task-title {{ font-size:24px !important; line-height:31px !important; }}
  .time-cell {{ display:block !important; width:auto !important; padding:14px 18px !important; }}
  .time-last {{ border-left:0 !important; border-top:1px solid #e2e9ef !important; }}
}}
</style></head>
<body style="margin:0;padding:0;width:100%;background-color:#f1f4f8;color:#243547;font-family:Arial,Helvetica,sans-serif">
<div style="display:none;font-size:1px;line-height:1px;color:#f1f4f8;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all">{escape(label)}: {escape(payload['title'])}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f1f4f8">
<tr><td class="outer" align="center" style="padding:36px 16px">
<!--[if mso]><table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#ffffff" style="max-width:600px;table-layout:fixed;border:1px solid #e1e7ee;border-radius:12px">
  <tr><td class="brand" bgcolor="#16354b" style="padding:24px 32px;border-radius:12px 12px 0 0;border-bottom:4px solid #0f9b9a">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr>
      <td width="54" valign="middle"><table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr><td width="42" height="42" align="center" bgcolor="#ffffff" style="color:#16354b;font-size:16px;letter-spacing:1px;font-weight:bold;border-radius:8px">ICC</td></tr></table></td>
      <td valign="middle" style="color:#ffffff;font-size:16px;line-height:22px;font-weight:bold">ICC Contabilidade<br><span style="color:#bcd0de;font-size:11px;letter-spacing:1px;font-weight:normal">PORTAL DE APLICAÇÕES</span></td>
    </tr></table>
  </td></tr>
  <tr><td class="content" style="padding:32px 32px 16px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="table-layout:fixed">
      <tr><td style="padding:0 0 16px"><span style="color:{accent};font-size:11px;line-height:18px;font-weight:bold;letter-spacing:1px">{escape(label.upper())}</span></td></tr>
      <tr><td><h1 class="task-title" style="margin:0 0 20px;color:#16354b;font-size:28px;line-height:36px;font-weight:bold;word-wrap:break-word;overflow-wrap:anywhere">{escape(payload['title'])}</h1></td></tr>
      <tr><td style="padding:0 0 24px;font-size:14px;line-height:23px;color:#657588;word-wrap:break-word;overflow-wrap:anywhere"><span style="color:#243547">Olá, <strong>{escape(payload['name'])}</strong>.</span><br>{intro}</td></tr>
      {deadline_html}
      <tr><td style="padding:0 0 26px">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="#f5f8fa" style="border:1px solid #e2e9ef;border-radius:8px;table-layout:fixed"><tr>
          <td class="time-cell" width="45%" valign="top" style="padding:16px 20px"><p style="margin:0 0 6px;color:#657588;font-size:10px;letter-spacing:1px;font-weight:bold">DATA DO {'ALERTA' if alert else 'LEMBRETE'}</p><p style="margin:0;color:#243547;font-size:17px;line-height:24px;font-weight:bold">{when:%d/%m/%Y}</p></td>
          <td class="time-cell time-last" valign="top" style="padding:16px 20px;border-left:1px solid #e2e9ef"><p style="margin:0 0 6px;color:#657588;font-size:10px;letter-spacing:1px;font-weight:bold">HORÁRIO</p><p style="margin:0;color:#243547;font-size:17px;line-height:24px;font-weight:bold">{when:%H:%M}</p><p style="margin:3px 0 0;color:#728191;font-size:11px;line-height:16px;word-break:break-all">{escape(payload['timezone'])}</p></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:0 0 10px;color:#657588;font-size:11px;letter-spacing:1px;font-weight:bold">DETALHES DA TAREFA</td></tr>
      <tr><td style="padding:0 0 24px;color:#34485b;font-size:14px;line-height:24px;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word">{description}</td></tr>
      {links_html}{path_hint}
    </table>
  </td></tr>
  <tr><td style="padding:20px 24px;border-top:1px solid #e8edf2;color:#728191;font-size:11px;line-height:18px;text-align:center">{footer}{alert_hint}</td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
<p style="margin:20px 0 0;color:#7c8b9a;font-size:11px;line-height:18px">ICC Contabilidade &nbsp;&middot;&nbsp; Lembretes de Tarefas</p>
</td></tr></table></body></html>'''


def message_for(delivery):
    payload = delivery['payload']
    when = datetime.fromtimestamp(payload['scheduled_ts'], ZoneInfo(payload['timezone']))
    subject = 'Teste de e-mail: Lembretes de Tarefas' if delivery['kind'] == 'TEST' else 'Lembrete de tarefa: '+payload['title']
    alert = delivery.get('purpose') == 'ESCALATION'
    intro = 'Este é um lembrete referente à tarefa abaixo:'
    if alert:
        subject = 'Alerta de tarefa crítica: '+payload['title']
        deadline = datetime.fromtimestamp(payload['deadline_ts'], ZoneInfo(payload['timezone']))
        intro = (f'A tarefa crítica ainda não foi marcada como concluída. Prazo final: {deadline:%d/%m/%Y %H:%M} '
                 f'({payload["timezone"]}). O alerta é programado para 24 horas antes do prazo; '
                 'se houver indisponibilidade, será enviado na retomada. '
                 f'Departamento: {payload.get("department") or "Não informado"}. Cliente: {payload.get("client") or "Não informado"}.')
    msg = EmailMessage(policy=SMTP)
    msg['From'] = formataddr(('ICC Contabilidade | Lembretes', REMETENTE))
    msg['To'] = payload['email']
    msg['Subject'] = subject
    msg['Message-ID'] = delivery['message_id']
    msg['Date'] = format_datetime(datetime.now(timezone.utc))
    parts = [f"Olá, {payload['name']}.", intro,
             f"Tarefa: {payload['title']}", f"Data: {when:%d/%m/%Y}", f"Horário: {when:%H:%M} ({payload['timezone']})",
             payload['description'] or 'Sem descrição.', 'Links relacionados:']
    for link in payload['links']:
        parts.append(f"{link['label']}: {link['value']}")
    footer = 'Este é um lembrete automático enviado pelo Portal de Aplicações da ICC Contabilidade.'
    parts.append(footer)
    msg.set_content('\n\n'.join(parts))
    html = _html_for(payload, when, alert, footer, test=delivery['kind'] == 'TEST')
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
