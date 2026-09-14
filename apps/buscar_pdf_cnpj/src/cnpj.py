"""Normalização, validação e formatação de CNPJ."""

import re


class CNPJInvalido(ValueError):
    pass


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _calcular_digito(base: str, pesos: tuple[int, ...]) -> str:
    soma = sum(int(digito) * peso for digito, peso in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar_cnpj(valor: str) -> str:
    cnpj = somente_digitos(valor)
    if len(cnpj) != 14:
        raise CNPJInvalido("Informe um CNPJ com 14 dígitos.")
    if cnpj == cnpj[0] * 14:
        raise CNPJInvalido("O CNPJ informado é inválido.")

    primeiro = _calcular_digito(cnpj[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    segundo = _calcular_digito(cnpj[:12] + primeiro, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    if cnpj[-2:] != primeiro + segundo:
        raise CNPJInvalido("O CNPJ informado é inválido.")
    return cnpj


def formatar_cnpj(cnpj: str) -> str:
    cnpj = somente_digitos(cnpj)
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
