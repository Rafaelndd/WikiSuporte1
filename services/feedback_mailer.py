"""
Envio de e-mails de feedback (SMTP).

Configuração (combinável):
  - Bloco [email] no Streamlit secrets (smtp_server, smtp_user, smtp_password, …), ou
  - Variáveis EMAIL_SUPORTE_* no .env na raiz, com EMAIL_SUPORTE_PASS opcional se a senha
    estiver só em secrets.toml (chave plana EMAIL_SUPORTE_PASS).

Gmail: senha de app (2FA); host comum smtp.gmail.com na porta 465 (SSL) ou 587 (STARTTLS).

SSL no Windows / OpenSSL 3+: o contexto usa o bundle do pacote `certifi`. Se ainda falhar
(antivírus, proxy corporativo), defina EMAIL_SMTP_SSL_INSECURE=1 no .env (último recurso).
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _build_smtp_ssl_context() -> ssl.SSLContext:
    """
    Evita falhas como CERTIFICATE_VERIFY_FAILED / Basic Constraints com o store do SO,
    usando CA bundle do certifi. Opcional: EMAIL_SMTP_SSL_INSECURE=1 desliga verificação
    apenas em ambiente de desenvolvimento/teste.
    """
    ambiente = os.getenv("APP_ENV", "").strip().lower() or os.getenv("ENVIRONMENT", "").strip().lower()
    insecure = (
        os.getenv("EMAIL_SMTP_SSL_INSECURE", "").strip().lower() in ("1", "true", "yes")
        and ambiente in {"dev", "development", "localhost", "local", "test"}
    )
    if insecure:
        logging.warning(
            "EMAIL_SMTP_SSL_INSECURE=1 ativo: validação TLS desligada. Use apenas em ambiente local."
        )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_dotenv_root() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_project_root() / ".env")
    except Exception:
        pass


def _secrets_email_table() -> Optional[Dict[str, Any]]:
    try:
        import streamlit as st

        if not hasattr(st, "secrets") or "email" not in st.secrets:
            return None
        e = st.secrets["email"]
        host = str(e.get("smtp_server") or "").strip()
        if not host:
            return None
        port = int(e.get("smtp_port", 587))
        user = str(e.get("smtp_user") or "").strip()
        password = str(e.get("smtp_password") or "").strip()
        if not user or not password:
            return None
        raw_name = str(e.get("from_name") or e.get("from_addr") or "WikiSuporte")
        from_name = raw_name.strip().strip('"').strip("'")
        to_addr = str(e.get("feedback_to") or user).strip() or user
        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "from_name": from_name,
            "to_address": to_addr,
        }
    except Exception:
        return None


def _secrets_flat_get(key: str, default: str = "") -> str:
    try:
        import streamlit as st

        if not hasattr(st, "secrets") or key not in st.secrets:
            return default
        v = st.secrets[key]
        if v is None:
            return default
        return str(v).strip()
    except Exception:
        return default


def _merge_smtp_from_flat_secrets(
    host: str,
    port: int,
    user: str,
    password: str,
    from_name: str,
    to_addr: str,
) -> tuple[str, int, str, str, str, str]:
    """Preenche campos vazios a partir de chaves planas no secrets.toml (EMAIL_SUPORTE_*)."""
    h = host or _secrets_flat_get("EMAIL_SUPORTE_HOST")
    u = user or _secrets_flat_get("EMAIL_SUPORTE_USER")
    p = password or _secrets_flat_get("EMAIL_SUPORTE_PASS")
    fn = from_name
    raw_fn = _secrets_flat_get("EMAIL_SUPORTE_NAME")
    if raw_fn:
        fn = raw_fn.strip('"').strip("'")
    t = to_addr or u
    ft = _secrets_flat_get("FEEDBACK_TO_EMAIL")
    if ft:
        t = ft
    p_raw = _secrets_flat_get("EMAIL_SUPORTE_PORT")
    try:
        prt = int(p_raw) if p_raw else port
    except ValueError:
        prt = port
    return h, prt, u, p, fn, t or u


def resolve_smtp_config() -> Optional[Dict[str, Any]]:
    """
    Ordem:
      1) Tabela Streamlit secrets [email] (formato contribuições).
      2) .env na raiz + complemento de secrets.toml (ex.: senha só em EMAIL_SUPORTE_PASS).
    """
    cfg = _secrets_email_table()
    if cfg:
        return cfg

    _load_dotenv_root()
    host = os.getenv("EMAIL_SUPORTE_HOST", "").strip()
    try:
        port = int(os.getenv("EMAIL_SUPORTE_PORT", "465"))
    except ValueError:
        port = 465
    user = os.getenv("EMAIL_SUPORTE_USER", "").strip()
    password = os.getenv("EMAIL_SUPORTE_PASS", "").strip()
    raw_name = os.getenv("EMAIL_SUPORTE_NAME", "WikiSuporte")
    from_name = str(raw_name).strip().strip('"').strip("'")
    to_addr = os.getenv("FEEDBACK_TO_EMAIL", "").strip() or user

    host, port, user, password, from_name, to_addr = _merge_smtp_from_flat_secrets(
        host, port, user, password, from_name, to_addr
    )

    if not host or not user or not password:
        return None
    if not to_addr:
        to_addr = user
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_name": from_name,
        "to_address": to_addr,
    }


def _valid_email(addr: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr.strip()))


def send_feedback_email(
    cfg: Dict[str, Any],
    *,
    tipo_feedback: str,
    assunto: str,
    mensagem: str,
    reply_to: Optional[str],
    usuario_nome: Optional[str] = None,
    usuario_id: Optional[int] = None,
) -> Tuple[bool, str]:
    reply = (reply_to or "").strip()
    if reply and not _valid_email(reply):
        return False, "O e-mail para retorno não parece válido. Corrija o campo ou deixe em branco."

    host = str(cfg["host"])
    port = int(cfg["port"])
    user = str(cfg["user"])
    password = str(cfg["password"])
    from_name = str(cfg.get("from_name") or "WikiSuporte")
    to_address = str(cfg.get("to_address") or user)

    msg = EmailMessage()
    subj = f"WikiSuporte — Feedback ({tipo_feedback}): {assunto}"
    if len(subj) > 250:
        subj = subj[:247] + "..."
    msg["Subject"] = subj
    msg["From"] = f"{from_name} <{user}>"
    msg["To"] = to_address
    msg["Reply-To"] = reply if reply else user

    body_lines = [
        "Novo feedback registrado no WikiSuporte.",
        "",
        f"Tipo: {tipo_feedback}",
        f"Assunto: {assunto}",
        "",
        "--- Descrição ---",
        mensagem.strip(),
        "",
        f"E-mail para retorno: {reply if reply else '(não informado)'}",
    ]
    if usuario_nome or usuario_id is not None:
        body_lines.extend(
            [
                "",
                "--- Sessão ---",
                f"Usuário: {usuario_nome or '-'}",
                f"ID: {usuario_id if usuario_id is not None else '-'}",
            ]
        )
    msg.set_content("\n".join(body_lines), charset="utf-8")

    ctx = _build_smtp_ssl_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as server:
                server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(user, password)
                server.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        return (
            False,
            "O servidor recusou usuário ou senha. Para Gmail, use uma senha de app (conta com 2FA), "
            f"não a senha normal da conta. Detalhe: {e}",
        )
    except TimeoutError:
        return (
            False,
            "Tempo esgotado ao conectar ao SMTP. Verifique host, porta, firewall ou VPN.",
        )
    except OSError as e:
        err_txt = str(e)
        hint = ""
        if "CERTIFICATE_VERIFY_FAILED" in err_txt or "SSL" in err_txt:
            hint = (
                " Verifique rede/proxy e reinstale o pacote `certifi`. "
                "Para ambientes de desenvolvimento, apenas então, ative `EMAIL_SMTP_SSL_INSECURE=1`."
            )
        return False, f"Erro de rede ou SSL ao contatar o servidor de e-mail: {e}.{hint}"
    except smtplib.SMTPException as e:
        return False, f"Erro SMTP: {e}"
    except Exception as e:
        return False, f"Falha ao enviar ({type(e).__name__}): {e}"

    return True, "Mensagem enviada com sucesso."
