"""Consultas locais e atualização incremental em segundo plano.

Mantém o esquema do índice 1.0 para reaproveitar os PDFs já lidos.
"""
import logging
import os
import re
import sqlite3
from contextlib import closing
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader
try:
    import pymupdf
except ImportError:
    pymupdf = None


@dataclass(frozen=True)
class DocumentoPDF:
    caminho: Path
    caminho_relativo: str
    tamanho: int


@dataclass
class EstatisticasIndice:
    total_pdfs: int = 0
    lidos: int = 0
    reaproveitados: int = 0
    sem_texto: int = 0
    erros: int = 0


def conectar(caminho_indice):
    caminho_indice = Path(caminho_indice)
    caminho_indice.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho_indice, timeout=30)
    conexao.execute('PRAGMA journal_mode=WAL')
    conexao.execute('PRAGMA synchronous=NORMAL')
    return conexao


def _criar_tabela(conexao):
    conexao.execute('''CREATE TABLE IF NOT EXISTS pdfs (
        caminho TEXT PRIMARY KEY, caminho_relativo TEXT NOT NULL,
        tamanho INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
        conteudo_numerico TEXT NOT NULL, status TEXT NOT NULL, erro TEXT,
        ultimo_scan TEXT NOT NULL, atualizado_em TEXT NOT NULL)''')
    conexao.execute('CREATE INDEX IF NOT EXISTS idx_pdfs_scan ON pdfs (ultimo_scan)')
    conexao.execute('CREATE TABLE IF NOT EXISTS indice_meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)')


def _prefixo(raiz):
    return str(Path(os.path.abspath(raiz))).rstrip('/\\') + os.sep


def _filtro_raiz(raiz):
    # Separador final evita incluir pastas irmãs. Não consulta a rede.
    prefixo = _prefixo(raiz)
    return len(prefixo), prefixo


def preparar_indice(raiz, caminho_indice, logger):
    """Reaproveita caminhos resolvidos da v1.0 após confirmar a raiz equivalente.

    Executada ao iniciar o módulo e ao solicitar atualização, nunca por busca.
    Não abre PDFs. Só move registros cujo prefixo corresponde à raiz resolvida
    pelo sistema operacional, preservando registros de outras pastas.
    """
    info = informacoes_indice(caminho_indice, raiz)
    logger.info('Diagnóstico do índice | banco=%s | total_banco=%s | nesta_raiz=%s | raiz=%s',
                caminho_indice, info['total_banco'], info['total_pdfs'], raiz)
    if info['total_banco'] == 0:
        return 0
    try:
        real = Path(raiz).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        logger.warning('Raiz indisponível para confirmar caminhos equivalentes: %s', exc)
        return 0
    origem = _prefixo(real)
    destino = _prefixo(raiz)
    if origem.casefold() == destino.casefold():
        return 0
    # Prefixos sobrepostos precisam de uma migração específica. Não arrisca
    # apagar destinos recém-inseridos nem reatribuir pastas não equivalentes.
    if origem.casefold().startswith(destino.casefold()) or destino.casefold().startswith(origem.casefold()):
        logger.warning('Normalização de caminhos sobrepostos não aplicada: %s | %s', origem, destino)
        return 0
    with closing(conectar(caminho_indice)) as con, con:
        quantidade = con.execute('SELECT COUNT(*) FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE',
                                 (len(origem), origem)).fetchone()[0]
        if not quantidade:
            return 0
        con.execute("""INSERT INTO pdfs
            SELECT ? || substr(caminho, ?), caminho_relativo, tamanho, mtime_ns,
                   conteudo_numerico, status, erro, ultimo_scan, atualizado_em
            FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE
            ON CONFLICT(caminho) DO UPDATE SET
                caminho_relativo=excluded.caminho_relativo, tamanho=excluded.tamanho,
                mtime_ns=excluded.mtime_ns, conteudo_numerico=excluded.conteudo_numerico,
                status=excluded.status, erro=excluded.erro, ultimo_scan=excluded.ultimo_scan,
                atualizado_em=excluded.atualizado_em
            WHERE excluded.atualizado_em > pdfs.atualizado_em""",
            (destino, len(origem) + 1, len(origem), origem))
        con.execute('DELETE FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE', (len(origem), origem))
        con.execute('INSERT OR IGNORE INTO indice_meta SELECT ?, valor FROM indice_meta WHERE chave=?',
                    ('atualizacao:' + destino, 'atualizacao:' + origem))
    logger.info('Compatibilidade restaurada | registros=%s | de=%s | para=%s | PDFs_relidos=0',
                quantidade, origem, destino)
    return quantidade


def _extrair_conteudo_numerico(caminho):
    try:
        textos = []
        if pymupdf is not None:
            try:
                with pymupdf.open(str(caminho)) as leitor:
                    if leitor.needs_pass and not leitor.authenticate(''):
                        return '', 'erro', 'PDF protegido por senha'
                    for pagina in leitor:
                        textos.append(pagina.get_text('text'))
            except Exception:
                # Um PDF incompatível com o motor rápido ainda tenta o leitor original.
                textos = _extrair_pypdf(caminho)
        else:
            textos = _extrair_pypdf(caminho)
        conteudo = re.sub(r'\D', '', ' '.join(textos))
        if not conteudo:
            return '', 'sem_texto', 'PDF sem texto numérico extraível; pode ser escaneado'
        return conteudo, 'ok', None
    except Exception as exc:
        return '', 'erro', f'{type(exc).__name__}: {exc}'


def _extrair_pypdf(caminho):
    # Fecha o arquivo antes de prosseguir para o próximo PDF.
    with open(caminho, 'rb') as arquivo:
        leitor = PdfReader(arquivo, strict=False)
        if leitor.is_encrypted and leitor.decrypt('') == 0:
            raise ValueError('PDF protegido por senha')
        return [pagina.extract_text() or '' for pagina in leitor.pages]


def informacoes_indice(caminho_indice, raiz):
    with closing(conectar(caminho_indice)) as con, con:
        _criar_tabela(con)
        total = con.execute('SELECT COUNT(*) FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE', _filtro_raiz(raiz)).fetchone()[0]
        total_banco = con.execute('SELECT COUNT(*) FROM pdfs').fetchone()[0]
        atualizado = con.execute('SELECT valor FROM indice_meta WHERE chave=?', ('atualizacao:' + _prefixo(raiz),)).fetchone()
    return {'total_pdfs': total, 'total_banco': total_banco, 'fora_da_raiz': total_banco - total,
            'ultima_atualizacao': atualizado[0] if atualizado else None}


def buscar_pdfs_por_cnpj(raiz, caminho_indice, cnpj, logger):
    """Busca somente no SQLite local, sem listar pastas nem abrir PDFs."""
    with closing(conectar(caminho_indice)) as con, con:
        _criar_tabela(con)
        filtro = _filtro_raiz(raiz)
        grupos = dict(con.execute('SELECT status, COUNT(*) FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE GROUP BY status', filtro))
        registros = con.execute('''SELECT caminho, caminho_relativo, tamanho FROM pdfs
            WHERE substr(caminho,1,?) = ? COLLATE NOCASE
            AND status = 'ok' AND instr(conteudo_numerico, ?) > 0
            ORDER BY caminho_relativo COLLATE NOCASE''', (*filtro, cnpj)).fetchall()
    total = sum(grupos.values())
    estatisticas = EstatisticasIndice(total_pdfs=total, reaproveitados=total,
        sem_texto=grupos.get('sem_texto', 0), erros=grupos.get('erro', 0))
    return [DocumentoPDF(Path(c), r, t) for c, r, t in registros], estatisticas


def atualizar_indice(raiz, caminho_indice, logger, progresso=None):
    """Varre apenas na atualização, salva por lotes e preserva o índice anterior."""
    raiz = Path(os.path.abspath(raiz))
    if not raiz.is_dir():
        raise OSError(f'A pasta de documentos não está disponível: {raiz}')
    scan = uuid.uuid4().hex
    stats = EstatisticasIndice()
    scan_completo = True
    momento = datetime.now().isoformat(timespec='seconds')

    def informar(atual=''):
        if progresso:
            progresso({**vars(stats), 'arquivo_atual': atual})

    def erro_pasta(exc):
        nonlocal scan_completo
        scan_completo = False
        stats.erros += 1
        logger.warning('Pasta não acessível; exclusões suspensas neste ciclo: %s', exc)

    logger.info('Atualizando índice | motor=%s | raiz=%s', 'PyMuPDF' if pymupdf else 'pypdf', raiz)
    with closing(conectar(caminho_indice)) as con, con:
        _criar_tabela(con)
        # Somente metadados pequenos em memória. Não carrega o texto dos PDFs.
        anteriores = {c: (t, m, s) for c, t, m, s in con.execute(
            'SELECT caminho,tamanho,mtime_ns,status FROM pdfs WHERE substr(caminho,1,?) = ? COLLATE NOCASE', _filtro_raiz(raiz))}
        for pasta, diretorios, nomes in os.walk(raiz, onerror=erro_pasta, followlinks=False):
            diretorios[:] = [d for d in diretorios if not (Path(pasta)/d).is_symlink()
                            and not (hasattr(os.path, 'isjunction') and os.path.isjunction(Path(pasta)/d))]
            for nome in nomes:
                if not nome.lower().endswith('.pdf'):
                    continue
                caminho = Path(pasta) / nome
                if caminho.is_symlink():
                    continue
                texto_caminho = str(caminho)
                relativo = str(caminho.relative_to(raiz))
                stats.total_pdfs += 1
                informar(relativo)
                try:
                    dados = caminho.stat()
                    anterior = anteriores.get(texto_caminho)
                    if anterior and anterior[:2] == (dados.st_size, dados.st_mtime_ns) and anterior[2] != 'erro':
                        status = anterior[2]
                        stats.reaproveitados += 1
                        con.execute('UPDATE pdfs SET ultimo_scan=? WHERE caminho=?', (scan, texto_caminho))
                    else:
                        conteudo, status, erro = _extrair_conteudo_numerico(caminho)
                        depois = caminho.stat()
                        if (dados.st_size, dados.st_mtime_ns) != (depois.st_size, depois.st_mtime_ns):
                            conteudo, status, erro = '', 'erro', 'Arquivo alterado durante a leitura; tente atualizar novamente'
                        stats.lidos += 1
                        con.execute('''INSERT INTO pdfs VALUES (?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(caminho) DO UPDATE SET
                            caminho_relativo=excluded.caminho_relativo, tamanho=excluded.tamanho,
                            mtime_ns=excluded.mtime_ns, conteudo_numerico=excluded.conteudo_numerico,
                            status=excluded.status, erro=excluded.erro, ultimo_scan=excluded.ultimo_scan,
                            atualizado_em=excluded.atualizado_em''',
                            (texto_caminho, relativo, dados.st_size, dados.st_mtime_ns, conteudo, status, erro, scan, momento))
                        if status != 'ok':
                            logger.warning('PDF não indexado | arquivo=%s | motivo=%s', caminho, erro)
                    if status == 'sem_texto':
                        stats.sem_texto += 1
                    elif status == 'erro':
                        stats.erros += 1
                except OSError as exc:
                    stats.erros += 1
                    scan_completo = False
                    logger.warning('PDF indisponível: %s | %s', caminho, exc)
                    con.execute('UPDATE pdfs SET ultimo_scan=? WHERE caminho=?', (scan, texto_caminho))
                # Torna resultados parciais pesquisáveis e evita refazer todo o trabalho após interrupção.
                if stats.total_pdfs % 25 == 0:
                    con.commit()
                    logger.info('Indexação | verificados=%s | lidos=%s | reaproveitados=%s',
                                stats.total_pdfs, stats.lidos, stats.reaproveitados)
                informar(relativo)
        if scan_completo:
            con.execute('DELETE FROM pdfs WHERE ultimo_scan<>? AND substr(caminho,1,?) = ? COLLATE NOCASE',
                        (scan, *_filtro_raiz(raiz)))
            con.execute('INSERT OR REPLACE INTO indice_meta VALUES (?,?)',
                        ('atualizacao:' + _prefixo(raiz), datetime.now().isoformat(timespec='seconds')))
        con.commit()
    informar('')
    logger.info('Atualização finalizada | %s', vars(stats))
    return stats
