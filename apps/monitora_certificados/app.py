from portal.tarefas import criar_app, arquivo_enviado
from portal.integracao import caminho

def preparar(req, pasta):
    pastas = {str(caminho('monitora_certificados', 'pasta_cpf')): 'CPF', str(caminho('monitora_certificados', 'pasta_cnpj')): 'CNPJ'}
    from pathlib import Path
    for p in pastas:
        if not Path(p).is_dir():
            raise ValueError('Uma pasta de certificados está indisponível. Confira config_apps.ini e o acesso do servidor.')
    correcoes = arquivo_enviado(req, 'correcoes', pasta/'correcoes', {'.xlsx'}, required=False)
    return {'pastas': pastas, 'correcoes': correcoes}

app = criar_app(__name__, 'monitora_certificados', 'Validade dos certificados', 'Lê o vencimento real dos certificados nas pastas configuradas e gera o relatório com dashboard. Esta execução não realiza o Robocopy do BAT antigo.', '<p class="note">O relatório contém senhas de certificados. Libere este aplicativo somente aos responsáveis.</p><label>Relatório anterior com SENHA CORRIGIDA (opcional)</label><input type="file" name="correcoes" accept=".xlsx">', preparar, 'apps.monitora_certificados.worker')
