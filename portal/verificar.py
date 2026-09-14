"""Diagnóstico local de configuração, sem iniciar aplicações nem executar rotinas."""
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import json
from .settings import BASE_DIR, CONFIG
from .integracao import CONFIG_APPS, caminho


def main():
    print('VERIFICACAO DO PORTAL\n')
    problemas = 0
    for line in (BASE_DIR/'requirements.txt').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'): continue
        name, required = line.split('==',1)
        try:
            installed = version(name)
            certo = installed == required
            print(f'{"OK" if certo else "AJUSTAR"}: {name} {installed} (pacote: {required})')
            problemas += not certo
        except PackageNotFoundError:
            print(f'AUSENTE: {name}. Execute 1_instalar.bat.')
            problemas += 1
    print('\nPASTAS E ARQUIVOS (acesso da conta atual do Windows)')
    checks = [('PDFs por cliente',Path(CONFIG.get('documentos','pasta_clientes'))),
              ('Relacoes RCF',Path(CONFIG.get('amanda','pasta_rcf',fallback='')))]
    for section,key in [('pdf_cnpj','pasta_documentos'),('sieg','pasta_xmls'),('analise_emails','pasta_base'),('analisa_certificados','pasta_cpf'),('analisa_certificados','pasta_cnpj'),('monitora_certificados','pasta_cpf'),('monitora_certificados','pasta_cnpj'),('aberturas','planilha')]:
        checks.append((section+'.'+key,caminho(section,key)))
    for name,path in checks:
        if not path.is_absolute():path=BASE_DIR/path
        try:exists=path.exists()
        except OSError:exists=False
        print(f'{"OK" if exists else "INACESSIVEL"}: {name}: {path}')
        problemas += not exists
    print('\nCADASTRO')
    for item in json.loads((BASE_DIR/'aplicativos.json').read_text(encoding='utf-8-sig')):
        file=BASE_DIR.joinpath(*item['modulo'].split('.')).with_suffix('.py')
        print(f'{"ATIVO" if item.get("ativo",True) else "INATIVO"}: {item["nome"]} | arquivo {"OK" if file.is_file() else "AUSENTE"}')
        problemas += not file.is_file()
    print('\nNenhum documento foi processado; nenhum e-mail ou guia foi emitido.')
    print(f'Itens a conferir: {problemas}. Pastas inacessíveis afetam os aplicativos correspondentes.')
    return 1 if problemas else 0

if __name__=='__main__':
    raise SystemExit(main())
