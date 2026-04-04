"""
Aviso de nova versão na Home e metadados para a página de release da versão.

A fonte de verdade passou a ser ``releases/releases_catalog.json``, gerido por
``utils/release_manager.py``. As constantes abaixo mantêm compatibilidade com
código legado quando o catálogo está vazio.
"""

from __future__ import annotations

import streamlit as st

from utils.release_manager import (
    get_latest_release,
    load_catalog,
    release_for_home_banner,
)

# --- Compat legado (fallback se não houver catálogo) ---
RELEASE_NOTES_VERSION = "1.0.1"
RELEASE_NOTES_DATE = "2026-04-04"
RELEASE_NOTES_SUMMARY = (
    "Login mais estável no navegador, página Release da versão e reforço de segurança nos bastidores."
)

_NOTAS_PAGE = "pages/10_📋_Notas_de_versao.py"


def _sync_legacy_constants_from_catalog() -> None:
    """Atualiza constantes de módulo a partir do catálogo (para imports antigos)."""
    global RELEASE_NOTES_VERSION, RELEASE_NOTES_DATE, RELEASE_NOTES_SUMMARY
    latest = get_latest_release(load_catalog(create_if_missing=False))
    if latest is None:
        return
    RELEASE_NOTES_VERSION = latest.versao.lstrip("vV") or latest.versao
    RELEASE_NOTES_DATE = latest.data_lancamento
    RELEASE_NOTES_SUMMARY = (latest.como_ficou or "")[:500]


def render_release_notes_banner() -> None:
    """
    Legado: antes mostrava banner em todas as páginas. Mantido vazio para não
    duplicar o aviso — use ``render_home_release_nudge`` só na Home.
    """
    return


def render_home_release_nudge() -> None:
    """
    Faixa na parte superior da Home: só aparece enquanto ``hoje <= notificacao_ate``
    da última release. Link nativo para a página de release da versão via ``st.page_link``.
    """
    if not st.session_state.get("autenticado"):
        return

    rec = release_for_home_banner()
    if rec is None:
        return

    st.markdown(
        """
        <style>
        .ws-home-release-nudge {
            border-radius: 12px;
            border: 1px solid rgba(22, 163, 74, 0.45);
            background: linear-gradient(135deg, rgba(22, 163, 74, 0.12), rgba(13, 148, 136, 0.08));
            padding: 0.85rem 1rem;
            margin: 0 0 0.75rem 0;
        }
        html[data-theme="dark"] .ws-home-release-nudge {
            border-color: rgba(52, 211, 153, 0.4);
            background: linear-gradient(135deg, rgba(22, 101, 52, 0.35), rgba(15, 118, 110, 0.2));
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    dl_fmt = rec.data_lancamento
    try:
        from datetime import date as _date

        dl_fmt = _date.fromisoformat(rec.data_lancamento[:10]).strftime("%d/%m/%Y")
    except ValueError:
        pass

    st.markdown(
        f"""
        <div class="ws-home-release-nudge" role="status">
            <strong>✅ Novo Release do WikiSuporte está disponível!</strong>
            <span style="opacity:0.9"> · Versão <code>{rec.versao}</code> · {dl_fmt}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Para saber mais, use o link abaixo.")
    st.page_link(_NOTAS_PAGE, label="👉 Clique aqui para abrir o Release da versão", icon="📋")


# Ao importar, alinha constantes legadas ao JSON (quando existir)
try:
    _sync_legacy_constants_from_catalog()
except Exception:
    pass
