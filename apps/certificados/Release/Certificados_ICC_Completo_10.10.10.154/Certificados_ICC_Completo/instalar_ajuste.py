"""Copia o complemento HTTPS e instala o painel somente se ele ainda nao existir."""
import importlib.util
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
BASE=Path(__file__).resolve().parent

def main(target):
    root=Path(target).resolve()
    if not (root/'portal/servidor.py').is_file():raise ValueError('Pasta do Portal_Apps incorreta.')
    if not (root/'apps/certificados/app.py').is_file():
        spec=importlib.util.spec_from_file_location('instalador_certificados',BASE/'modulo_certificados/instalar_no_portal.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.install(root)
    else:print('Modulo de certificados existente mantido. Nenhum arquivo dele foi substituido.')
    destination=root/'https_icc';source=BASE/'https_icc'
    backup=root/'backups_atualizacao'/('complemento_https_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    for p in source.rglob('*'):
        if p.is_file():
            relative=p.relative_to(source);out=destination/relative
            if out.exists():
                saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(out,saved)
            out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out)
    print('Complemento copiado para: '+str(destination))
    print('Backup dos arquivos anteriores: '+str(backup))
    print('Siga COMECE_AQUI.md: baixe caddy.exe e execute os BATs numerados.')

if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception as exc:print('ERRO:',exc);sys.exit(1)
