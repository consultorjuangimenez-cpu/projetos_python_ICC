import json, sys, shutil
from pathlib import Path
from .processamento import validar_certificados, carregar_senhas_manuais
from portal.settings import BASE_DIR
if __name__ == '__main__':
    pasta = Path(sys.argv[1])
    params = json.loads((pasta/'parametros.json').read_text(encoding='utf-8'))
    estado = BASE_DIR/'dados/apps/monitora_certificados'
    estado.mkdir(parents=True, exist_ok=True)
    # O motor trabalha em uma cópia, e o estado persistente só é atualizado no sucesso.
    trabalho = pasta/'trabalho'
    trabalho.mkdir()
    for nome in ('estado_certificados.json', 'Relatorio_Certificados.xlsx'):
        if (estado/nome).exists(): shutil.copy2(estado/nome, trabalho/nome)
    if params.get('correcoes'):
        import pandas as pd
        df = pd.read_excel(params['correcoes'], header=None, nrows=15, dtype=str)
        if not any({'ARQUIVO ORIGINAL','SENHA CORRIGIDA'}.issubset({str(v).strip() for v in row.dropna()}) for _, row in df.iterrows()):
            raise ValueError('O relatório de correções não contém os cabeçalhos ARQUIVO ORIGINAL e SENHA CORRIGIDA.')
        shutil.copy2(params['correcoes'], trabalho/'Relatorio_Certificados.xlsx')
    validar_certificados(params['pastas'], str(trabalho), str(trabalho))
    for nome in ('estado_certificados.json', 'Relatorio_Certificados.xlsx'):
        temp = estado/(nome+'.tmp')
        shutil.copy2(trabalho/nome, temp)
        temp.replace(estado/nome)
    shutil.copy2(trabalho/'Relatorio_Certificados.xlsx', pasta/'saida/Relatorio_Certificados.xlsx')
    (pasta/'resultado.json').write_text(json.dumps({'mensagem':'Validação concluída. Baixe o relatório desta execução.'}), encoding='utf-8')
