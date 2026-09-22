"""
Tema visual do WikiSuporte (Streamlit) — apenas modo escuro.

Duas ferramentas Streamlit alinhadas às práticas recomendadas:
- ``st.markdown(..., unsafe_allow_html=True)`` para CSS de marca (paleta EPSY).
- ``streamlit.components.v1.html`` para sincronizar o tema nativo (escuro)
  com ``localStorage`` no formato esperado pelo frontend do Streamlit 1.55+.

Chave de armazenamento no navegador (igual ao Streamlit):
``stActiveTheme-{pathname}-v2`` com valor ``JSON.stringify("Dark")``.
"""

from __future__ import annotations

from typing import Final

import streamlit as st
import streamlit.components.v1 as components

from services.wiki_authenticator import render_wiki_sidebar_logout_button

# Chave da escolha do utilizador — mantida fixa em "dark".
SESSION_THEME_KEY: Final[str] = "ws_streamlit_theme"

VALID_THEMES: Final[tuple[str, ...]] = ("dark",)


def normalize_theme(raw: str | None) -> str:
    """Sistema opera apenas em modo escuro — qualquer valor resolve para ``dark``."""
    return "dark"


def ensure_theme_session_defaults() -> None:
    """Garante o tema escuro fixo na sessão."""
    st.session_state[SESSION_THEME_KEY] = "dark"


def build_theme_stylesheet(theme: str | None = None) -> str:
    """CSS de marca do modo escuro (função pura — fácil de testar)."""
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


def inject_theme_markdown_css(theme: str | None = None) -> None:
    """Injeta o CSS de marca do tema escuro via ``st.markdown``."""
    st.markdown(build_theme_stylesheet(), unsafe_allow_html=True)


def inject_parent_data_theme_script(theme: str | None = None) -> None:
    """Ajusta ``data-theme="dark"`` no documento pai (iframe → app)."""
    html = """<!DOCTYPE html><html><body><script>
    (function () {
      try {
        var p = window.parent;
        var root = p.document.documentElement;
        if (root) root.setAttribute("data-theme", "dark");
      } catch (e) {}
    })();
    </script></body></html>"""
    components.html(html, height=0, width=0)


def inject_sidebar_page_nav_labels_pt_br() -> None:
    """
    Traduz rótulos nativos do menu de páginas na sidebar (Streamlit multipage).

    O framework não expõe i18n para \"View less\" / \"View N more\"; o script atua
    no documento pai e reexecuta em mudanças do DOM.
    """
    html = """<!DOCTYPE html><html><body><script>
    (function () {
      function translateSidebarPageNav(doc) {
        try {
          var sidebar = doc.querySelector('[data-testid="stSidebar"]');
          if (!sidebar) return;
          var nodes = sidebar.querySelectorAll('button, a, [role="button"]');
          for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (!el) continue;
            var t = (el.textContent || '').trim();
            if (t === 'View less') {
              el.textContent = 'Ver menos';
            } else if (/^View \\d+ more$/.test(t)) {
              var m = t.match(/^View (\\d+) more$/);
              if (m) el.textContent = 'Ver mais ' + m[1];
            }
          }
        } catch (e) {}
      }
      try {
        var p = window.parent;
        var d = p.document;
        translateSidebarPageNav(d);
        var sidebar = d.querySelector('[data-testid="stSidebar"]');
        if (sidebar && typeof MutationObserver !== 'undefined') {
          var t = null;
          var obs = new MutationObserver(function () {
            if (t) clearTimeout(t);
            t = setTimeout(function () { translateSidebarPageNav(d); }, 50);
          });
          obs.observe(sidebar, { childList: true, subtree: true, characterData: true });
        }
      } catch (e) {}
    })();
    </script></body></html>"""
    components.html(html, height=0, width=0)


def wiki_theme_apply_authenticated(*, show_sidebar_logout: bool = True) -> None:
    """
    Aplica o tema escuro para sessões autenticadas: CSS e ``data-theme``.

    Deve ser chamado depois de ``st.set_page_config`` e da verificação de login.

    ``show_sidebar_logout=False`` na Home: o ``app.py`` desenha ponto VR e chama
    ``render_wiki_sidebar_logout_button()`` por último. Nas demais páginas,
    deixe o padrão ``True`` para o Sair aparecer normalmente.
    """
    if not st.session_state.get("autenticado"):
        return
    ensure_theme_session_defaults()
    inject_theme_markdown_css()
    inject_parent_data_theme_script()
    inject_sidebar_page_nav_labels_pt_br()
    if show_sidebar_logout:
        st.sidebar.divider()
        render_wiki_sidebar_logout_button()


def wiki_theme_apply_login_page() -> None:
    """Tela de login: CSS + ``data-theme`` do tema escuro (sem recarregar nem sidebar)."""
    ensure_theme_session_defaults()
    inject_theme_markdown_css()
    inject_parent_data_theme_script()
