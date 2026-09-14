from portal.tarefas import criar_app, arquivo_enviado

def preparar(req, pasta):
    logs = req.files.getlist('logs')
    if not logs or not any(f.filename for f in logs):
        raise ValueError('Selecione ao menos um CSV de recebimentos.')
    entrada = pasta / 'entrada'
    entrada.mkdir()
    for i, arquivo in enumerate(logs):
        if not arquivo.filename or not arquivo.filename.lower().endswith('.csv'):
            raise ValueError('Envie somente logs em CSV.')
        arquivo.save(entrada / f'log_{i+1}.csv')
    return {'entrada': str(entrada)}

app = criar_app(__name__, 'analise_emails', 'Análise de logs de e-mail',
    'Envie os logs de recebimentos para gerar a análise e a lista de bloqueios. A lista é entregue para revisão; o portal não aplica bloqueios no provedor.',
    '<label>Logs CSV</label><input type="file" name="logs" accept=".csv" multiple required>',
    preparar, 'apps.analise_emails.worker')
