"""
Tema visual do WikiSuporte (Streamlit).

Duas ferramentas Streamlit alinhadas às práticas recomendadas:
- ``st.markdown(..., unsafe_allow_html=True)`` para CSS de marca (paleta EPSY).
- ``streamlit.components.v1.html`` para sincronizar o tema nativo (claro/escuro)
  com ``localStorage`` no formato esperado pelo frontend do Streamlit 1.55+.

Chave de armazenamento no navegador (igual ao Streamlit):
``stActiveTheme-{pathname}-v2`` com valor ``JSON.stringify("Light"|"Dark")``.
"""

from __future__ import annotations

from typing import Final

import streamlit as st
import streamlit.components.v1 as components

from services.wiki_authenticator import render_wiki_sidebar_logout_button

# Chave da escolha do utilizador (claro / escuro)
SESSION_THEME_KEY: Final[str] = "ws_streamlit_theme"
# Guarda o valor já processado nesta sessão para detetar mudança no rádio
_SESSION_THEME_SNAPSHOT_KEY: Final[str] = "_ws_streamlit_theme_snapshot"

VALID_THEMES: Final[tuple[str, ...]] = ("light", "dark")

_LABELS: Final[dict[str, str]] = {
    "light": "Claro",
    "dark": "Escuro",
}


def normalize_theme(raw: str | None) -> str:
    """Devolve ``light`` ou ``dark``; valores desconhecidos caem em ``light``."""
    if raw in VALID_THEMES:
        return raw
    return "light"


def ensure_theme_session_defaults() -> None:
    """Garante tema inicial e migra presets antigos (anthropic_light / spotify_dark)."""
    if SESSION_THEME_KEY not in st.session_state:
        legacy = st.session_state.get("ws_ui_theme_preset")
        if legacy == "spotify_dark":
            st.session_state[SESSION_THEME_KEY] = "dark"
        elif legacy == "anthropic_light":
            st.session_state[SESSION_THEME_KEY] = "light"
        else:
            ctx_type = getattr(getattr(st, "context", None), "theme", None)
            ct = getattr(ctx_type, "type", None) if ctx_type is not None else None
            st.session_state[SESSION_THEME_KEY] = "dark" if ct == "dark" else "light"


def _streamlit_storage_label(theme: str) -> str:
    return "Dark" if normalize_theme(theme) == "dark" else "Light"


def build_theme_stylesheet(theme: str) -> str:
    """
    CSS de marca para o modo escolhido (função pura — fácil de testar).

    Reforça fundos e botões com a paleta EPSY sem depender de terceiros.
    """
    t = normalize_theme(theme)
    if t == "dark":
        return """
        <style>
        html[data-theme="dark"] .stApp {
            background: #0f1419 !important;
        }
        html[data-theme="dark"] [data-testid="stHeader"] {
            background: rgba(15, 20, 25, 0.94) !important;
            border-bottom: 1px solid #1e2a33 !important;
            backdrop-filter: blur(8px);
        }
        html[data-theme="dark"] [data-testid="stSidebar"] {
            background: #0c1014 !important;
            border-right: 1px solid #1e2a33 !important;
        }
        html[data-theme="dark"] [data-testid="stSidebar"] .stMarkdown,
        html[data-theme="dark"] [data-testid="stSidebar"] p,
        html[data-theme="dark"] [data-testid="stSidebar"] span {
            color: #e8eef2 !important;
        }
        html[data-theme="dark"] .block-container {
            color: #f0f4f7 !important;
        }
        html[data-theme="dark"] [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #243540 !important;
            background: #151d24 !important;
        }
        html[data-theme="dark"] .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #15789a 0%, #0f5f7a 100%) !important;
            border: none !important;
            color: #fff !important;
        }
        html[data-theme="dark"] a {
            color: #4db3d4 !important;
        }
        </style>
        """
    return """
        <style>
        html[data-theme="light"] .stApp {
            background: linear-gradient(180deg, #fafbfc 0%, #f3f6f8 100%) !important;
        }
        html[data-theme="light"] [data-testid="stHeader"] {
            background: rgba(250, 251, 252, 0.94) !important;
            border-bottom: 1px solid #e2e8f0 !important;
            backdrop-filter: blur(8px);
        }
        html[data-theme="light"] [data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #e2e8f0 !important;
        }
        html[data-theme="light"] .block-container {
            color: #1a202c !important;
        }
        html[data-theme="light"] .stMarkdown, html[data-theme="light"] .stCaption {
            color: #2d3748;
        }
        html[data-theme="light"] .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, #f85001 0%, #e04800 100%) !important;
            border: none !important;
            color: #fff !important;
        }
        html[data-theme="light"] .stButton > button[kind="primary"]:hover {
            box-shadow: 0 2px 10px rgba(248, 80, 1, 0.35);
        }
        html[data-theme="light"] a {
            color: #15789a !important;
        }
        </style>
        """


def inject_theme_markdown_css(theme: str | None = None) -> None:
    """Injeta o CSS de marca via ``st.markdown``."""
    ensure_theme_session_defaults()
    key = theme if theme is not None else str(st.session_state.get(SESSION_THEME_KEY, "light"))
    css = build_theme_stylesheet(key)
    st.markdown(css, unsafe_allow_html=True)


def inject_parent_data_theme_script(theme: str) -> None:
    """
    Ajusta ``data-theme`` no documento pai (iframe → app) para alinhar CSS customizado.
    """
    t = normalize_theme(theme)
    attr = "dark" if t == "dark" else "light"
    html = f"""<!DOCTYPE html><html><body><script>
    (function () {{
      try {{
        var p = window.parent;
        var root = p.document.documentElement;
        if (root) root.setAttribute("data-theme", "{attr}");
      }} catch (e) {{}}
    }})();
    </script></body></html>"""
    components.html(html, height=0, width=0)


def inject_streamlit_native_theme_reload(theme: str) -> None:
    """
    Persiste o tema no ``localStorage`` do Streamlit e recarrega a página.

    Usa a mesma chave e formato que o frontend do Streamlit 1.55+.
    """
    label = _streamlit_storage_label(theme)
    # JSON.stringify("Light") → chave com aspas no valor armazenado
    html = f"""<!DOCTYPE html><html><body><script>
    (function () {{
      try {{
        var p = window.parent;
        var key = "stActiveTheme-" + p.location.pathname + "-v2";
        p.localStorage.setItem(key, JSON.stringify("{label}"));
        p.location.reload();
      }} catch (e) {{}}
    }})();
    </script></body></html>"""
    components.html(html, height=0, width=0)


def render_theme_sidebar_controls() -> None:
    """Rádio Claro / Escuro na barra lateral; recarrega ao mudar para aplicar o tema nativo."""
    ensure_theme_session_defaults()
    with st.sidebar:
        with st.expander("Aparência", expanded=False):
            previous = st.session_state.get(_SESSION_THEME_SNAPSHOT_KEY)
            st.radio(
                "Tema",
                options=list(VALID_THEMES),
                format_func=lambda x: _LABELS.get(x, x),
                key=SESSION_THEME_KEY,
                help=(
                    "Alterna entre tema claro e escuro do Streamlit. "
                    "Ao mudar, a página recarrega uma vez para aplicar a aparência nativa."
                ),
            )
            current = normalize_theme(str(st.session_state.get(SESSION_THEME_KEY, "light")))
            if previous is not None and previous != current:
                st.session_state[_SESSION_THEME_SNAPSHOT_KEY] = current
                inject_streamlit_native_theme_reload(current)
                st.stop()
            st.session_state[_SESSION_THEME_SNAPSHOT_KEY] = current


def wiki_theme_apply_authenticated(*, show_sidebar_logout: bool = True) -> None:
    """
    Aplica tema para sessões autenticadas: CSS, ``data-theme`` e controlo na sidebar.

    Deve ser chamado depois de ``st.set_page_config`` e da verificação de login.

    ``show_sidebar_logout=False`` na Home: o ``app.py`` desenha ponto VR e chama
    ``render_wiki_sidebar_logout_button()`` por último. Nas demais páginas,
    deixe o padrão ``True`` para o Sair aparecer após o tema.
    """
    if not st.session_state.get("autenticado"):
        return
    ensure_theme_session_defaults()
    theme = normalize_theme(str(st.session_state.get(SESSION_THEME_KEY, "light")))
    inject_theme_markdown_css(theme)
    inject_parent_data_theme_script(theme)
    render_theme_sidebar_controls()
    if show_sidebar_logout:
        st.sidebar.divider()
        render_wiki_sidebar_logout_button()


def wiki_theme_apply_login_page() -> None:
    """Tela de login: só CSS + ``data-theme`` (sem recarregar nem sidebar)."""
    ensure_theme_session_defaults()
    theme = normalize_theme(str(st.session_state.get(SESSION_THEME_KEY, "light")))
    inject_theme_markdown_css(theme)
    inject_parent_data_theme_script(theme)
