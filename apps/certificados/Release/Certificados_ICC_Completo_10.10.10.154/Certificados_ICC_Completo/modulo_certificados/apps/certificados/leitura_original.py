"""Funções preservadas do monitora.py enviado por Juan."""
import re
from cryptography import x509
from cryptography.x509.oid import NameOID, ObjectIdentifier

def extrair_cliente_e_senha(nome_arquivo):
    nome = re.sub(r'(?i)(\.pfx|\.p12)+$', '', nome_arquivo)
    nome = nome.strip()
    
    nome = re.sub(r'\s*\(\d+\)$', '', nome)
    nome = re.sub(r'\(ARROBA\)$', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'[\s\-]*CPF(?:\s+novo)?$', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'_VENC\..*$', '', nome, flags=re.IGNORECASE)
    nome = re.sub(r'\s+-$', '', nome)
    
    senha = ""
    cliente = ""
    
    m = re.search(r"^(.*?)\s+\d{11,14}\s+\d{2}-\d{2}-\d{4}\s+(.*)$", nome)
    if m: 
        cliente, senha = m.group(1), m.group(2)
    else:
        m = re.search(r"^(.*?)(?:[_\s-]*senha[_\s-]+)(.*)$", nome, re.IGNORECASE)
        if m: 
            cliente, senha = m.group(1), m.group(2)
        else:
            m = re.search(r"^(.*?)[_\s-]+(\d{3,})$", nome)
            if m:
                cliente, senha = m.group(1), m.group(2)
            else:
                m = re.search(r"^(.*?)\s*-\s*(.*)$", nome)
                if m: 
                    cliente, senha = m.group(1), m.group(2)
                else:
                    m = re.search(r"^(.*?)_([^_]+)$", nome)
                    if m and (re.search(r"\d", m.group(2))):
                        cliente, senha = m.group(1), m.group(2)
                    else:
                        m = re.search(r"^(.*?)\s+([^_\s]+)$", nome)
                        if m and (re.search(r"\d", m.group(2))):
                            cliente, senha = m.group(1), m.group(2)
                        else:
                            cliente, senha = nome, "NÃO IDENTIFICADA"
                            
    if senha != "NÃO IDENTIFICADA":
        cliente = cliente.strip(' _-')
        senha_limpa = senha.lstrip('_- ')
        
        if re.match(r'^\d+$', senha_limpa):
            senha = senha_limpa
        else:
            senha = senha.lstrip('_')
            
    return cliente, senha

def decodificar_texto_der(valor):
    """Lê o texto ASN.1 dos campos OtherName sem incluir tag/comprimento."""
    if len(valor) < 2:
        return ""
    tag = valor[0]
    tamanho = valor[1]
    inicio = 2
    if tamanho & 0x80:
        quantidade = tamanho & 0x7f
        if not quantidade or len(valor) < inicio + quantidade:
            return ""
        tamanho = int.from_bytes(valor[inicio:inicio + quantidade], "big")
        inicio += quantidade
    if inicio + tamanho != len(valor):
        return ""
    conteudo = valor[inicio:inicio + tamanho]
    if tag == 0xA0:
        return decodificar_texto_der(conteudo)
    codificacoes = {
        0x0C: "utf-8", 0x13: "ascii", 0x16: "ascii",
        0x04: "utf-8", 0x14: "latin-1", 0x1E: "utf-16-be",
    }
    if tag not in codificacoes:
        return ""
    try:
        return conteudo.decode(codificacoes[tag])
    except UnicodeDecodeError:
        return ""

def formatar_documento(documento, tipo):
    documento = re.sub(r"[.\-/\s]", "", documento)
    if tipo == "CPF" and re.fullmatch(r"[0-9]{11}", documento):
        return f"{documento[:3]}.{documento[3:6]}.{documento[6:9]}-{documento[9:]}"
    if tipo == "CNPJ" and re.fullmatch(r"[0-9A-Z]{12}[0-9]{2}", documento):
        return f"{documento[:2]}.{documento[2:5]}.{documento[5:8]}/{documento[8:12]}-{documento[12:]}"
    return ""

def extrair_documento_certificado(certificado, tipo):
    # Em e-CNPJ, usa o CNPJ da empresa, nunca o CPF do responsável.
    oid = ObjectIdentifier("2.16.76.1.3.3" if tipo == "CNPJ" else "2.16.76.1.3.1")
    try:
        extensao = certificado.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        for campo in extensao.get_values_for_type(x509.OtherName):
            if campo.type_id != oid:
                continue
            texto = decodificar_texto_der(campo.value).strip()
            # Dados de pessoa física: nascimento (8 caracteres), seguido do CPF (11).
            documento = texto[8:19] if tipo == "CPF" else texto
            documento = formatar_documento(documento, tipo)
            if documento:
                return documento
    except (x509.ExtensionNotFound, ValueError):
        pass

    # Alternativa para certificados com documento no final do Common Name.
    # Não busca números no nome do arquivo, onde podem representar a senha.
    for atributo in certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME):
        _, separador, documento = atributo.value.rpartition(":")
        if separador:
            documento = formatar_documento(documento.strip(), tipo)
            if documento:
                return documento
    return ""
