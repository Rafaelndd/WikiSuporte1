"""
Serviço de segurança/restrição de acesso às páginas Streamlit.

Objetivos:
- Centralizar a validação de login.
- Normalizar perfis para a convenção atual: dev, coordenador, analista.
- Facilitar o bloqueio de acesso por perfil em cada página.
"""

from __future__ import annotations

from typing import Iterable, List

import streamlit as st


def normalize_perfil(raw_perfil: str | None) -> str:
    """
    Normaliza o valor de perfil vindo da sessão/banco para:
    - 'dev'
    - 'coordenador'
    - 'analista' (ou outro valor original, se diferente)
    """
    if not raw_perfil:
        return "analista"

    r = str(raw_perfil).strip().lower()

    if r in ("desenvolvedor", "dev"):
        return "dev"
    if r in ("coordenação", "coordenador"):
        return "coordenador"

    return r


def require_login() -> str:
    """
    Garante que o usuário esteja autenticado.
    - Se não estiver, redireciona para 'app.py'.
    - Retorna o perfil normalizado (dev / coordenador / analista / outro).
    """
    if not st.session_state.get("autenticado", False):
        st.switch_page("app.py")

    perfil_raw = st.session_state.get("perfil", "analista")
    perfil_norm = normalize_perfil(perfil_raw)
    # Deixa o perfil normalizado disponível para outras partes da app
    st.session_state["perfil_normalizado"] = perfil_norm
    try:
        from services.ui_realtime import render_global_notifications_listener
        render_global_notifications_listener()
    except Exception:
        pass
    return perfil_norm


def require_profile(allowed: Iterable[str], titulo_bloqueio: str | None = None, detalhes: str | None = None) -> str:
    """
    Exige login e que o perfil do usuário esteja na lista 'allowed'.
    - allowed: iterável de perfis normalizados esperados (ex.: ['dev', 'coordenador']).
    - titulo_bloqueio: mensagem principal opcional para exibir em caso de acesso negado.
    - detalhes: mensagem complementar opcional.

    Em caso de acesso negado:
      - Exibe mensagens no Streamlit.
      - Executa st.stop().

    Retorna o perfil normalizado em caso de acesso permitido.
    """
    perfil = require_login()
    allowed_norm: List[str] = [normalize_perfil(p) for p in allowed]

    if perfil not in allowed_norm:
        if titulo_bloqueio:
            st.error(titulo_bloqueio)
        else:
            st.error("⛔ Acesso Negado.")

        if detalhes:
            st.warning(detalhes)

        st.stop()

    return perfil

