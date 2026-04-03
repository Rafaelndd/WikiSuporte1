"""
Banner de novidades da versão + link para a página de notas (releases).

Ao publicar uma nova versão, atualize as constantes abaixo e acrescente
entradas em releases/WIKISUPORTE_NOTAS_DE_VERSAO.md.
"""

from __future__ import annotations

import streamlit as st

# --- Atualizar a cada release ---
RELEASE_NOTES_VERSION = "2.1.0"
RELEASE_NOTES_DATE = "2026-04-02"
RELEASE_NOTES_SUMMARY = (
    "Sessão de login mais estável no navegador, nova página de notas de versão e reforço de segurança nos bastidores."
)

_SESSION_ACK = f"ws_release_notes_ack_{RELEASE_NOTES_VERSION.replace('.', '_')}"


def render_release_notes_banner() -> None:
    """
    Exibe um aviso discreto com link para Notas de versão (uma vez por sessão até o utilizador dispensar).
    Só faz sentido com utilizador autenticado; chamado a partir de ui_realtime.
    """
    if not st.session_state.get("autenticado"):
        return
    if st.session_state.get(_SESSION_ACK):
        return

    st.markdown(
        """
        <style>
        .ws-release-banner {
            border-radius: 12px;
            border: 1px solid rgba(30, 95, 191, 0.35);
            background: linear-gradient(135deg, rgba(30, 95, 191, 0.08), rgba(13, 148, 136, 0.06));
            padding: 0.85rem 1rem;
            margin: 0.25rem 0 0.75rem 0;
        }
        .ws-release-banner .ws-brand-wiki { color: #1e5fbf; font-weight: 800; }
        .ws-release-banner .ws-brand-sup { color: #0d9488; font-weight: 800; }
        html[data-theme="dark"] .ws-release-banner .ws-brand-wiki { color: #93c5fd; }
        html[data-theme="dark"] .ws-release-banner .ws-brand-sup { color: #5eead4; }
        .ws-release-meta { font-size: 0.9rem; color: #6b7280; margin-top: 0.25rem; }
        html[data-theme="dark"] .ws-release-meta { color: #9ca3af; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="ws-release-banner" role="region" aria-label="Novidades da versão">
            <div>
                <span class="ws-brand-wiki">Wiki</span><span class="ws-brand-sup">Suporte</span>
                · <strong>Novidades da versão {RELEASE_NOTES_VERSION}</strong>
            </div>
            <div class="ws-release-meta">Publicado em {RELEASE_NOTES_DATE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(RELEASE_NOTES_SUMMARY)

    c1, c2, c3 = st.columns([1.1, 1.1, 2.2])
    with c1:
        try:
            st.page_link(
                "pages/10_📋_Notas_de_versao.py",
                label="Abrir notas de versão",
                icon="📋",
            )
        except Exception:
            st.markdown("*Abra **Notas de versão** no menu lateral.*")
    with c2:
        if st.button("Entendi", key=f"btn_ack_release_{RELEASE_NOTES_VERSION}", type="secondary"):
            st.session_state[_SESSION_ACK] = True
            st.rerun()
    with c3:
        pass
