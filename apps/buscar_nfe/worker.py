"""Motor v6.3 adaptado ao protocolo de tarefas do Portal Apps."""
import json
from collections import Counter
import os
import re
import sys
import zipfile
from pathlib import Path
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

VERSAO_APP = "v6.3-portal"

PADRAO_CHAVE = r"[0-9]{6}[A-Z0-9]{12}[0-9]{26}"


def extrair_info_chave(chave):
    """Preserva letras do CNPJ; valida formato, sem validar dígito verificador."""
    chave_limpa = re.sub(r"[\s./-]", "", str(chave).strip()).upper()
    if re.fullmatch(PADRAO_CHAVE, chave_limpa):
        return chave_limpa, str(int(chave_limpa[25:34]))
    return None, None


def extrair_chave_do_xml(caminho_xml):
    """Exige uma NF-e completa e lê seu Id, independentemente do namespace."""
    if Path(caminho_xml).stat().st_size > 20 * 1024 * 1024:
        raise ValueError("XML excede o limite de 20 MB.")
    root = ET.parse(caminho_xml).getroot()
    for elemento in root.iter():
        if elemento.tag.rsplit("}", 1)[-1] == "infNFe":
            identificador = elemento.get("Id", "")
            if identificador.startswith("NFe"):
                return extrair_info_chave(identificador[3:])[0]
    return None


def normalizar_tipo(texto):
    return texto.casefold().replace("í", "i").rstrip("s")


def buscar_arquivos(documento, tipo, chaves, raiz_hub, ano):
    """Busca em três etapas, sempre complementando apenas as chaves pendentes."""
    raiz_hub = Path(raiz_hub).resolve(strict=True)
    if not raiz_hub.is_dir():
        raise ValueError("Pasta de XMLs indisponível.")
    melhores = {}
    erros = []
    recusados = 0
    principais = {"entrada"} if tipo == "Entrada" else {"saida"} if tipo == "Saida" else {"entrada", "saida"}
    complementares = {"saida"} if tipo == "Entrada" else {"entrada"} if tipo == "Saida" else {"entrada", "saida"}

    def varrer(pasta, tipos, procuradas, origem):
        nonlocal recusados
        numeros = {str(int(ch[25:34])) for ch in procuradas}
        pasta = Path(pasta)
        if pasta.is_symlink() or not pasta.resolve().is_relative_to(raiz_hub):
            erros.append(f"Pasta fora da raiz permitida ou link ignorado: {pasta}")
            return
        if not os.path.isdir(pasta):
            erros.append(f"Pasta ausente ou inacessível: {pasta}")
            return
        for raiz, subpastas, arquivos in os.walk(pasta, onerror=lambda e: erros.append(str(e))):
            partes = os.path.relpath(raiz, pasta).split(os.sep)
            # Mantém os dois padrões: CNPJ/ANO/TIPO e CNPJ/TIPO/ANO.
            subpastas[:] = [p for p in subpastas
                            if not Path(raiz, p).is_symlink()
                            and Path(raiz, p).resolve().is_relative_to(raiz_hub)
                            and not (re.fullmatch(r"\d{4}", p) and p != ano)
                            and not (normalizar_tipo(p) in {"entrada", "saida"}
                                     and normalizar_tipo(p) not in tipos)]
            if ano not in partes or not any(normalizar_tipo(p) in tipos for p in partes):
                continue
            nomes = {nome.casefold(): nome for nome in arquivos}
            for arq in arquivos:
                nome, ext = os.path.splitext(arq)
                if ext.casefold() != ".xml":
                    continue
                chave_nome, _ = extrair_info_chave(nome)
                numero_nome = str(int(nome)) if re.fullmatch(r"[0-9]{1,9}", nome) else None
                if numero_nome not in numeros and chave_nome not in procuradas:
                    continue
                caminho = os.path.join(raiz, arq)
                try:
                    caminho = Path(caminho)
                    if caminho.is_symlink() or not caminho.resolve().is_relative_to(raiz_hub):
                        erros.append(f"XML fora da raiz permitida ou link ignorado: {caminho}")
                        continue
                    chave_xml = extrair_chave_do_xml(caminho)
                    if chave_xml not in procuradas:
                        recusados += 1
                        continue
                    mtime = os.path.getmtime(caminho)
                    if chave_xml not in melhores or mtime > melhores[chave_xml]["mtime"]:
                        pdf = nomes.get((nome + ".pdf").casefold())
                        if pdf:
                            caminho_pdf = Path(raiz, pdf)
                            if caminho_pdf.is_symlink() or not caminho_pdf.resolve().is_relative_to(raiz_hub):
                                erros.append(f"PDF fora da raiz permitida ou link ignorado: {caminho_pdf}")
                                pdf = None
                        melhores[chave_xml] = {
                            "xml": caminho,
                            "pdf": os.path.join(raiz, pdf) if pdf else None,
                            "mtime": mtime, "origem": origem,
                        }
                except (OSError, ValueError, ET.ParseError, DefusedXmlException) as exc:
                    erros.append(f"Falha ao ler {caminho}: {exc}")

    varrer(os.path.join(raiz_hub, documento), principais, set(chaves), "Principal")
    grupos = {}
    for chave in sorted(set(chaves) - melhores.keys()):
        grupos.setdefault(chave[6:20], set()).add(chave)
    for emitente, pendentes in grupos.items():
        varrer(os.path.join(raiz_hub, emitente), complementares, pendentes, "Complementar")
    # Uma única varredura global para o conjunto restante, não uma por chave.
    # Mantém os resultados anteriores e compara a chave interna de cada candidato.
    pendentes_globais = set(chaves) - melhores.keys()
    if pendentes_globais:
        varrer(raiz_hub, complementares, pendentes_globais, "Global")
    return melhores, sorted(set(chaves) - melhores.keys()), recusados, erros


def buscar(params):
    return buscar_arquivos(params['documento'], params['tipo'], params['chaves'],
                           params['raiz'], params['ano'])


def nomes_no_zip(chaves):
    """Usa nNF da chave já conferida no XML, sem colidir nomes de notas."""
    chaves = sorted(set(chaves))
    numeros = {chave: str(int(chave[25:34])) for chave in chaves}
    contagem = Counter(numeros.values())
    nomes = {}
    usados = set()
    for chave in chaves:
        numero = numeros[chave]
        base = numero
        if contagem[numero] > 1:
            serie = str(int(chave[22:25]))
            base = f"{numero}_serie_{serie}_emitente_{chave[6:20]}"
        nome = base
        indice = 2
        while nome in usados:
            nome = f"{base}_{indice}"
            indice += 1
        nomes[chave] = nome
        usados.add(nome)
    return nomes


def executar(pasta, params):
    pasta = Path(pasta)
    saida = pasta / 'saida'
    saida.mkdir(parents=True, exist_ok=True)
    encontrados, faltantes, recusados, erros = buscar(params)
    nomes = nomes_no_zip(encontrados)
    empacotados = {}
    total_arquivos = 0
    with zipfile.ZipFile(saida / 'Notas.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for chave, dados in sorted(encontrados.items()):
            try:
                z.write(dados['xml'], nomes[chave] + '.xml')
            except OSError as exc:
                erros.append(f"Falha ao incluir XML {dados['xml']}: {exc}")
                continue
            empacotados[chave] = dados
            total_arquivos += 1
            if dados['pdf']:
                try:
                    z.write(dados['pdf'], nomes[chave] + '.pdf')
                    total_arquivos += 1
                except OSError as exc:
                    erros.append(f"Falha ao incluir PDF {dados['pdf']}: {exc}")
        complemento = sum(d['origem'] == 'Complementar' for d in empacotados.values())
        globais = sum(d['origem'] == 'Global' for d in empacotados.values())
        nao_incluidos = sorted(encontrados.keys() - empacotados.keys())
        resumo = (f"{len(empacotados)} XML(s) incluído(s); {len(faltantes)} chave(s) não localizada(s). "
                  f"Complementar: {complemento}; global: {globais}.")
        if nao_incluidos:
            resumo += f" {len(nao_incluidos)} XML(s) localizado(s), mas não incluído(s)."
        if erros:
            resumo += " Há falhas de acesso/leitura. Consulte Resumo.txt."
        texto = '\n'.join([
            f'Buscar NF-es {VERSAO_APP}', resumo,
            f"Ano: {params['ano']}; movimentação: {params['tipo']}.",
            f'Total de arquivos XML/PDF incluídos: {total_arquivos}.',
            f'Candidatos recusados por chave ausente/diferente: {recusados}.',
            '', 'Chaves não localizadas:', *faltantes,
            '', 'XMLs localizados, mas não incluídos no ZIP:', *nao_incluidos,
            '', 'Erros e pastas ausentes/inacessíveis:', *erros,
            '', 'Origem dos XMLs incluídos:',
            *[f"{nomes[chave]}.xml; {chave}; {d['origem']}; {d['xml']}" for chave, d in empacotados.items()],
        ])
        z.writestr('Resumo.txt', texto)
    (saida / 'Resumo.txt').write_text(texto, encoding='utf-8')
    return resumo


if __name__=='__main__':
    pasta=Path(sys.argv[1])
    params=json.loads((pasta/'parametros.json').read_text(encoding='utf-8'))
    mensagem=executar(pasta,params)
    (pasta/'resultado.json').write_text(json.dumps({'mensagem':mensagem},ensure_ascii=False),encoding='utf-8')
