"""
Presets visuais opcionais para o WikiSuporte (Streamlit).

Objetivo
--------
Complementar o tema nativo do Streamlit (claro/escuro em ☰ → Configurações)
com paletas de marca **não destrutivas**: apenas CSS extra, sem novas dependências.

Presets
-------
- **padrao**: nenhum CSS adicional (comportamento Streamlit puro).
- **anthropic_light**: papel quente, tipografia neutra — pensado para uso com
  aparência **clara** do Streamlit (`html[data-theme="light"]`).
- **spotify_dark**: base #121212 e cartões elevados — pensado para aparência
  **escura** do Streamlit (`html[data-theme="dark"]`).

Os seletores respeitam `data-theme` para não forçar contraste ilegível quando
o utilizador mistura preset e modo do Streamlit; nesse caso o impacto visual
é reduzido de propósito.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

# Chave única na sessão (evitar colisão com outras flags)
SESSION_PRESET_KEY: Final[str] = "ws_ui_theme_preset"

VALID_PRESETS: Final[tuple[str, ...]] = ("padrao", "anthropic_light", "spotify_dark")

_LABELS: Final[dict[str, str]] = {
    "padrao": "Padrão Streamlit",
    "anthropic_light": "Claro (inspiração Anthropic)",
    "spotify_dark": "Escuro (inspiração Spotify)",
}


def normalize_preset(raw: str | None) -> str:
    """Devolve um preset suportado; valores desconhecidos caem em 'padrao'."""
    if raw in VALID_PRESETS:
        return raw
    return "padrao"


def ensure_theme_session_defaults() -> None:
    """Garante chave inicial na sessão antes de widgets com a mesma key."""
    if SESSION_PRESET_KEY not in st.session_state:
        st.session_state[SESSION_PRESET_KEY] = "padrao"


def build_theme_stylesheet(preset: str) -> str:
    """
    Gera o bloco CSS para o preset (função pura — fácil de testar).

    O CSS é aplicado só quando o modo nativo do Streamlit corresponde ao
    preset escolhido, para manter contraste acessível.
    """
    p = normalize_preset(preset)
    if p == "padrao":
        return ""

    if p == "anthropic_light":
        return """
        <style>
        /* Claro — papel quente, bordas suaves (use tema claro do Streamlit) */
        html[data-theme="light"] .stApp {
            background: linear-gradient(180deg, #faf8f5 0%, #f3f0ea 100%) !important;
        }
        html[data-theme="light"] [data-testid="stHeader"] {
            background: rgba(250, 248, 245, 0.92) !important;
            border-bottom: 1px solid #e8e4dc !important;
            backdrop-filter: blur(8px);
        }
        html[data-theme="light"] [data-testid="stSidebar"] {
            background: #fffcf7 !important;
            border-right: 1px solid #e8e4dc !important;
        }
        html[data-theme="light"] .block-container {
            color: #1f1f1f !important;
        }
        html[data-theme="light"] .stMarkdown, html[data-theme="light"] .stCaption {
            color: #3a3a3a;
        }
        html[data-theme="light"] .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #c47a5a 0%, #b86f52 100%) !important;
            border: none !important;
            color: #fff !important;
        }
        html[data-theme="light"] .stButton > button[kind="primary"]:hover {
            box-shadow: 0 2px 8px rgba(180, 111, 82, 0.35);
        }
        </style>
        """

    # spotify_dark
    return """
    <style>
    /* Escuro — camadas tipo Spotify (use tema escuro do Streamlit) */
    html[data-theme="dark"] .stApp {
        background: #121212 !important;
    }
    html[data-theme="dark"] [data-testid="stHeader"] {
        background: rgba(18, 18, 18, 0.92) !important;
        border-bottom: 1px solid #282828 !important;
        backdrop-filter: blur(8px);
    }
    html[data-theme="dark"] [data-testid="stSidebar"] {
        background: #000000 !important;
        border-right: 1px solid #282828 !important;
    }
    html[data-theme="dark"] [data-testid="stSidebar"] .stMarkdown,
    html[data-theme="dark"] [data-testid="stSidebar"] p,
    html[data-theme="dark"] [data-testid="stSidebar"] span {
        color: #e0e0e0 !important;
    }
    html[data-theme="dark"] .block-container {
        color: #f5f5f5 !important;
    }
    html[data-theme="dark"] [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #333333 !important;
        background: #1e1e1e !important;
    }
    html[data-theme="dark"] .stButton > button[kind="secondary"] {
        background: #282828 !important;
        color: #fff !important;
        border: 1px solid #3e3e3e !important;
    }
    html[data-theme="dark"] a {
        color: #1ed760 !important;
    }
    </style>
    """


def inject_theme_stylesheet(preset: str | None = None) -> None:
    """Injeta CSS global via markdown (idempotente por rerun)."""
    ensure_theme_session_defaults()
    key = preset if preset is not None else str(st.session_state.get(SESSION_PRESET_KEY, "padrao"))
    css = build_theme_stylesheet(key)
    if css.strip():
        st.markdown(css, unsafe_allow_html=True)


def render_theme_sidebar_controls() -> None:
    """Controlo na barra lateral: preset guardado em session_state."""
    ensure_theme_session_defaults()
    with st.sidebar:
        with st.expander("🎨 Tema visual", expanded=False):
            st.radio(
                "Preset de cor",
                options=list(VALID_PRESETS),
                format_func=lambda x: _LABELS.get(x, x),
                key=SESSION_PRESET_KEY,
                help=(
                    "Combina com o tema claro/escuro do Streamlit "
                    "(menu ☰ → Configurações → Aparência). "
                    "Claro Anthropic funciona melhor no modo claro; "
                    "Spotify escuro no modo escuro."
                ),
            )
            st.caption(
                "Modo claro/escuro global: ☰ **Configurações do app** → **Aparência**."
            )


def wiki_theme_apply_authenticated() -> None:
    """
    Aplica tema para sessões autenticadas: CSS + controlo na sidebar.

    Deve ser chamado depois de `st.set_page_config` e da verificação de login.
    """
    if not st.session_state.get("autenticado"):
        return
    inject_theme_stylesheet()
    render_theme_sidebar_controls()
