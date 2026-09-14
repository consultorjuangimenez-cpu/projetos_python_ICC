from __future__ import annotations

import tempfile
from portal.settings import CLIENTS_ROOT, BASE_DIR
import logging
import zipfile
from pathlib import Path
from typing import Final

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_file,
)


LOG_DIR: Final[Path] = BASE_DIR / "logs" / "buscar_pdf"



app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

@app.after_request
def protect_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.endpoint != "index" and response.mimetype == "text/html" and not response.headers.get("X-Portal-Access"):
        response.mimetype = "text/plain"
    return response


LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
    handlers=[
        logging.FileHandler(
            LOG_DIR / "buscador_documentos_v2.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

@app.errorhandler(OSError)
def filesystem_error(exc):
    logger.exception("Falha de acesso ao sistema de arquivos.")
    return Response("Não foi possível acessar os documentos. Consulte o log no servidor.", status=500, mimetype="text/plain")



def is_client_folder(folder: Path) -> bool:
    """Verifica se uma pasta deve ser considerada cliente.

    Uma pasta de cliente precisa ser um diretório e seu nome deve
    começar com uma letra.

    Args:
        folder: Pasta que será analisada.

    Returns:
        True quando a pasta atender às regras de cliente.
    """
    if not folder.is_dir():
        return False

    name = folder.name.strip()

    if not name:
        return False

    return name[0].isalpha()


def get_clients() -> list[str]:
    """Obtém a lista de clientes disponíveis.

    Returns:
        Nomes das pastas de clientes em ordem alfabética.

    Raises:
        FileNotFoundError: Quando a pasta-base não existir.
        NotADirectoryError: Quando o caminho configurado não for pasta.
        OSError: Quando ocorrer erro ao acessar o diretório.
    """
    if not CLIENTS_ROOT.exists():
        raise FileNotFoundError(
            f"Pasta principal não encontrada: {CLIENTS_ROOT}"
        )

    if not CLIENTS_ROOT.is_dir():
        raise NotADirectoryError(
            f"O caminho não é uma pasta: {CLIENTS_ROOT}"
        )

    clients: list[str] = []

    for folder in CLIENTS_ROOT.iterdir():
        try:
            if is_client_folder(folder) and folder.resolve().parent == CLIENTS_ROOT.resolve():
                clients.append(folder.name)
        except OSError as exc:
            logger.warning(
                "Não foi possível analisar a pasta '%s': %s",
                folder,
                exc,
            )

    clients.sort(key=str.casefold)

    return clients


def get_client_folder(client_name: str) -> Path:
    """Localiza e valida a pasta de um cliente.

    Args:
        client_name: Nome exato do cliente selecionado.

    Returns:
        Caminho validado da pasta do cliente.

    Raises:
        ValueError: Quando o cliente não estiver na lista permitida.
    """
    client_name = client_name.strip()

    if not client_name:
        raise ValueError("Cliente não informado.")

    available_clients = get_clients()

    client_lookup = {
        name.casefold(): name
        for name in available_clients
    }

    real_name = client_lookup.get(client_name.casefold())

    if real_name is None:
        raise ValueError(
            "O cliente informado não foi encontrado."
        )

    client_folder = CLIENTS_ROOT / real_name

    resolved_root = CLIENTS_ROOT.resolve()
    resolved_client = client_folder.resolve()

    if resolved_client.parent != resolved_root:
        raise ValueError(
            "A pasta selecionada não pertence ao diretório permitido."
        )

    return resolved_client


def get_client_pdfs(client_folder: Path) -> list[dict[str, str]]:
    """Lista os PDFs existentes na pasta do cliente.

    A pesquisa também considera subpastas.

    Args:
        client_folder: Pasta validada do cliente.

    Returns:
        Lista contendo nome e caminho relativo dos PDFs.
    """
    pdfs: list[dict[str, str]] = []

    try:
        files = client_folder.rglob("*")

        for file_path in files:
            try:
                if not file_path.is_file():
                    continue

                if file_path.suffix.casefold() != ".pdf":
                    continue

                if not file_path.resolve().is_relative_to(client_folder.resolve()):
                    continue

                relative_path = file_path.relative_to(
                    client_folder
                )

                pdfs.append(
                    {
                        "name": file_path.name,
                        "path": str(relative_path),
                    }
                )

            except OSError as exc:
                logger.warning(
                    "Erro ao analisar arquivo '%s': %s",
                    file_path,
                    exc,
                )

    except OSError as exc:
        logger.error(
            "Erro ao pesquisar PDFs em '%s': %s",
            client_folder,
            exc,
        )
        raise

    pdfs.sort(
        key=lambda item: item["path"].casefold()
    )

    return pdfs


def get_unique_zip_name(
    file_path: Path,
    used_names: set[str],
) -> str:
    """Cria um nome único para um arquivo dentro do ZIP.

    Args:
        file_path: Arquivo que será incluído.
        used_names: Nomes já utilizados no ZIP.

    Returns:
        Nome único do arquivo.
    """
    original_name = file_path.name

    if original_name.casefold() not in used_names:
        used_names.add(original_name.casefold())
        return original_name

    stem = file_path.stem
    suffix = file_path.suffix

    counter = 2

    while True:
        candidate = f"{stem}_{counter}{suffix}"

        if candidate.casefold() not in used_names:
            used_names.add(candidate.casefold())
            return candidate

        counter += 1


def validate_selected_pdf(
    client_folder: Path,
    relative_path: str,
) -> Path:
    """Valida um PDF selecionado pelo navegador.

    Args:
        client_folder: Pasta validada do cliente.
        relative_path: Caminho relativo recebido do formulário.

    Returns:
        Caminho absoluto e validado do PDF.

    Raises:
        ValueError: Quando o caminho for inválido.
        FileNotFoundError: Quando o arquivo não existir.
    """
    if not relative_path.strip():
        raise ValueError("Caminho de documento vazio.")

    candidate = (
        client_folder / relative_path
    ).resolve()

    client_resolved = client_folder.resolve()

    try:
        candidate.relative_to(client_resolved)
    except ValueError as exc:
        raise ValueError(
            "Documento fora da pasta permitida."
        ) from exc

    if not candidate.exists():
        raise FileNotFoundError(
            f"Documento não encontrado: {candidate.name}"
        )

    if not candidate.is_file():
        raise ValueError(
            f"O caminho não é um arquivo: {candidate.name}"
        )

    if candidate.suffix.casefold() != ".pdf":
        raise ValueError(
            f"O arquivo não é PDF: {candidate.name}"
        )

    return candidate


@app.get("/")
def index() -> str:
    """Exibe a página principal."""
    try:
        clients = get_clients()
        error = None

        logger.info(
            "Lista de clientes carregada | total=%d",
            len(clients),
        )

    except (
        FileNotFoundError,
        NotADirectoryError,
        OSError,
    ) as exc:
        logger.exception(
            "Erro ao carregar clientes."
        )

        clients = []
        error = str(exc)

    return render_template(
        "index.html",
        clients=clients,
        error=error,
    )


@app.get("/api/documentos")
def api_documents() -> Response:
    """Retorna os PDFs do cliente selecionado."""
    client_name = request.args.get(
        "cliente",
        "",
    ).strip()

    try:
        client_folder = get_client_folder(
            client_name
        )

        documents = get_client_pdfs(
            client_folder
        )

    except (
        ValueError,
        FileNotFoundError,
        NotADirectoryError,
    ) as exc:
        logger.warning(
            "Falha ao listar documentos | cliente=%s | erro=%s",
            client_name,
            exc,
        )

        return jsonify(
            {
                "success": False,
                "message": str(exc),
                "documents": [],
            }
        ), 400

    except OSError as exc:
        logger.exception(
            "Erro de acesso aos documentos do cliente '%s'.",
            client_name,
        )

        return jsonify(
            {
                "success": False,
                "message": (
                    "Não foi possível acessar a pasta do cliente. "
                    f"Detalhes: {exc}"
                ),
                "documents": [],
            }
        ), 500

    logger.info(
        "Documentos carregados | cliente=%s | total=%d",
        client_folder.name,
        len(documents),
    )

    return jsonify(
        {
            "success": True,
            "client": client_folder.name,
            "documents": documents,
        }
    )


@app.post("/download")
def download_documents() -> Response | tuple[str, int]:
    """Cria o ZIP contendo os PDFs selecionados."""
    client_name = request.form.get(
        "cliente",
        "",
    ).strip()

    selected_documents = request.form.getlist(
        "documentos"
    )

    selected_documents = list(dict.fromkeys(selected_documents))
    if len(selected_documents) > 500:
        return "Selecione no máximo 500 documentos por download.", 400

    if not selected_documents:
        return (
            "Selecione pelo menos um documento.",
            400,
        )

    try:
        client_folder = get_client_folder(
            client_name
        )

        validated_files: list[Path] = []

        for relative_path in selected_documents:
            file_path = validate_selected_pdf(
                client_folder=client_folder,
                relative_path=relative_path,
            )

            validated_files.append(file_path)

    except (
        ValueError,
        FileNotFoundError,
        NotADirectoryError,
    ) as exc:
        logger.warning(
            "Seleção inválida | cliente=%s | erro=%s",
            client_name,
            exc,
        )

        return str(exc), 400

    if sum(file.stat().st_size for file in validated_files) > 200 * 1024 * 1024:
        return "A seleção excede 200 MB. Divida o download em lotes menores.", 400

    zip_buffer = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    used_names: set[str] = set()

    try:
        with zipfile.ZipFile(
            zip_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zip_file:
            for pdf_path in validated_files:
                zip_name = get_unique_zip_name(
                    file_path=pdf_path,
                    used_names=used_names,
                )

                zip_file.write(
                    filename=pdf_path,
                    arcname=zip_name,
                )

    except OSError as exc:
        logger.exception(
            "Erro ao gerar ZIP para '%s'.",
            client_folder.name,
        )

        zip_buffer.close()
        return (
            "Erro ao gerar arquivo ZIP. Consulte o log no servidor.",
            500,
        )

    zip_buffer.seek(0)

    safe_client_name = "".join(
        character
        if character.isalnum()
        or character in (" ", "-", "_")
        else "_"
        for character in client_folder.name
    ).strip()

    download_name = (
        f"Documentos - {safe_client_name}.zip"
    )

    logger.info(
        "ZIP gerado | cliente=%s | arquivos=%d",
        client_folder.name,
        len(validated_files),
    )

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_name,
    )



def main() -> None:
    from portal.servidor import main as start_portal
    start_portal()


if __name__ == "__main__":
    main()
