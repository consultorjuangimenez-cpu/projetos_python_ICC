"""Funções auxiliares para gerar ZIP sem substituir nomes duplicados."""

from pathlib import Path


def nome_zip_disponivel(nome_original: str, nomes_usados: set[str]) -> str:
    caminho = Path(nome_original)
    candidato = caminho.name
    contador = 2
    while candidato.casefold() in nomes_usados:
        candidato = f"{caminho.stem} ({contador}){caminho.suffix}"
        contador += 1
    nomes_usados.add(candidato.casefold())
    return candidato
