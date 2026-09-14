"""Execute a partir da pasta do aplicativo: python -m unittest discover -s tests -v"""
import importlib
import io
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
from flask import g
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client
from werkzeug.wrappers import Response

PASTA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PASTA.parent))
indice = importlib.import_module(PASTA.name + '.src.indice_pdf')
CNPJ = '11222333000181'


def pdf(caminho, texto, paginas=1):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for _ in range(paginas):
            doc.new_page().insert_text((30, 60), texto)
        doc.save(str(caminho))


class Regressao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.raiz = self.base/'documentos'
        self.raiz.mkdir()
        self.db = self.base/'indice.sqlite3'
        self.log = logging.getLogger('teste')

    def atualizar(self):
        return indice.atualizar_indice(self.raiz, self.db, self.log)

    def buscar(self):
        return indice.buscar_pdfs_por_cnpj(self.raiz, self.db, CNPJ, self.log)

    def test_incremental_modificados_excluidos_e_busca_sem_rede(self):
        pdf(self.raiz/'a.pdf', '11.222.333/0001-81')
        pdf(self.raiz/'sub'/'b.PDF', CNPJ)
        pdf(self.raiz/'outro.pdf', '99888777000166')
        self.assertEqual(self.atualizar().lidos, 3)
        with patch.object(indice, '_extrair_conteudo_numerico', side_effect=AssertionError('Releitura indevida')):
            self.assertEqual(self.atualizar().reaproveitados, 3)
        stat_original = Path.stat
        def stat_local(caminho, *args, **kwargs):
            if caminho.is_relative_to(self.raiz):
                raise AssertionError('Consulta à rede indevida')
            return stat_original(caminho, *args, **kwargs)
        with patch.object(Path, 'stat', stat_local), patch.object(os, 'walk', side_effect=AssertionError('Varredura indevida')):
            docs, stats = self.buscar()
            self.assertEqual(len(docs), 2)
            self.assertEqual(stats.lidos, 0)
        (self.raiz/'a.pdf').unlink()
        (self.raiz/'outro.pdf').unlink()
        pdf(self.raiz/'outro.pdf', CNPJ)
        stats = self.atualizar()
        self.assertEqual(stats.lidos, 1)
        self.assertEqual({d.caminho.name for d in self.buscar()[0]}, {'b.PDF', 'outro.pdf'})

    def test_indice_antigo_e_raizes_isoladas(self):
        pdf(self.raiz/'a.pdf', CNPJ)
        self.atualizar()
        with sqlite3.connect(self.db) as con:
            con.execute('DROP TABLE indice_meta')
        with patch.object(indice, '_extrair_conteudo_numerico', side_effect=AssertionError('Migração não deve reler')):
            self.assertEqual(len(self.buscar()[0]), 1)
            self.assertEqual(self.atualizar().reaproveitados, 1)
        outra = self.base/'documentos2'; outra.mkdir()
        pdf(outra/'b.pdf', CNPJ)
        indice.atualizar_indice(outra, self.db, self.log)
        self.assertEqual(len(self.buscar()[0]), 1)

    def test_raiz_equivalente_reaproveita_legado_sem_reler(self):
        pdf(self.raiz/'cliente'/'CNPJ.pdf', CNPJ)
        self.atualizar()
        alias = self.base/'unidade_mapeada'
        alias.symlink_to(self.raiz, target_is_directory=True)
        # Reproduz o defeito: registros resolvidos, consulta pelo alias, zero.
        self.assertEqual(indice.informacoes_indice(self.db, alias)['total_pdfs'], 0)
        with patch.object(indice, '_extrair_conteudo_numerico', side_effect=AssertionError('Não deve reler')):
            self.assertEqual(indice.preparar_indice(alias, self.db, self.log), 1)
            docs, stats = indice.buscar_pdfs_por_cnpj(alias, self.db, CNPJ, self.log)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].caminho, alias/'cliente'/'CNPJ.pdf')
            self.assertEqual(indice.atualizar_indice(alias, self.db, self.log).reaproveitados, 1)
            self.assertEqual(indice.preparar_indice(alias, self.db, self.log), 0)

    def test_migracao_mescla_duplicados_e_preserva_outra_raiz(self):
        pdf(self.raiz/'CNPJ.pdf', CNPJ)
        self.atualizar()
        outra = self.base/'outra'; outra.mkdir()
        pdf(outra/'nao_mover.pdf', CNPJ)
        indice.atualizar_indice(outra, self.db, self.log)
        alias = self.base/'alias'; alias.symlink_to(self.raiz, target_is_directory=True)
        with sqlite3.connect(self.db) as con:
            row = list(con.execute('SELECT * FROM pdfs WHERE caminho=?', (str(self.raiz/'CNPJ.pdf'),)).fetchone())
            row[0] = str(alias/'CNPJ.pdf'); row[4] = '999'; row[8] = '2099-01-01'
            con.execute('INSERT INTO pdfs VALUES (?,?,?,?,?,?,?,?,?)', row)
        self.assertEqual(indice.preparar_indice(alias, self.db, self.log), 1)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pdfs').fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT conteudo_numerico FROM pdfs WHERE caminho=?', (str(alias/'CNPJ.pdf'),)).fetchone()[0], '999')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM pdfs WHERE caminho=?', (str(outra/'nao_mover.pdf'),)).fetchone()[0], 1)

    def test_pdf_sem_texto_corrompido_e_cnpj_na_ultima_pagina(self):
        with pymupdf.open() as doc:
            doc.new_page()
            doc.save(str(self.raiz/'vazio.pdf'))
        (self.raiz/'ruim.pdf').write_bytes(b'arquivo invalido')
        with pymupdf.open() as doc:
            for _ in range(5):
                doc.new_page()
            doc[-1].insert_text((30, 60), CNPJ)
            doc.save(str(self.raiz/'ultima.pdf'))
        stats = self.atualizar()
        self.assertEqual((stats.sem_texto, stats.erros), (1, 1))
        self.assertEqual([d.caminho.name for d in self.buscar()[0]], ['ultima.pdf'])

    def test_falha_rede_nao_apaga_indice(self):
        pdf(self.raiz/'a.pdf', CNPJ)
        self.atualizar()
        def falhar(raiz, onerror, **kwargs):
            onerror(PermissionError('rede indisponível'))
            return iter(())
        with patch.object(os, 'walk', side_effect=falhar):
            self.atualizar()
        self.assertEqual(len(self.buscar()[0]), 1)

    def test_fallback_pypdf(self):
        pdf(self.raiz/'a.pdf', CNPJ)
        with patch.object(indice, 'pymupdf', None):
            self.assertEqual(self.atualizar().lidos, 1)
        self.assertEqual(len(self.buscar()[0]), 1)

    def carregar_app(self):
        for handler in list(logging.getLogger('buscar_pdfs_cnpj').handlers):
            handler.close()
            logging.getLogger('buscar_pdfs_cnpj').removeHandler(handler)
        # O pacote enviado depende do portal, não incluído no ZIP. Simula somente a integração.
        portal = types.ModuleType('portal')
        integracao = types.ModuleType('portal.integracao')
        integracao.caminho = lambda *args: self.raiz
        settings = types.ModuleType('portal.settings'); settings.BASE_DIR = self.base
        with patch.dict(sys.modules, {'portal': portal, 'portal.integracao': integracao, 'portal.settings': settings}):
            nome = PASTA.name + '.app'
            sys.modules.pop(nome, None)
            modulo = importlib.import_module(nome)
        modulo.app.config.update(TESTING=True)
        def fechar_logs():
            for handler in list(modulo.LOGGER.logger.handlers):
                handler.close()
                modulo.LOGGER.logger.removeHandler(handler)
        self.addCleanup(fechar_logs)
        modulo.app.jinja_env.globals['csrf_token'] = lambda: 'csrf-teste'
        @modulo.app.before_request
        def usuario():
            from flask import request
            g.usuario = {'id': request.headers.get('X-Usuario', '1')}
        return modulo

    def test_busca_e_zip_montados_no_portal(self):
        pdf(self.raiz/'cliente1'/'guia.pdf', CNPJ)
        pdf(self.raiz/'cliente2'/'guia.pdf', CNPJ)
        mod = self.carregar_app()
        indice.atualizar_indice(self.raiz, mod.CAMINHO_INDICE, self.log)
        cliente = Client(DispatcherMiddleware(Response('Portal'), {'/apps/pdf-cnpj': mod.app}), Response)
        base = '/apps/pdf-cnpj'
        resposta = cliente.post(base+'/buscar', data={'cnpj': CNPJ})
        self.assertEqual(resposta.status_code, 200)
        html = resposta.get_data(as_text=True)
        self.assertIn('action="/apps/pdf-cnpj/baixar"', html)
        token = re.search(r'name="token" value="([^"]+)"', html)[1]
        self.assertEqual(cliente.get(base+'/estado-indice').status_code, 200)
        # Força ZIP no disco para testar os dois tipos de temporário.
        for memoria in [50, 0.00001]:
            mod.CONFIG['busca']['memoria_zip_mb'] = memoria
            saida = cliente.post(base+'/baixar', data={'token': token, 'arquivos': ['0', '1', '1']})
            self.assertEqual(saida.status_code, 200)
            dados = saida.get_data()
            self.assertEqual(int(saida.headers['Content-Length']), len(dados))
            self.assertIn('attachment;', saida.headers['Content-Disposition'])
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.namelist(), ['guia.pdf', 'guia (2).pdf'])
                self.assertEqual(z.read('guia.pdf'), (self.raiz/'cliente1'/'guia.pdf').read_bytes())
            saida.close()
        self.assertEqual(cliente.post(base+'/baixar', data={'token': token, 'arquivos': ['0']}, headers={'X-Usuario': '2'}).status_code, 410)
        self.assertEqual(cliente.post(base+'/baixar', data={'token': token, 'arquivos': ['-1']}).status_code, 400)
        self.assertEqual(cliente.post(base+'/baixar', data={'token': token}).status_code, 400)
        # Resultados continuam disponíveis após reiniciar o módulo.
        mod2 = self.carregar_app()
        cliente2 = mod2.app.test_client()
        with cliente2.post('/baixar', data={'token': token, 'arquivos': ['0']}) as resposta:
            self.assertEqual(resposta.status_code, 200)
            resposta.get_data()
        # Arquivo removido não deve gerar ZIP incompleto silenciosamente.
        (self.raiz/'cliente1'/'guia.pdf').unlink()
        self.assertEqual(cliente.post(base+'/baixar', data={'token': token, 'arquivos': ['0', '1']}).status_code, 404)
        with sqlite3.connect(mod.CAMINHO_RESULTADOS) as con:
            con.execute('UPDATE resultados SET criado=?', (time.time()-86400,))
        self.assertEqual(cliente.post(base+'/baixar', data={'token': token, 'arquivos': ['1']}).status_code, 410)

    @unittest.skipUnless(os.environ.get('PDF_TESTE_CNPJ'), 'Informe PDF_TESTE_CNPJ para validar um PDF real')
    def test_pdf_real_busca_e_download_apos_migracao(self):
        import shutil
        real = Path(os.environ['PDF_TESTE_CNPJ'])
        alvo = self.raiz/'AGROPECUARIA SAO PEDRO LTDA'/'CNPJ.pdf'
        alvo.parent.mkdir(); shutil.copyfile(real, alvo)
        for motor in (None, pymupdf):
            with patch.object(indice, 'pymupdf', motor):
                conteudo, status, _ = indice._extrair_conteudo_numerico(alvo)
                self.assertEqual(status, 'ok')
                self.assertIn('42072999000124', conteudo)
        banco = self.base/'dados/apps/buscar_pdf_cnpj/indice_pdfs.sqlite3'
        indice.atualizar_indice(self.raiz, banco, self.log)
        # Portal usa o alias; o índice antigo usa o destino resolvido.
        alias = self.base/'F_documentos_Rafael'; alias.symlink_to(self.raiz, target_is_directory=True)
        self.raiz = alias
        mod = self.carregar_app()
        cliente = mod.app.test_client()
        with patch.object(mod, '_iniciar_atualizacao', side_effect=AssertionError('Índice deve ser reaproveitado')):
            res = cliente.post('/buscar', data={'cnpj': '42.072.999/0001-24'})
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('AGROPECUARIA SAO PEDRO LTDA', html)
        token = re.search(r'name="token" value="([^"]+)"', html)[1]
        with cliente.post('/baixar', data={'token': token, 'arquivos': ['0']}) as saida:
            self.assertEqual(saida.status_code, 200)
            with zipfile.ZipFile(io.BytesIO(saida.get_data())) as z:
                self.assertEqual(z.namelist(), ['CNPJ.pdf'])
                self.assertEqual(z.read('CNPJ.pdf'), real.read_bytes())

    def test_atualizacao_nao_bloqueia_busca(self):
        import threading
        mod = self.carregar_app()
        entrou = threading.Event(); liberar = threading.Event()
        def lento(*args):
            entrou.set(); liberar.wait(5)
        with patch.object(mod, 'atualizar_indice', side_effect=lento):
            cliente = mod.app.test_client()
            self.assertEqual(cliente.post('/atualizar-indice').status_code, 202)
            self.assertTrue(entrou.wait(1))
            self.assertFalse(cliente.post('/atualizar-indice').json['iniciado'])
            self.assertTrue(cliente.get('/estado-indice').json['executando'])
            self.assertEqual(cliente.post('/buscar', data={'cnpj': CNPJ}).status_code, 200)
            liberar.set()
            self.assertTrue(mod._indice_lock.acquire(timeout=2)); mod._indice_lock.release()


if __name__ == '__main__':
    unittest.main()
