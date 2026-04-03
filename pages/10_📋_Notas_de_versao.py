"""
Página pública interna: notas de versão do WikiSuporte (linguagem para utilizadores).
Conteúdo: releases/WIKISUPORTE_NOTAS_DE_VERSAO.md
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from services.release_notes_banner import RELEASE_NOTES_DATE, RELEASE_NOTES_VERSION
from services.ui_realtime import render_global_notifications_listener

st.set_page_config(
    page_title="WikiSuporte — Notas de versão",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not st.session_state.get("autenticado", False):
    st.info("Redirecionando para a página de login…")
    st.switch_page("app.py")

render_global_notifications_listener(show_release_banner=False)

_BASE = Path(__file__).resolve().parent.parent
_MD_PATH = _BASE / "releases" / "WIKISUPORTE_NOTAS_DE_VERSAO.md"

st.markdown(
    """
    <style>
    .ws-notes-hero {
        text-align: center;
        margin: 0 auto 1rem auto;
        max-width: 48rem;
    }
    .ws-notes-hero h1 {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        font-weight: 800;
        font-size: clamp(1.75rem, 4vw, 2.25rem);
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.03em;
    }
    .ws-notes-hero .wiki { color: #1e5fbf; }
    .ws-notes-hero .suporte { color: #0d9488; }
    html[data-theme="dark"] .ws-notes-hero .wiki { color: #93c5fd; }
    html[data-theme="dark"] .ws-notes-hero .suporte { color: #5eead4; }
    .ws-notes-hero .meta {
        color: #6b7280;
        font-size: 0.95rem;
        margin: 0;
    }
    html[data-theme="dark"] .ws-notes-hero .meta { color: #9ca3af; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="ws-notes-hero">
        <h1 aria-label="WikiSuporte Notas de versão">
            <span class="wiki">Wiki</span><span class="suporte">Suporte</span>
        </h1>
        <p class="meta"><strong>Notas de versão</strong> · Release {RELEASE_NOTES_VERSION} · {RELEASE_NOTES_DATE}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

if not _MD_PATH.is_file():
    st.error("Ficheiro de notas não encontrado. Contacte a equipa técnica.")
    st.stop()

raw = _MD_PATH.read_text(encoding="utf-8")
# Remove o primeiro H1 duplicado se existir (o título já está no hero)
raw = re.sub(r"^#\s+Notas de versão[^\n]*\n+", "", raw.strip(), count=1)
# Oculta bloco "Para a equipa técnica" na UI (mantém no repo para devs)
raw = re.split(r"\n---\n## Para a equipa técnica", raw, maxsplit=1)[0].strip()

st.markdown(raw)
