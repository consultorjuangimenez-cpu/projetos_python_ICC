"""Leitura e validação da configuração do projeto."""

import json
from pathlib import Path
from typing import Any


CAMPOS_OBRIGATORIOS = {
    "projeto": ("nome", "slug"),
    "pastas": ("documentos", "indice", "logs"),
    "busca": ("resultado_expira_minutos", "maximo_arquivos_por_zip", "memoria_zip_mb"),
    "web": ("host", "porta", "debug"),
    "logs": ("nivel", "dias_retencao"),
}


def carregar_configuracao(caminho: Path) -> dict[str, Any]:
    if not caminho.is_file():
        raise FileNotFoundError(f"Configuração não encontrada: {caminho}")

    with caminho.open("r", encoding="utf-8") as arquivo:
        config = json.load(arquivo)

    for secao, campos in CAMPOS_OBRIGATORIOS.items():
        if secao not in config:
            raise ValueError(f"Seção obrigatória ausente no config.json: {secao}")
        for campo in campos:
            if campo not in config[secao]:
                raise ValueError(f"Campo obrigatório ausente: {secao}.{campo}")
    return config


def resolver_caminho(base_dir: Path, valor: str) -> Path:
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else base_dir / caminho
