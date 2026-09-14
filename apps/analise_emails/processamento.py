import glob
import os
import re
import shutil
from datetime import datetime
from collections import Counter

import pandas as pd


# =============================================================================
# CONFIGURAÇÕES (Utilizando caminho UNC para evitar falhas de mapeamento)
# =============================================================================

PASTA_BASE = r"\\SRVPROSOFT\Arquivos_ICC\TI\KingHost\Analise_Log_Recebidos"

PASTA_ENTRADA = PASTA_BASE
PASTA_ANALISADOS = os.path.join(PASTA_BASE, "Analisados")
PASTA_SAIDA = os.path.join(PASTA_BASE, "Bloqueados")
PASTA_HISTORICO = os.path.join(PASTA_SAIDA, "Historico")

MEU_DOMINIO = "icccontabilidade.com.br"

# Arquivo externo contendo e-mails/domínios liberados
ARQUIVO_EMAILS_LIBERADOS = os.path.join(PASTA_BASE, "emails_liberados.csv")

# Pontuações de corte
CORTE_PONTUACAO_SPAM = 25
CORTE_BLOQUEIO_DOMINIO = 50
MIN_OCORRENCIAS_HISTORICO = 2


# =============================================================================
# WHITELIST FIXA
# =============================================================================

WHITELIST_EXATA = {
    "icccontabilidade.com.br",
    "sefaz.mt.gov.br",
    "thomsonreuters.com",
    "cnj.jus.br",
    "acesso.gov.br",
    "sicredi.com.br",
    "rovaris.com.br",
    "jus.br",
    "gov.br",
    "docusign.net",
    "infomach.com.br",
    "sieg.com",
}


# =============================================================================
# PROVEDORES PÚBLICOS
# =============================================================================

PROVEDORES_PUBLICOS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "yahoo.com.br",
    "icloud.com",
    "uol.com.br",
    "terra.com.br",
    "bol.com.br",
}


# =============================================================================
# PADRÕES DE SPAM E PLATAFORMAS DE DISPARO
# =============================================================================

PADROES_SPAM = [
    r"\bmkt\b",
    r"marketing",
    r"emailmkt",
    r"mailmkt",
    r"newsletter",
    r"promo",
    r"oferta",
    r"sendgrid",
    r"mailgrid",
    r"servidor[a-z0-9]{4,}",
    r"info\d+@",
    r"suporte\d*@",
    r"envio\d*@",
    r"bounce",
    r"mmkt",
]

PLATAFORMAS_DISPARO = [
    "mktomail.com",
    "mcsv.net",
    "sendgrid.net",
    "mailgun",
    "brasilmei.com.br",
    "onstar.com",
    "duplas.com.br",
    "caixadaalegria.com.br",
    "advanced.cloud",
    "loft.com.br",
    "datagroexperience.com",
    "rci.com",
    "guias.store",
    "roxa.org",
]

TERMOS_PROMOCIONAIS = [
    "off", "desconto", "promoção", "promocao", "boleto de cobrança", "boleto de cobranca",
    "cupom", "grátis", "gratis", "oferta", "últimas horas", "ultimas horas", "aproveite",
    "imperdível", "imperdivel", "ganhe", "clique aqui", "atualização necessária",
    "solicitação de assinatura", "kit de cervejas", "vinhos", "passagens", "alerta de segurança",
    "garanta já", "limpe seu nome", "quitar dívidas", "crédito aprovado", "bruna contabilidade",
    "proposta", "doação", "doacao", "oportunidade de investimento", "últimas unidades",
    "notificación", "prazo vencido", "férias", "ferias", "regularize", "nota fiscal disponível"
]

REMETENTES_GENERICOS = {
    "admin", "administrator", "financeiro", "financeira", "faturamento", "cobranca",
    "cobrança", "suporte", "contato", "atendimento", "website", "info", "noreply",
    "no-reply", "notificacao", "notificação", "setorfinanceiro", "departamento",
    "comercial", "envio", "contabilidade"
}

TLD_RISCO = {
    "xyz", "top", "click", "fun", "online", "site", "space", "ninja", "biz",
    "info", "store", "cloud", "org", "it", "mx"
}


# =============================================================================
# FUNÇÕES DE NORMALIZAÇÃO E SUPORTE
# =============================================================================

def normalizar(valor):
    if pd.isna(valor):
        return ""
    val = str(valor).strip().lower()
    if val.startswith("b'") or val.startswith('b"'):
        val = val[2:-1]
    return val

def normalizar_email(email):
    return normalizar(email).strip(" \t\r\n\"'(),;")

def normalizar_dominio(domain):
    return normalizar(domain).strip(" \t\r\n\"'(),;").lstrip("@")

def extrair_dominio(email):
    email = normalizar_email(email)
    return email.rsplit("@", 1)[1].strip().lower() if "@" in email else ""

def extrair_usuario(email):
    email = normalizar_email(email)
    return email.rsplit("@", 1)[0].strip().lower() if "@" in email else ""

def carregar_emails_liberados():
    emails_liberados, dominios_liberados = set(), set()
    if not os.path.isfile(ARQUIVO_EMAILS_LIBERADOS):
        return emails_liberados, dominios_liberados
    try:
        with open(ARQUIVO_EMAILS_LIBERADOS, "r", encoding="utf-8-sig", errors="ignore") as f:
            for linha in f:
                linha = linha.strip().lower().replace('"', '').replace("'", "")
                if not linha or linha in {"email", "e-mail", "endereco_email", "endereco"}:
                    continue
                for parte in re.split(r"[;,]", linha):
                    item = parte.strip(" \t\r\n\"'(),;")
                    if item.startswith("@"):
                        dom = normalizar_dominio(item)
                        if dom and "." in dom:
                            dominios_liberados.add(dom)
                    elif "@" in item:
                        em = normalizar_email(item)
                        if re.fullmatch(r"[^@\s;,]+@[^@\s;,]+\.[^@\s;,]+", em):
                            emails_liberados.add(em)
    except Exception as e:
        print(f"Erro ao ler liberados: {e}")
    return emails_liberados, dominios_liberados

def dominio_whitelist(domain, dominios_liberados=None):
    domain = normalizar_dominio(domain)
    if not domain:
        return False
    for permitido in WHITELIST_EXATA:
        permitido = normalizar_dominio(permitido)
        if domain == permitido or domain.endswith("." + permitido):
            return True
    return dominios_liberados and domain in dominios_liberados

def subdominio_hex_aleatorio(domain):
    partes = domain.split(".")
    return bool(re.fullmatch(r"[0-9a-f]{6,12}", partes[0])) if len(partes) >= 3 else False

def subdominio_servidor_aleatorio(domain):
    partes = domain.split(".")
    return bool(re.fullmatch(r"(servidor|potomac|em\d+|mail\d+|atl\d+)[a-z0-9]*", partes[0])) if len(partes) >= 3 else False

def carregar_historico_bloqueios():
    emails, dominios = Counter(), Counter()
    arquivos = glob.glob(os.path.join(PASTA_HISTORICO, "Bloqueados_*"))
    for arquivo in arquivos:
        try:
            with open(arquivo, "r", encoding="utf-8", errors="ignore") as f:
                for linha in f:
                    item = normalizar(linha).strip(" \t\r\n\"'(),;").rstrip(",;")
                    if item.startswith("@"):
                        dominios[normalizar_dominio(item)] += 1
                    elif "@" in item:
                        em = normalizar_email(item)
                        emails[em] += 1
                        dom = extrair_dominio(em)
                        if dom: dominios[dom] += 1
        except Exception:
            pass
    return emails, dominios


# =============================================================================
# AVALIAÇÃO DE SPAM
# =============================================================================

def avaliar_email(row, historico_emails, historico_dominios, emails_liberados, dominios_liberados):
    sender = normalizar_email(row.get("Remetente", ""))
    subject = normalizar(row.get("Assunto", ""))

    email = sender
    domain = extrair_dominio(email)
    usuario = extrair_usuario(email)
    dominio_formatado = f"@{domain}" if domain else ""

    if not email:
        return (email, dominio_formatado, 0, "SEM_REMETENTE")
    if email in emails_liberados:
        return (email, dominio_formatado, 0, "EMAIL_LIBERADO")
    if dominio_whitelist(domain, dominios_liberados):
        return (email, dominio_formatado, 0, "DOMINIO_LIBERADO")

    score = 0
    motivos = []

    if email in historico_emails:
        score += 100
        motivos.append(f"EMAIL_HISTORICO_{historico_emails[email]}X")

    ocorrencias_domain = historico_dominios.get(domain, 0)
    if ocorrencias_domain >= MIN_OCORRENCIAS_HISTORICO and domain not in PROVEDORES_PUBLICOS:
        score += 70
        motivos.append(f"DOMINIO_HISTORICO_{ocorrencias_domain}X")

    if usuario.startswith(("bounce", "bounces")):
        score += 25
        motivos.append("PREFIXO_BOUNCE")

    for plat in PLATAFORMAS_DISPARO:
        if plat in domain:
            score += 30
            motivos.append("PLATAFORMA_DISPARO_MKT")
            break

    if subdominio_hex_aleatorio(domain):
        score += 30
        motivos.append("SUBDOMINIO_HEX_ALEATORIO")

    if subdominio_servidor_aleatorio(domain):
        score += 25
        motivos.append("SERVIDOR_MASSI_SERVICO")

    for padrao in PADROES_SPAM:
        if re.search(padrao, email, re.IGNORECASE):
            score += 25
            motivos.append("PADRAO_DISPARO")
            break

    if usuario in REMETENTES_GENERICOS:
        score += 15
        motivos.append("REMETENTE_GENERICO")

    for termo in TERMOS_PROMOCIONAIS:
        if termo in subject:
            score += 25
            motivos.append("ASSUNTO_SUSPEITO")
            break

    if "[remetente não verificado]" in subject or "[remetente nao verificado]" in subject:
        score += 25
        motivos.append("REMETENTE_NAO_VERIFICADO")

    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    if tld in TLD_RISCO:
        score += 15
        motivos.append(f"TLD_RISCO_{tld}")

    if len(motivos) >= 2:
        score += 10
        motivos.append("MULTIPLOS_INDICADORES")

    return (email, dominio_formatado, score, " | ".join(motivos))


# =============================================================================
# LEITURA DE ARQUIVOS
# =============================================================================

def ler_csv_ou_excel(arquivo):
    for enc in ["utf-8", "utf-8-sig", "latin-1"]:
        for sep in [";", ","]:
            try:
                df = pd.read_csv(arquivo, sep=sep, encoding=enc, engine="python")
                # Trata possíveis caracteres ocultos no nome da coluna
                df.columns = [col.strip().replace('\ufeff', '') for col in df.columns]
                if "Remetente" in df.columns:
                    return df
            except Exception:
                continue
    try:
        df = pd.read_excel(arquivo)
        df.columns = [col.strip().replace('\ufeff', '') for col in df.columns]
        return df
    except Exception:
        return None


# =============================================================================
# PROCESSAMENTO PRINCIPAL
# =============================================================================

def processar_logs():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    os.makedirs(PASTA_ANALISADOS, exist_ok=True)

    emails_liberados, dominios_liberados = carregar_emails_liberados()
    historico_emails, historico_dominios = carregar_historico_bloqueios()

    arquivos_csv = [f for f in glob.glob(os.path.join(PASTA_ENTRADA, "*.csv")) if os.path.isfile(f)]
    if not arquivos_csv:
        print("Nenhum arquivo CSV encontrado para processar.")
        return

    dfs = []
    arquivos_processados = []

    for arquivo in arquivos_csv:
        df = ler_csv_ou_excel(arquivo)
        if df is None or "Remetente" not in df.columns:
            continue
        dfs.append(df)
        arquivos_processados.append(arquivo)

    if not dfs:
        print("Nenhum CSV válido com a coluna 'Remetente' foi identificado.")
        return

    df_total = pd.concat(dfs, ignore_index=True)

    df_recebidos = df_total[
        df_total["Status"].astype(str).str.strip().str.lower().isin(["recebido", "recebida"])
    ].copy()

    if df_recebidos.empty:
        print("Nenhum e-mail com status 'Recebido' foi encontrado.")
        return

    resultados = df_recebidos.apply(
        lambda row: avaliar_email(row, historico_emails, historico_dominios, emails_liberados, dominios_liberados),
        axis=1
    )

    df_recebidos["Endereco_Email"] = [r[0] for r in resultados]
    df_recebidos["Dominio"] = [r[1] for r in resultados]
    df_recebidos["Pontuacao_Spam"] = [r[2] for r in resultados]
    df_recebidos["Motivo"] = [r[3] for r in resultados]

    spams = df_recebidos[df_recebidos["Pontuacao_Spam"] >= CORTE_PONTUACAO_SPAM].copy()

    if not spams.empty:
        spams = spams[~spams["Endereco_Email"].map(normalizar_email).isin(emails_liberados)].copy()
        if dominios_liberados:
            spams = spams[~spams["Dominio"].map(normalizar_dominio).isin(dominios_liberados)].copy()

    emails_unicos = sorted(
        {normalizar_email(e) for e in spams["Endereco_Email"].dropna() if normalizar_email(e) and normalizar_email(e) not in emails_liberados}
    )

    dominios_candidatos = []
    for _, row in spams.iterrows():
        domain = normalizar_dominio(row["Dominio"])
        score = row["Pontuacao_Spam"]
        if not domain or domain in PROVEDORES_PUBLICOS or domain in dominios_liberados:
            continue
        if score >= CORTE_BLOQUEIO_DOMINIO or subdominio_hex_aleatorio(domain) or subdominio_servidor_aleatorio(domain) or historico_dominios.get(domain, 0) >= MIN_OCORRENCIAS_HISTORICO:
            dominios_candidatos.append("@" + domain)

    dominios_unicos = sorted(
        {"@" + normalizar_dominio(d) for d in dominios_candidatos if normalizar_dominio(d) and normalizar_dominio(d) not in dominios_liberados}
    )

    lista_final = sorted(set(emails_unicos + dominios_unicos))

    timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M")

    # 1. GERAÇÃO DO ARQUIVO DE BLOQUEADOS (Bloqueados_*.csv)
    nome_arquivo_bloqueados = f"Bloqueados_{timestamp}.csv"
    caminho_csv_bloqueados = os.path.join(PASTA_SAIDA, nome_arquivo_bloqueados)

    with open(caminho_csv_bloqueados, "w", encoding="utf-8") as f_out:
        for item in lista_final:
            f_out.write(f"{item},\n")

    # 2. GERAÇÃO DO RELATÓRIO DE ANÁLISE COMPLETA (Analise_*.csv)
    nome_arquivo_analise = f"Analise_{timestamp}.csv"
    caminho_csv_analise = os.path.join(PASTA_SAIDA, nome_arquivo_analise)

    colunas_relatorio = ["Remetente", "Destinatario", "Assunto", "Dominio", "Pontuacao_Spam", "Motivo"]
    cols_existentes = [c for c in colunas_relatorio if c in spams.columns]

    if not spams.empty:
        spams[cols_existentes].to_csv(caminho_csv_analise, sep=";", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame(columns=cols_existentes).to_csv(caminho_csv_analise, sep=";", index=False, encoding="utf-8-sig")

    print("\n==================================================")
    print(" ANTISPAM - PROCESSAMENTO CONCLUÍDO")
    print("==================================================")
    print(f"Recebidos analisados: {len(df_recebidos)}")
    print(f"Spams detectados: {len(spams)}")
    print(f"Bloqueados gerados: {len(lista_final)} -> {caminho_csv_bloqueados}")
    print(f"Relatório de Análise: {caminho_csv_analise}")
    print("==================================================")

    # MOVER ARQUIVOS PROCESSADOS
    for arquivo in arquivos_processados:
        try:
            shutil.move(arquivo, os.path.join(PASTA_ANALISADOS, os.path.basename(arquivo)))
        except Exception as e:
            print(f"Erro ao mover arquivo {os.path.basename(arquivo)}: {e}")


