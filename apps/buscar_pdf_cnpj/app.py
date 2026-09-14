# -*- coding: utf-8 -*-
"""Aplicação web para localizar e baixar PDFs pelo CNPJ contido no documento.

Histórico:
    1.1.1 - Busca local, atualização em segundo plano e envio robusto do ZIP.
"""

import json
import sqlite3
from contextlib import closing
import secrets
import tempfile
import threading
import time
import zipfile
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, g

from .src.cnpj import CNPJInvalido, formatar_cnpj, validar_cnpj
from .src.configuracao import carregar_configuracao, resolver_caminho
from .src.indice_pdf import DocumentoPDF, buscar_pdfs_por_cnpj, atualizar_indice, informacoes_indice, preparar_indice
from .src.logs import configurar_logger
from .src.zip_utils import nome_zip_disponivel
from .versao import __version__


BASE_DIR = Path(__file__).resolve().parent
CONFIG = carregar_configuracao(BASE_DIR / "config.json")
from portal.integracao import caminho
from portal.settings import BASE_DIR as PORTAL_DIR
PASTA_DOCUMENTOS = caminho("pdf_cnpj", "pasta_documentos", CONFIG["pastas"]["documentos"])
CAMINHO_INDICE = PORTAL_DIR / "dados/apps/buscar_pdf_cnpj/indice_pdfs.sqlite3"
PASTA_LOGS = PORTAL_DIR / "logs/buscar_pdf_cnpj"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)
CAMINHO_INDICE.parent.mkdir(parents=True, exist_ok=True)

LOGGER = configurar_logger(
    nome=CONFIG["projeto"]["slug"],
    pasta_logs=PASTA_LOGS,
    nivel=CONFIG["logs"]["nivel"],
    dias_retencao=CONFIG["logs"]["dias_retencao"],
)

# A v1.0 gravava Path.resolve(), que pode transformar F: no caminho UNC.
# A v1.1 filtrava apenas F:. Confirma e normaliza essa equivalência uma vez.
try:
    preparar_indice(PASTA_DOCUMENTOS, CAMINHO_INDICE, LOGGER)
except Exception:
    LOGGER.exception("Não foi possível preparar a compatibilidade do índice existente")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

_indice_lock = threading.Lock()
_estado_lock = threading.Lock()
_estado = {"executando": False, "erro": None, "verificados": 0,
           "lidos": 0, "reaproveitados": 0, "arquivo_atual": ""}
CAMINHO_RESULTADOS = CAMINHO_INDICE.with_name("resultados_buscas.sqlite3")


def _conectar_resultados():
    con = sqlite3.connect(CAMINHO_RESULTADOS, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS resultados (token TEXT PRIMARY KEY, usuario TEXT, criado REAL, dados TEXT)")
    con.execute("DELETE FROM resultados WHERE criado < ?", (
        time.time() - CONFIG["busca"]["resultado_expira_minutos"] * 60,))
    return con


def _guardar_resultado(cnpj, documentos):
    token = secrets.token_urlsafe(24)
    dados = {"cnpj": cnpj, "documentos": [
        {"caminho": str(d.caminho), "caminho_relativo": d.caminho_relativo, "tamanho": d.tamanho}
        for d in documentos]}
    with closing(_conectar_resultados()) as con, con:
        con.execute("INSERT INTO resultados VALUES (?,?,?,?)", (
            token, str(g.usuario["id"]), time.time(), json.dumps(dados)))
    return token


def _obter_resultado(token):
    with closing(_conectar_resultados()) as con, con:
        registro = con.execute("SELECT dados FROM resultados WHERE token=? AND usuario=?",
                               (token, str(g.usuario["id"]))).fetchone()
    if not registro:
        return None
    dados = json.loads(registro[0])
    dados["documentos"] = [DocumentoPDF(Path(d["caminho"]), d["caminho_relativo"], d["tamanho"])
                             for d in dados["documentos"]]
    return dados


def _iniciar_atualizacao():
    if not _indice_lock.acquire(blocking=False):
        return False
    with _estado_lock:
        _estado.update(executando=True, erro=None, verificados=0, lidos=0,
                       reaproveitados=0, arquivo_atual="", erros=0, sem_texto=0)

    def progresso(dados):
        with _estado_lock:
            _estado.update(dados)
            _estado["verificados"] = dados["total_pdfs"]

    def executar():
        try:
            preparar_indice(PASTA_DOCUMENTOS, CAMINHO_INDICE, LOGGER)
            atualizar_indice(PASTA_DOCUMENTOS, CAMINHO_INDICE, LOGGER, progresso)
        except Exception:
            LOGGER.exception("Falha na atualização do índice")
            with _estado_lock:
                _estado["erro"] = "Não foi possível atualizar o índice. Verifique o acesso à pasta e o log."
        finally:
            with _estado_lock:
                _estado["executando"] = False
            _indice_lock.release()
    try:
        threading.Thread(target=executar, name="indice-pdf", daemon=True).start()
    except Exception:
        with _estado_lock:
            _estado["executando"] = False
        _indice_lock.release()
        raise
    return True


@app.get("/estado-indice")
def estado_indice():
    with _estado_lock:
        estado = dict(_estado)
    resposta = jsonify({**estado, **informacoes_indice(CAMINHO_INDICE, PASTA_DOCUMENTOS)})
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.post("/atualizar-indice")
def solicitar_atualizacao():
    iniciado = _iniciar_atualizacao()
    return jsonify(iniciado=iniciado), 202


def _tamanho_legivel(tamanho: int) -> str:
    valor = float(tamanho)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.0f} {unidade}" if unidade == "B" else f"{valor:.1f} {unidade}"
        valor /= 1024
    return f"{tamanho} B"


def _documento_dentro_da_raiz(caminho: Path) -> bool:
    try:
        raiz_real = PASTA_DOCUMENTOS.resolve(strict=True)
        caminho_real = caminho.resolve(strict=True)
        return caminho_real.is_file() and caminho_real.is_relative_to(raiz_real)
    except (OSError, RuntimeError):
        return False


@app.get("/")
def pagina_inicial():
    return render_template(
        "index.html",
        versao=__version__,
        pasta_documentos=str(PASTA_DOCUMENTOS),
    )


@app.post("/buscar")
def buscar():
    valor_informado = request.form.get("cnpj", "")

    try:
        cnpj = validar_cnpj(valor_informado)
    except CNPJInvalido as exc:
        return render_template(
            "index.html",
            versao=__version__,
            pasta_documentos=str(PASTA_DOCUMENTOS),
            erro=str(exc),
            cnpj_digitado=valor_informado,
        ), 400

    info = informacoes_indice(CAMINHO_INDICE, PASTA_DOCUMENTOS)
    # Um índice da versão anterior é utilizável imediatamente, sem reler a rede.
    if info["total_banco"] == 0 and not info["ultima_atualizacao"]:
        _iniciar_atualizacao()

    inicio = time.monotonic()
    try:
        documentos, estatisticas = buscar_pdfs_por_cnpj(
            raiz=PASTA_DOCUMENTOS,
            caminho_indice=CAMINHO_INDICE,
            cnpj=cnpj,
            logger=LOGGER,
        )
    except Exception as exc:
        LOGGER.exception("Falha na busca do CNPJ %s: %s", cnpj, exc)
        return render_template(
            "index.html",
            versao=__version__,
            pasta_documentos=str(PASTA_DOCUMENTOS),
            erro="Não foi possível concluir a busca. Consulte o log para detalhes.",
            cnpj_digitado=formatar_cnpj(cnpj),
        ), 500

    token = _guardar_resultado(cnpj, documentos)
    duracao = time.monotonic() - inicio
    LOGGER.info(
        "Busca concluída | cnpj=%s | encontrados=%s | total_pdfs=%s | "
        "lidos=%s | reaproveitados=%s | sem_texto=%s | erros=%s | segundos=%.2f",
        cnpj,
        len(documentos),
        estatisticas.total_pdfs,
        estatisticas.lidos,
        estatisticas.reaproveitados,
        estatisticas.sem_texto,
        estatisticas.erros,
        duracao,
    )

    itens = [
        {
            "id": indice,
            "nome": documento.caminho.name,
            "caminho_relativo": documento.caminho_relativo,
            "tamanho": _tamanho_legivel(documento.tamanho),
        }
        for indice, documento in enumerate(documentos)
    ]

    return render_template(
        "index.html",
        versao=__version__,
        pasta_documentos=str(PASTA_DOCUMENTOS),
        cnpj_digitado=formatar_cnpj(cnpj),
        cnpj_encontrado=formatar_cnpj(cnpj),
        resultados=itens,
        token=token,
        estatisticas=estatisticas,
        duracao=duracao,
        indice_parcial=_estado["executando"],
        indice_incompativel=info["total_banco"] > 0 and info["total_pdfs"] == 0,
    )


@app.post("/baixar")
def baixar():
    token = request.form.get("token", "")
    resultado = _obter_resultado(token)
    if not resultado:
        abort(410, description="A pesquisa expirou. Faça uma nova busca.")

    ids_recebidos = request.form.getlist("arquivos")
    if not ids_recebidos:
        abort(400, description="Selecione pelo menos um PDF.")

    limite = CONFIG["busca"]["maximo_arquivos_por_zip"]
    if len(set(ids_recebidos)) > limite:
        abort(400, description=f"O limite por download é de {limite} arquivos.")

    documentos: list[DocumentoPDF] = resultado["documentos"]
    selecionados: list[DocumentoPDF] = []
    ids_unicos: set[int] = set()

    for valor in ids_recebidos:
        try:
            indice = int(valor)
        except ValueError:
            abort(400, description="Seleção de arquivo inválida.")
        if not 0 <= indice < len(documentos):
            abort(400, description="Seleção de arquivo inválida.")
        if indice in ids_unicos:
            continue
        ids_unicos.add(indice)
        documento = documentos[indice]
        if _documento_dentro_da_raiz(documento.caminho):
            selecionados.append(documento)
        else:
            LOGGER.warning("Arquivo indisponível ou fora da raiz: %s", documento.caminho)
            abort(404, description="Um PDF selecionado foi removido ou está inacessível. Atualize o índice e refaça a busca.")

    if not selecionados:
        abort(404, description="Nenhum dos arquivos selecionados está disponível.")

    arquivo_zip = tempfile.SpooledTemporaryFile(
        max_size=CONFIG["busca"]["memoria_zip_mb"] * 1024 * 1024,
        mode="w+b",
    )
    nomes_usados: set[str] = set()
    try:
        # PDFs já costumam ser comprimidos. Evita gastar CPU comprimindo novamente.
        with zipfile.ZipFile(arquivo_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zip_saida:
            for documento in selecionados:
                nome_no_zip = nome_zip_disponivel(documento.caminho.name, nomes_usados)
                zip_saida.write(documento.caminho, arcname=nome_no_zip)
        tamanho = arquivo_zip.tell()
        arquivo_zip.seek(0)
    except Exception:
        arquivo_zip.close()
        LOGGER.exception("Falha ao gerar ZIP")
        abort(503, description="Não foi possível ler todos os PDFs para gerar o ZIP. Verifique a rede e tente novamente.")

    cnpj = resultado["cnpj"]
    LOGGER.info("ZIP gerado | cnpj=%s | arquivos=%s | bytes=%s", cnpj, len(selecionados), tamanho)

    def enviar_blocos():
        try:
            while True:
                bloco = arquivo_zip.read(1024 * 1024)
                if not bloco:
                    break
                yield bloco
        finally:
            arquivo_zip.close()

    # Envia blocos com tamanho explícito, sem depender de file_wrapper do servidor do portal.
    resposta = Response(enviar_blocos(), mimetype="application/zip", headers={
        "Content-Disposition": f'attachment; filename="PDFs_CNPJ_{cnpj}.zip"',
        "Content-Length": str(tamanho),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
    resposta.call_on_close(arquivo_zip.close)
    return resposta


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(410)
@app.errorhandler(503)
def erro_solicitacao(exc):
    return render_template(
        "index.html",
        versao=__version__,
        pasta_documentos=str(PASTA_DOCUMENTOS),
        erro=getattr(exc, "description", "Solicitação inválida."),
    ), exc.code


