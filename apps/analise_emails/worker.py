import json, sys
from pathlib import Path
from . import processamento as motor
from portal.integracao import caminho

def executar(pasta):
    base = caminho('analise_emails', 'pasta_base')
    # Histórico e liberados continuam nas pastas originais; nunca são alterados.
    motor.PASTA_ENTRADA = str(pasta/'entrada')
    motor.PASTA_ANALISADOS = str(pasta/'analisados')
    motor.PASTA_SAIDA = str(pasta/'saida')
    motor.PASTA_HISTORICO = str(base/'Bloqueados'/'Historico')
    motor.ARQUIVO_EMAILS_LIBERADOS = str(base/'emails_liberados.csv')
    if not Path(motor.ARQUIVO_EMAILS_LIBERADOS).is_file():
        raise ValueError('A lista emails_liberados.csv não foi encontrada na pasta configurada. Confira antes de analisar os logs.')
    for path in (pasta/'entrada').glob('*.csv'):
        df = motor.ler_csv_ou_excel(str(path))
        if df is None or not {'Remetente','Status'}.issubset(df.columns):
            raise ValueError('CSV inválido: faltam as colunas Remetente e Status.')
    motor.processar_logs()
    return 'Análise concluída. Revise os CSVs antes de importar qualquer bloqueio.' if list((pasta/'saida').glob('*.csv')) else 'Nenhum recebimento foi encontrado nos arquivos enviados.'

if __name__ == '__main__':
    pasta = Path(sys.argv[1])
    mensagem = executar(pasta)
    (pasta/'resultado.json').write_text(json.dumps({'mensagem':mensagem}, ensure_ascii=False), encoding='utf-8')
