import importlib.util
import json
from pathlib import Path
import smtplib
import ssl
from types import SimpleNamespace
import unittest

path=Path(__file__).resolve().parents[1]/'ferramentas_lembretes/diagnosticar_smtp.py'
spec=importlib.util.spec_from_file_location('diag_smtp',path)
diag=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class FakeSMTP:
    esmtp_features={'auth':'PLAIN LOGIN'}
    def __init__(self,error=None,code=235):self.calls=[];self.error=error;self.code=code
    def ehlo_or_helo_if_needed(self):self.calls.append('EHLO')
    def starttls(self,context):self.calls.append('STARTTLS')
    def ehlo(self):self.calls.append('EHLO')
    def login(self,user,password):
        self.calls.append('AUTH')
        if self.error:raise self.error
        return self.code,b'Accepted'
    def close(self):self.calls.append('CLOSE')
    def mail(self,*args):raise AssertionError('Nao enviar MAIL no diagnostico')
    def rcpt(self,*args):raise AssertionError('Nao enviar RCPT no diagnostico')
    def data(self,*args):raise AssertionError('Nao enviar DATA no diagnostico')


def settings(**kwargs):
    return SimpleNamespace(**({'host':'smtp.example.com','port':465,'security':'SSL',
        'username':'teste@example.com','password':'SENHA_TESTE_NAO_REAL','timeout':10}|kwargs))


class DiagnosticTests(unittest.TestCase):
    def test_auth_only_no_message(self):
        client=FakeSMTP()
        result=diag.diagnose(settings(),lambda:client)
        self.assertEqual(result['autenticacao'],'OK')
        self.assertEqual(client.calls,['EHLO','AUTH','CLOSE'])
        self.assertTrue(result['nenhuma_mensagem_enviada'])

    def test_tls_precedes_auth(self):
        client=FakeSMTP()
        result=diag.diagnose(settings(security='STARTTLS',port=587),lambda:client)
        self.assertEqual(result['autenticacao'],'OK')
        self.assertEqual(client.calls,['EHLO','STARTTLS','EHLO','AUTH','CLOSE'])

    def test_no_password_no_connection(self):
        calls=[]
        result=diag.diagnose(settings(password=''),lambda:calls.append(1))
        self.assertFalse(calls)
        self.assertEqual(result['autenticacao'],'NAO_TESTADA')

    def test_535_redacts_entire_server_response(self):
        exc=smtplib.SMTPAuthenticationError(535,b'5.7.8 refused secret SENHA_TESTE_NAO_REAL')
        result=diag.diagnose(settings(),lambda:FakeSMTP(exc))
        self.assertEqual((result['autenticacao'],result['codigo_smtp'],result['codigo_estendido']),('RECUSADA',535,'5.7.8'))
        self.assertNotIn('SENHA_TESTE_NAO_REAL',json.dumps(result))
        self.assertNotIn('refused secret',json.dumps(result))

    def test_plaintext_blocked(self):
        calls=[]
        result=diag.diagnose(settings(security='NONE'),lambda:calls.append(1))
        self.assertFalse(calls)
        self.assertEqual(result['autenticacao'],'NAO_TESTADA')

    def test_tls_failure_has_safe_diagnostic(self):
        def failing():raise ssl.SSLCertVerificationError('certificate')
        result=diag.diagnose(settings(),failing)
        self.assertEqual(result['conexao_tls'],'CERTIFICADO_NAO_VALIDADO')

    def test_close_failure_does_not_hide_success(self):
        class CloseFails(FakeSMTP):
            def close(self):raise OSError('close failed')
        self.assertEqual(diag.diagnose(settings(),CloseFails)['autenticacao'],'OK')

    def test_503_not_proof_of_supplied_credentials(self):
        self.assertEqual(diag.diagnose(settings(),lambda:FakeSMTP(code=503))['autenticacao'],'RESPOSTA_INESPERADA')


if __name__=='__main__':unittest.main()
