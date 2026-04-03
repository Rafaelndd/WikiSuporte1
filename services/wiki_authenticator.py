"""
Integração streamlit-authenticator com credenciais carregadas do PostgreSQL.

Os hashes em `usuarios.password_hash` devem ser compatíveis com bcrypt (ex.: gerados
via PostgreSQL `crypt(senha, gen_salt('bf'))`). O streamlit-authenticator valida com
`bcrypt.checkpw`, equivalente ao `crypt()` do Postgres para esse formato.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from streamlit_authenticator import Authenticate

from modules.database import get_connection
from services.perfil_usuario import normalizar_perfil_para_sessao

WIKI_COOKIE_NAME = "wikisuporte_auth"
CREDENTIALS_CACHE_TTL_SEC = 120

# Inclui NULL e valores "ativos" sem misturar boolean com integer (PG falha em `ativo = 1` se `ativo` for boolean).
_USUARIO_CONSIDERADO_ATIVO = """(
    ativo IS NULL
    OR LOWER(TRIM(CAST(ativo AS TEXT))) IN ('true', 't', '1', 'sim', 'yes')
)"""


def login_aliases_and_display(nome: Any, username: Any) -> Tuple[List[str], str]:
    """
    Chaves aceitas no login (minúsculas), na ordem: username depois nome.

    Se ambos existem e diferem (ex.: e-mail em username, \"Dev\" em nome), qualquer um
    autentica — alinhado ao fetch em `fetch_user_row_by_login_key`.
    """
    u = (str(username).strip() if username is not None else "") or ""
    n = (str(nome).strip() if nome is not None else "") or ""
    keys: List[str] = []
    for candidate in (u, n):
        if candidate:
            k = candidate.lower()
            if k not in keys:
                keys.append(k)
    if not keys:
        return [], ""
    display = n if n else u
    return keys, display


def credential_login_key(nome: Any, username: Any) -> Tuple[str, str]:
    """Primeira chave de login + nome exibido (compatível com testes)."""
    keys, display = login_aliases_and_display(nome, username)
    if not keys:
        return "", ""
    return keys[0], display


def _cookie_signing_key() -> str:
    key = (os.getenv("WS_SESSION_SECRET") or os.getenv("LGPD_SECRET_KEY") or "").strip()
    if not key:
        logging.warning(
            "Defina WS_SESSION_SECRET ou LGPD_SECRET_KEY para assinar o cookie de login "
            "(streamlit-authenticator). Em produção use uma chave longa e aleatória."
        )
        key = "wikisuporte-dev-only-unsafe-set-ws-session-secret"
    return key


@st.cache_data(ttl=CREDENTIALS_CACHE_TTL_SEC, show_spinner=False)
def load_credentials_for_stauth() -> Dict[str, Any]:
    """Monta o dict no formato esperado pelo streamlit-authenticator (usuários ativos)."""
    engine = get_connection()
    out: Dict[str, Any] = {"usernames": {}}
    sql_nome_apenas = text(f"""
        SELECT nome, password_hash
        FROM usuarios
        WHERE {_USUARIO_CONSIDERADO_ATIVO}
          AND password_hash IS NOT NULL
          AND trim(coalesce(nome, '')) <> ''
    """)
    sql_com_username = text(f"""
        SELECT nome, username, password_hash
        FROM usuarios
        WHERE {_USUARIO_CONSIDERADO_ATIVO}
          AND password_hash IS NOT NULL
          AND (
              trim(coalesce(username, '')) <> ''
              OR trim(coalesce(nome, '')) <> ''
          )
    """)
    try:
        with engine.connect() as conn:
            try:
                rows = conn.execute(sql_com_username).fetchall()
                has_username = True
            except ProgrammingError as pe:
                conn.rollback()
                logging.info(
                    "load_credentials_for_stauth: consulta com username indisponível (%s); usando só nome.",
                    pe,
                )
                rows = conn.execute(sql_nome_apenas).fetchall()
                has_username = False
    except Exception as e:
        logging.error("load_credentials_for_stauth: %s", e)
        return out

    for r in rows:
        m = r._mapping
        nome_val = m["nome"]
        user_val = m["username"] if has_username else None
        alias_keys, display_name = login_aliases_and_display(nome_val, user_val)
        raw_hash = m["password_hash"]
        if not alias_keys or raw_hash is None:
            continue
        if isinstance(raw_hash, bytes):
            phs = raw_hash.decode("utf-8", errors="replace")
        else:
            phs = str(raw_hash).strip()
        if not phs:
            continue
        for ukey in alias_keys:
            out["usernames"][ukey] = {
                "name": display_name,
                "password": phs,
            }
    return out


def get_wiki_authenticator() -> Authenticate:
    creds = load_credentials_for_stauth()
    return Authenticate(
        creds,
        WIKI_COOKIE_NAME,
        _cookie_signing_key(),
        30.0,
        auto_hash=False,
        login_sleep_time=0,
    )


def fetch_user_row_by_login_key(username_lower: str) -> Optional[tuple[Any, ...]]:
    """Retorna uma linha (id, nome_exibicao, perfil) para o usuário ativo, ou None."""
    engine = get_connection()
    u = (username_lower or "").strip().lower()
    if not u:
        return None
    sql_nome = text(f"""
        SELECT id, trim(nome) AS nome_exibicao, perfil
        FROM usuarios
        WHERE lower(trim(nome)) = :u
          AND {_USUARIO_CONSIDERADO_ATIVO}
    """)
    # Aceita o mesmo conjunto de aliases que load_credentials (nome OU username).
    sql_nome_ou_username = text(f"""
        SELECT id,
               coalesce(nullif(trim(nome), ''), nullif(trim(username), '')) AS nome_exibicao,
               perfil
        FROM usuarios
        WHERE {_USUARIO_CONSIDERADO_ATIVO}
          AND (
              lower(trim(nome)) = :u
              OR lower(trim(username)) = :u
          )
    """)
    try:
        with engine.connect() as conn:
            try:
                row = conn.execute(sql_nome_ou_username, {"u": u}).fetchone()
            except ProgrammingError:
                conn.rollback()
                row = conn.execute(sql_nome, {"u": u}).fetchone()
    except Exception as e:
        logging.error("fetch_user_row_by_login_key: %s", e)
        return None
    return row


def sync_wiki_session_from_stauth() -> None:
    """Espelha o estado do streamlit-authenticator para as chaves usadas pelo WikiSuporte."""
    if not st.session_state.get("authentication_status"):
        st.session_state["autenticado"] = False
        return
    uname = st.session_state.get("username")
    if not uname:
        st.session_state["autenticado"] = False
        return
    row = fetch_user_row_by_login_key(str(uname))
    if not row:
        logging.warning(
            "sync_wiki_session_from_stauth: utilizador '%s' autenticou no stauth mas não há "
            "linha ativa em `usuarios` (nome/username/ativo). Verifique coluna `ativo` e o login.",
            uname,
        )
        wiki_force_logout()
        return
    st.session_state["autenticado"] = True
    st.session_state["usuario_id"] = int(row[0])
    st.session_state["usuario_nome"] = str(row[1] or "")
    st.session_state["perfil"] = normalizar_perfil_para_sessao(str(row[2] or "analista"))
    if "notificacoes_lidas" not in st.session_state:
        st.session_state["notificacoes_lidas"] = []


def wiki_force_logout() -> None:
    """Encerra sessão stauth, remove cookie e limpa campos locais."""
    auth: Optional[Authenticate] = st.session_state.get("_wiki_authenticator_ref")
    if auth is None:
        auth = get_wiki_authenticator()
    try:
        if st.session_state.get("authentication_status"):
            auth.authentication_controller.logout()
        auth.cookie_controller.delete_cookie()
    except Exception as e:
        logging.warning("wiki_force_logout: %s", e)
    st.session_state["autenticado"] = False
    for k in ("usuario_id", "usuario_nome", "perfil", "ultimo_acesso"):
        st.session_state.pop(k, None)


def ensure_stauth_cookie_restored() -> None:
    """Processa cookie de re-login sem desenhar o formulário padrão da biblioteca."""
    auth = get_wiki_authenticator()
    st.session_state["_wiki_authenticator_ref"] = auth
    auth.login(location="unrendered", key="ws_stauth_probe")
    sync_wiki_session_from_stauth()
