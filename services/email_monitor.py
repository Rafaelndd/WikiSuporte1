"""
Serviço: Monitor de E-mail do Suporte.
- Filtra a caixa de e-mail do suporte em busca de cobranças enviadas por Rodrigo ou Jairo.
- Extrai o número do chamado do corpo/assunto e vincula em cobrancas_chamados.
Configuração via variáveis de ambiente: EMAIL_SUPORTE_HOST, EMAIL_SUPORTE_USER, EMAIL_SUPORTE_PASS, etc.
Não modifica arquivos originais do projeto.
"""
import os
import re
from datetime import datetime
from typing import List, Optional, Tuple

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

try:
    from modules.database import get_connection
except ImportError:
    get_connection = None

# Remetentes considerados para cobrança (nomes ou e-mails)
REMENTENTES_COBRANCA = ("rodrigo", "jairo")

# Padrões para extrair número de chamado (regex)
PADROES_CHAMADO = [
    r"chamado\s*[#nº]?\s*(\d+)",
    r"#\s*(\d+)",
    r"n[º°]?\s*(\d+)",
    r"nr\.?\s*(\d+)",
    r"numero\s*(\d+)",
    r"(\d{4,})\s*\(chamado\)",
]


def _engine():
    if get_connection is None:
        raise RuntimeError("modules.database.get_connection não disponível.")
    return get_connection()


def _config_email():
    """Lê configuração de e-mail do ambiente (.env)."""
    from dotenv import load_dotenv
    load_dotenv()
    return {
        "host": os.getenv("EMAIL_SUPORTE_HOST", ""),
        "user": os.getenv("EMAIL_SUPORTE_USER", ""),
        "password": os.getenv("EMAIL_SUPORTE_PASS", ""),
        "folder": os.getenv("EMAIL_SUPORTE_FOLDER", "INBOX"),
    }


def extrair_numero_chamado(texto: str) -> Optional[int]:
    """
    Extrai o primeiro número de chamado encontrado no texto (assunto + corpo).
    Retorna int ou None.
    """
    if not texto:
        return None
    texto = (texto or "").replace("\r\n", " ").replace("\n", " ")
    for pattern in PADROES_CHAMADO:
        m = re.search(pattern, texto, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def remetente_e_cobranca(de: Optional[str], assunto: Optional[str], corpo: Optional[str]) -> bool:
    """
    Verifica se o e-mail é de Rodrigo ou Jairo e parece ser cobrança
    (assunto ou corpo contém palavras como cobrança, cobrar, follow-up, acompanhamento).
    """
    if not de:
        return False
    de_lower = de.lower()
    if not any(nome in de_lower for nome in REMENTENTES_COBRANCA):
        return False
    texto = f"{assunto or ''} {corpo or ''}".lower()
    termos = ("cobrança", "cobranca", "cobrar", "cobramos", "follow-up", "followup", "acompanhamento", "retorno")
    return any(t in texto for t in termos)


def vincular_cobranca_ao_chamado(
    nr_chamado: int,
    texto_bruto: str,
    remetente_nome: Optional[str] = None,
) -> bool:
    """
    Insere registro em cobrancas_chamados para o chamado informado.
    Retorna True se inseriu com sucesso.
    """
    engine = _engine()
    with engine.begin() as conn:
        # Verifica se o chamado existe
        r = conn.execute(
            text("SELECT 1 FROM chamados_tecnuv WHERE nr_chamado = :nr"),
            {"nr": nr_chamado}
        ).fetchone()
        if not r:
            return False
        conn.execute(
            text("""
                INSERT INTO cobrancas_chamados (nr_chamado, data_cobranca, analista_epsy, texto_bruto_cobranca)
                VALUES (:nr, :data, :analista, :texto)
            """),
            {
                "nr": nr_chamado,
                "data": datetime.now(),
                "analista": remetente_nome or "E-mail (Rodrigo/Jairo)",
                "texto": texto_bruto[:5000] if texto_bruto else None,
            }
        )
    return True


def processar_email_cobranca(de: str, assunto: str, corpo: str) -> Optional[Tuple[int, bool]]:
    """
    Se o e-mail for de Rodrigo/Jairo e tratar de cobrança, extrai nr_chamado e vincula.
    Retorna (nr_chamado, True) se vinculou, (nr_chamado, False) se achou número mas não vinculou, None se não for cobrança.
    """
    if not remetente_e_cobranca(de, assunto, corpo):
        return None
    nr = extrair_numero_chamado(f"{assunto} {corpo}")
    if nr is None:
        return None
    ok = vincular_cobranca_ao_chamado(nr, f"Assunto: {assunto}\n\n{corpo or ''}", remetente_nome=de[:100])
    return (nr, ok)


def buscar_e_processar_emails_imap(limite: int = 50) -> List[Tuple[int, bool]]:
    """
    Conecta ao servidor IMAP (configuração via .env), busca e-mails recentes,
    filtra por Rodrigo/Jairo e cobrança, extrai chamado e vincula.
    Retorna lista de (nr_chamado, vinculado) para cada e-mail processado.
    """
    try:
        import imaplib
        import email
    except ImportError:
        return []

    cfg = _config_email()
    if not cfg.get("host") or not cfg.get("user"):
        return []

    resultados = []
    try:
        mail = imaplib.IMAP4_SSL(cfg["host"])
        mail.login(cfg["user"], cfg["password"] or "")
        mail.select(cfg["folder"], readonly=False)
        _, data = mail.search(None, "ALL")
        ids = data[0].split()
        if not ids:
            mail.logout()
            return []
        # Últimos N
        ids = ids[-limite:] if len(ids) > limite else ids
        for eid in reversed(ids):
            try:
                _, msg_data = mail.fetch(eid, "(RFC822)")
                for part in msg_data:
                    if isinstance(part, tuple):
                        msg = email.message_from_bytes(part[1])
                        de = msg.get("From", "")
                        assunto = msg.get("Subject", "")
                        corpo = ""
                        if msg.is_multipart():
                            for p in msg.walk():
                                if p.get_content_type() == "text/plain":
                                    corpo += (p.get_payload(decode=True) or b"").decode("utf-8", errors="ignore")
                                    break
                        else:
                            corpo = (msg.get_payload(decode=True) or b"").decode("utf-8", errors="ignore")
                        res = processar_email_cobranca(de, assunto, corpo)
                        if res:
                            resultados.append(res)
            except Exception:
                continue
        mail.logout()
    except Exception:
        pass
    return resultados


def executar_monitor_cobrancas(limite_emails: int = 50) -> dict:
    """
    Executa uma varredura da caixa e retorna resumo: { processados, vinculados, erros }.
    """
    resultados = buscar_e_processar_emails_imap(limite=limite_emails)
    vinculados = sum(1 for _, ok in resultados if ok)
    return {"processados": len(resultados), "vinculados": vinculados}
