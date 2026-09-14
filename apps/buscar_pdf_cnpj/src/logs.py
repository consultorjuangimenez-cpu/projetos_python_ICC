"""Configuração centralizada dos logs."""

import logging
from datetime import datetime, timedelta
from pathlib import Path


class LoggerProjeto(logging.LoggerAdapter):
    """Logger que também informa o arquivo utilizado nesta execução."""

    def __init__(self, logger: logging.Logger, arquivo_log: Path):
        super().__init__(logger, {})
        self.arquivo_log = arquivo_log


def _remover_logs_antigos(pasta_logs: Path, dias_retencao: int) -> None:
    limite = datetime.now() - timedelta(days=dias_retencao)
    for caminho in pasta_logs.glob("*.log"):
        try:
            alterado_em = datetime.fromtimestamp(caminho.stat().st_mtime)
            if alterado_em < limite:
                caminho.unlink()
        except OSError:
            continue


def configurar_logger(
    nome: str,
    pasta_logs: Path,
    nivel: str = "INFO",
    dias_retencao: int = 90,
) -> LoggerProjeto:
    pasta_logs.mkdir(parents=True, exist_ok=True)
    _remover_logs_antigos(pasta_logs, dias_retencao)

    arquivo_log = pasta_logs / f"{nome}_{datetime.now():%Y-%m-%d}.log"
    logger = logging.getLogger(nome)
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    arquivo_handler = logging.FileHandler(arquivo_log, encoding="utf-8")
    arquivo_handler.setFormatter(formato)
    logger.addHandler(arquivo_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formato)
    logger.addHandler(console_handler)

    return LoggerProjeto(logger, arquivo_log)
