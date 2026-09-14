"""Cadastro inicial somente no console do notebook, sem senha padrão."""
from getpass import getpass


def configurar(users):
    if users.has_admin():
        return
    if users.list():
        raise RuntimeError('Não existe administrador ativo. Restaure um backup válido de dados antes de iniciar.')
    print('\nPRIMEIRO ACESSO: cadastre o administrador do portal.')
    print('A senha nao aparece enquanto voce digita. Minimo: 4 caracteres.')
    while True:
        username=input('Login do administrador: ').strip()
        name=input('Nome: ').strip()
        password=getpass('Senha: ')
        confirmation=getpass('Repita a senha: ')
        if password != confirmation:
            print('As senhas nao conferem. Tente novamente.')
            continue
        try:
            users.bootstrap(username,name,password)
        except ValueError as exc:
            print(str(exc))
            continue
        print('Administrador cadastrado. Iniciando o portal...')
        return
