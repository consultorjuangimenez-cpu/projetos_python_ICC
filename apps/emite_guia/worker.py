import json, sys, logging, zipfile
from pathlib import Path
from .processamento import rodar_automacao_background
if __name__ == '__main__':
    pasta = Path(sys.argv[1])
    params = json.loads((pasta/'parametros.json').read_text(encoding='utf-8'))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    pdfs = pasta/'pdfs'
    itens = rodar_automacao_background(params['dados'], params['planilha'], str(pdfs))
    arquivos = sorted(pdfs.glob('*.pdf'))
    validos = []
    for arquivo in arquivos:
        with arquivo.open('rb') as stream:
            if stream.read(4) == b'%PDF': validos.append(arquivo)
    if validos:
        with zipfile.ZipFile(pasta/'saida/Guias.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for p in validos: z.write(p,p.name)
    total = len(itens)
    faltantes = [str(i['linha_num']) for i in itens if not any(p.name.startswith(f"Guia_Linha_{i['linha_num']}_{i['chave'][:10]}") for p in validos)]
    resumo = f'{len(validos)} PDF(s) válido(s) para {total} linha(s).'
    if faltantes:
        resumo += ' Linhas sem PDF: ' + ', '.join(faltantes) + '. Confira a SEFAZ antes de reemitir.'
    (pasta/'saida/Resumo.txt').write_text(resumo, encoding='utf-8')
    (pasta/'resultado.json').write_text(json.dumps({'mensagem':resumo}, ensure_ascii=False), encoding='utf-8')
