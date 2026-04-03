"""
Integração streamlit-authenticator com credenciais carregadas do PostgreSQL.

Os hashes em `usuarios.password_hash` devem ser compatíveis com bcrypt (ex.: gerados
via PostgreSQL `crypt(senha, gen_salt('bf'))`). O streamlit-authenticator valida com
`bcrypt.checkpw`, equivalente ao `crypt()` do Postgres para esse formato.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import streamlit as st
from sqlalchemy import text
from streamlit_authenticator import Authenticate

from modules.database import get_connection

WIKI_COOKIE_NAME = "wikisuporte_auth"
CREDENTIALS_CACHE_TTL_SEC = 120


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
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT lower(trim(nome)) AS ukey, nome, password_hash
                    FROM usuarios
                    WHERE ativo = TRUE
                      AND password_hash IS NOT NULL
                      AND trim(coalesce(nome, '')) <> ''
                """)
            ).fetchall()
    except Exception as e:
        logging.error("load_credentials_for_stauth: %s", e)
        return out

    for r in rows:
        ukey = (r.ukey or "").strip()
        raw_hash = r.password_hash
        if not ukey or raw_hash is None:
            continue
        if isinstance(raw_hash, bytes):
            phs = raw_hash.decode("utf-8", errors="replace")
        else:
            phs = str(raw_hash).strip()
        if not phs:
            continue
        out["usernames"][ukey] = {
            "name": str(r.nome or ukey),
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
    """Retorna uma linha (id, nome, perfil) para o usuário ativo, ou None."""
    engine = get_connection()
    u = (username_lower or "").strip().lower()
    if not u:
        return None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, nome, perfil
                    FROM usuarios
                    WHERE lower(trim(nome)) = :u AND ativo = TRUE
                """),
                {"u": u},
            ).fetchone()
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
        wiki_force_logout()
        return
    st.session_state["autenticado"] = True
    st.session_state["usuario_id"] = int(row[0])
    st.session_state["usuario_nome"] = str(row[1] or "")
    st.session_state["perfil"] = str(row[2] or "analista")
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
