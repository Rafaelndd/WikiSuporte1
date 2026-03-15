"""
Layout profissional: header, menu lateral (left_drawer) e área de conteúdo.

Substitui a combinação Streamlit (st.sidebar + st.columns) por componentes
NiceGUI com ui.header() e ui.left_drawer().
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from nicegui import ui

from . import state


def obter_saudacao() -> str:
    hora = datetime.now().hour
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


def build_header() -> None:
    """Cabeçalho fixo com título e identidade visual."""
    with ui.header().classes("bg-primary text-white shadow"):
        ui.label("💡 WikiSuporte").classes("text-xl font-bold")
        ui.space()
        if state.is_authenticated():
            ui.label(f"👤 {state.get_usuario_nome() or 'Usuário'}").classes("text-sm")


def build_drawer(navigate_fn: Callable[[str], None]) -> None:
    """
    Menu lateral (drawer) com links para as páginas.
    Equivalente ao st.sidebar + navegação por páginas do Streamlit.
    """
    with ui.left_drawer(fixed=True).classes("bg-slate-100") as drawer:
        drawer.props("width=280")
        if not state.is_authenticated():
            return
        nome = state.get_usuario_nome() or "Usuário"
        perfil = state.get_perfil_normalizado()
        ui.label(f"👤 {nome}").classes("text-lg font-semibold mt-2")
        ui.label(f"{obter_saudacao()}!").classes("text-sm text-gray-600")
        ui.label(f"🛡️ Perfil: {perfil.title()}").classes("text-xs text-gray-500 mb-4")
        ui.separator()

        # Links principais (paridade com páginas Streamlit)
        links = [
            ("/", "🏠 Home"),
            ("/dashboard-atendimentos", "📊 Dashboard Atendimentos"),
            ("/importacao-dados", "📁 Importação de Dados"),
            ("/dashboard-chamados", "📊 Dashboard Chamados"),
            ("/dashboard-tickets-epsy", "📊 Dashboard Tickets EPSY"),
            ("/contribuicoes-suporte", "🤝 Contribuições Suporte"),
            ("/registro-atendimentos", "📝 Registro Atendimentos"),
            ("/feedback", "💬 Feedback"),
            ("/releases-tecnuv", "🧩 Releases Tecnuv (Manual)"),
            ("/configuracoes", "⚙️ Configurações"),
        ]
        for path, label in links:
            ui.link(label, path).classes("block py-2 text-gray-700 hover:text-primary")

        ui.separator()
        with ui.expansion("🤔 Mini-FAQ", icon="help").classes("w-full"):
            ui.markdown(
                """
**Por onde começo?**  
Comece pela **Home**: alertas do dia e indicadores. Use **Importação** para relatórios. **Dashboards** para análise.

**Como sair?**  
Use o botão **Sair do Sistema** abaixo.

**Não vejo alguma página.**  
Algumas telas são restritas a **Coordenação/Dev**.
                """
            ).classes("text-sm")
        ui.separator()
        ui.button("🚪 Sair do Sistema", on_click=lambda: _logout(navigate_fn)).props(
            "flat color=negative"
        ).classes("w-full mt-2")


def _logout(navigate_fn: Callable[[str], None]) -> None:
    try:
        from modules.auditoria import registrar_log_auditoria
        uid = state.get_usuario_id()
        if uid:
            registrar_log_auditoria(uid, "LOGOUT", "Usuário saiu do sistema.")
    except Exception:
        pass
    state.logout()
    navigate_fn("/")
