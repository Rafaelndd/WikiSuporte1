"""
Página interna: release da versão do WikiSuporte (utilizadores autenticados).

Conteúdo principal: catálogo ``releases/releases_catalog.json`` (``utils.release_manager``).
O Markdown ``releases/WIKISUPORTE_NOTAS_DE_VERSAO.md`` permanece como anexo opcional.
"""

from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import streamlit as st

from services.release_notes_banner import RELEASE_NOTES_DATE, RELEASE_NOTES_VERSION
from services.ui_realtime import render_global_notifications_listener
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.wiki_authenticator import process_forced_logout_from_url
from utils.release_manager import ReleaseRecord, load_catalog

st.set_page_config(
    page_title="WikiSuporte — Release da versão",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

if process_forced_logout_from_url():
    st.rerun()

if not st.session_state.get("autenticado", False):
    st.info("Redirecionando para a página de login…")
    st.switch_page("app.py")

render_global_notifications_listener(show_release_banner=False)
wiki_theme_apply_authenticated()

_BASE = Path(__file__).resolve().parent.parent
_MD_PATH = _BASE / "releases" / "WIKISUPORTE_NOTAS_DE_VERSAO.md"


def _fmt_data(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _normalizar_versao_para_md(versao_catalogo: str) -> str:
    v = (versao_catalogo or "").strip().lower()
    return v[1:] if v.startswith("v") else v


def _extrair_detalhes_md_por_versao(versao_catalogo: str) -> str:
    """Extrai do markdown apenas a seção da versão correspondente."""
    if not _MD_PATH.is_file():
        return ""
    raw = _MD_PATH.read_text(encoding="utf-8")
    alvo = re.escape(_normalizar_versao_para_md(versao_catalogo))
    padrao = rf"(?ims)^##\s+Versão\s+{alvo}\b.*?(?=^\s*##\s+Versão\s+|\Z)"
    m = re.search(padrao, raw)
    return (m.group(0).strip() if m else "")


def _split_topicos(texto: str) -> list[str]:
    bruto = (texto or "").strip()
    if not bruto:
        return ["—"]

    blocos = [b.strip() for b in re.split(r"\n\s*\n+", bruto) if b.strip()]
    if len(blocos) == 1 and "\n" in blocos[0]:
        linhas = [ln.strip(" -•\t") for ln in blocos[0].splitlines() if ln.strip()]
        if len(linhas) > 1:
            blocos = linhas
    return blocos or ["—"]


def _formatar_topico_html(topico: str) -> str:
    # Remove bolinhas antigas no início para padronizar com o novo layout.
    limpo = re.sub(r"^\s*[🔴🟢🟡🟠🔵]+\s*", "", topico or "")
    esc = html.escape(limpo)
    esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
    return esc.replace("\n", "<br/>")


def _render_coluna_topicos(texto: str, *, tipo: str) -> None:
    topicos = _split_topicos(texto)
    # Um emoji por alteração, com visual mais moderno.
    emoji = "⚠️" if tipo == "era" else "✨"
    classe = "ws-release-col ws-release-col-era" if tipo == "era" else "ws-release-col ws-release-col-ficou"
    itens_html = "".join(
        f'<div class="ws-release-topic">{emoji} {_formatar_topico_html(t)}</div>'
        for t in topicos
    )
    st.markdown(f'<div class="{classe}">{itens_html}</div>', unsafe_allow_html=True)


def _render_release_expander(rec: ReleaseRecord, *, expanded: bool) -> None:
    title = f"{rec.versao} · {_fmt_data(rec.data_lancamento)}"
    with st.expander(title, expanded=expanded):
        _render_release_corpo(rec)


def _render_release_corpo(rec: ReleaseRecord) -> None:
    """Renderiza o corpo do release no layout atual."""
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Como era ⚠️")
        _render_coluna_topicos(rec.como_era, tipo="era")
    with c2:
        st.markdown("##### Como ficou ✨")
        _render_coluna_topicos(rec.como_ficou, tipo="ficou")
    st.caption(
        f"Aviso na Home: {rec.dias_notificacao} dia(s) a partir do lançamento "
        f"(último dia: {_fmt_data(rec.notificacao_ate)})."
    )
    detalhes_md = _extrair_detalhes_md_por_versao(rec.versao)
    if detalhes_md:
        with st.expander("📎 Mais detalhes deste release", expanded=False):
            st.markdown(detalhes_md)


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
        font-size: clamp(2rem, 4.8vw, 2.85rem);
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.03em;
    }
    .ws-notes-hero .wiki { color: #f85001; }
    .ws-notes-hero .suporte { color: #15789a; }
    html[data-theme="dark"] .ws-notes-hero .wiki { color: #ff9a6b; }
    html[data-theme="dark"] .ws-notes-hero .suporte { color: #5eb8d9; }
    .ws-notes-hero .meta {
        color: #6b7280;
        font-size: 0.95rem;
        margin: 0;
    }
    html[data-theme="dark"] .ws-notes-hero .meta { color: #9ca3af; }
    .ws-release-col {
        border-radius: 12px;
        padding: 0.35rem 0.75rem;
        border: 1px solid transparent;
    }
    .ws-release-col-era {
        background: rgba(239, 68, 68, 0.08);
        border-color: rgba(239, 68, 68, 0.28);
    }
    .ws-release-col-ficou {
        background: rgba(34, 197, 94, 0.13);
        border-color: rgba(22, 163, 74, 0.35);
    }
    html[data-theme="dark"] .ws-release-col-era {
        background: rgba(127, 29, 29, 0.3);
        border-color: rgba(248, 113, 113, 0.4);
    }
    html[data-theme="dark"] .ws-release-col-ficou {
        background: rgba(20, 83, 45, 0.45);
        border-color: rgba(74, 222, 128, 0.45);
    }
    .ws-release-topic {
        padding: 0.6rem 0.2rem;
        line-height: 1.5;
        border-bottom: 1px dashed rgba(107, 114, 128, 0.35);
    }
    .ws-release-topic:last-child {
        border-bottom: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

catalog = load_catalog(create_if_missing=True)
latest = catalog[0] if catalog else None
hero_version = latest.versao if latest else RELEASE_NOTES_VERSION
hero_date = latest.data_lancamento if latest else RELEASE_NOTES_DATE

st.markdown(
    f"""
    <div class="ws-notes-hero">
        <h1 aria-label="WikiSuporte Release da versão">
            <span class="wiki">Wiki</span><span class="suporte">Suporte</span>
        </h1>
        <p class="meta"><strong>Release da versão</strong> · Último release · {hero_version} · {_fmt_data(hero_date)}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

if not catalog:
    st.warning("Ainda não há releases registadas no sistema.")
else:
    aba_ultimo, aba_historico = st.tabs(
        ["🚀 Último Release", "🗂️ Histórico de releases"]
    )

    with aba_ultimo:
        if latest:
            st.subheader("Último Release", anchor=False)
            st.caption("Aqui fica o conteúdo completo da versão atual do sistema.")
            st.markdown(f"**{latest.versao} · {_fmt_data(latest.data_lancamento)}**")
            _render_release_corpo(latest)
        else:
            st.info("Nenhum release disponível.")

    with aba_historico:
        historico = catalog[1:] if len(catalog) > 1 else []
        st.subheader("Histórico de releases", anchor=False)
        if not historico:
            st.caption("Ainda não há versões anteriores ao último release.")
        else:
            st.caption("Aqui ficam as versões anteriores, da mais recente para a mais antiga.")
            for rec in historico:
                _render_release_expander(rec, expanded=False)
