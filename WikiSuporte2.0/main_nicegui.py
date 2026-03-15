"""
WikiSuporte — Versão NiceGUI (entrada da aplicação).

Migração 1:1 do Streamlit: mesmas funcionalidades, regras de negócio,
PostgreSQL e integrações GoTo/ClickUp. Navegação por @ui.page e layout
com header + left_drawer; reatividade via bindings e @ui.refreshable.

Execute: python main_nicegui.py
        (a partir da pasta WikiSuporte2.0, com o projeto WikiSuporte1 como pai)
"""
from __future__ import annotations

import os
import random
import sys
from datetime import datetime

# Garante que o projeto pai (WikiSuporte1) esteja no path para modules/, services/, config
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
os.chdir(_ROOT)  # .env, mascote/, assets/, logs/ na raiz do projeto

from dotenv import load_dotenv
load_dotenv()

from nicegui import ui

from wiki_nicegui import state
from wiki_nicegui.auth import verificar_login
from wiki_nicegui.layout import build_drawer, build_header, obter_saudacao
from wiki_nicegui.data_home import obter_alertas_usuario, obter_kpis_home
from wiki_nicegui.data_chamados import carregar_chamados_tecnuv, lista_analistas_chamados


# -----------------------------------------------------------------------------
# Navegação (usado no drawer)
# -----------------------------------------------------------------------------
def _navigate(path: str) -> None:
    ui.navigate.to(path)


# -----------------------------------------------------------------------------
# Página raiz: Login (se não autenticado) ou Home (se autenticado)
# -----------------------------------------------------------------------------
@ui.page("/")
def index_page() -> None:
    if state.is_authenticated():
        _render_app_layout(_render_home_content)
    else:
        _render_login_page()


def _render_login_page() -> None:
    """Tela de login (paridade com tela_login() do app.py)."""
    ui.add_head_html(
        """
        <style>
            .center-card { max-width: 420px; margin: 2rem auto; padding: 1.5rem; border-radius: 12px; }
            .quote { color: #666; font-style: italic; text-align: center; margin-top: 1rem; }
        </style>
        """
    )
    usuario = ui.input("👤 Usuário", placeholder="Insira o seu nome de usuário").classes("w-full")
    senha = ui.input("🔑 Senha", password=True, placeholder="••••••••").classes("w-full")
    msg = ui.label("").classes("text-negative mt-2")
    frases = [
        "Aquele que quer ser o maior entre vós, seja o que serve. Jesus",
        "A persistência é o caminho do êxito. Charles Chaplin",
        "O melhor modo de prever o futuro é criá-lo. Alan Kay",
    ]

    def do_login() -> None:
        u = (usuario.value or "").strip()
        p = senha.value or ""
        if not u or not p:
            msg.set_text("⚠️ Preencha usuário e senha.")
            return
        ok, user_id, perfil = verificar_login(u, p)
        if ok and user_id and perfil is not None:
            try:
                from modules.auditoria import registrar_log_auditoria
                registrar_log_auditoria(user_id, "LOGIN", "Usuário autenticou-se com sucesso.")
            except Exception:
                pass
            state.set_login(user_id, u, perfil)
            ui.navigate.to("/")
            ui.navigate.reload()
        else:
            msg.set_text("❌ Usuário ou senha incorretos. Tente novamente.")

    with ui.column().classes("absolute-center items-center w-full max-w-md"):
        try:
            ui.image("/mascote/psy_no_dashbsoard.png").classes("w-48 mx-auto")
        except Exception:
            pass
        ui.label("WikiSuporte").classes("text-2xl font-bold mt-4")
        ui.label("Plataforma de Suporte Técnico").classes("text-gray-500 mb-4")
        with ui.card().classes("center-card"):
            ui.label("🔐 Login").classes("text-lg font-semibold mb-4")
            usuario.props("outlined")
            senha.props("outlined")
            ui.button("Entrar", on_click=do_login).props("unelevated color=primary").classes(
                "w-full mt-4"
            )
            msg
        ui.label(f"💡 Pensamento do dia: {random.choice(frases)}").classes("quote text-sm mt-4")
        ui.label("© 2026 WikiSuporte — Desenvolvido por Rafael D. Nascimento.").classes(
            "text-gray-400 text-xs mt-2"
        )


def _render_app_layout(content_fn) -> None:
    """Layout com header + drawer + área de conteúdo (paridade com sidebar + main do Streamlit)."""
    build_header()
    build_drawer(_navigate)
    with ui.column().classes("w-full q-pa-md"):
        content_fn()


def _render_home_content() -> None:
    """Conteúdo da Home (paridade com tela_home() do app.py)."""
    nome = (state.get_usuario_nome() or "").capitalize()
    usuario_id = state.get_usuario_id()
    dias_semana = [
        "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira",
        "Sábado", "Domingo",
    ]
    hoje = datetime.now()
    data_str = f"{dias_semana[hoje.weekday()]}, {hoje.strftime('%d/%m/%Y')}"

    saudacao = obter_saudacao()
    icone = "🌕 💻" if "noite" in saudacao.lower() else "🌤️ 💻" if "tarde" in saudacao.lower() else "☀️ 💻"
    ui.label(f"{saudacao}, {nome}! {icone}").classes("text-2xl font-bold")
    ui.label(
        "Este é o seu painel de controle central do WikiSuporte. "
        "Acompanhe os seus indicadores e os alertas do dia."
    ).classes("text-gray-600 mb-4")

    df_plantao, df_correcoes = obter_alertas_usuario(usuario_id or 0)
    total_alertas = len(df_plantao) + len(df_correcoes)
    if total_alertas > 0:
        ui.label(f"📅 {data_str}   |   ⚡ {total_alertas} alerta(s) no sistema").classes("mb-2")
    else:
        ui.label(f"📅 {data_str}").classes("mb-2")

    ui.separator()

    # KPIs e conquistas
    kpis = obter_kpis_home(usuario_id or 0)
    with ui.card().classes("w-full mb-4"):
        ui.label("🏆 Seu desempenho").classes("text-lg font-semibold mb-2")
        with ui.row().classes("gap-4 flex-wrap"):
            with ui.column().classes("p-4 border rounded"):
                ui.label("Nível").classes("text-sm text-gray-500")
                ui.label(str(kpis.get("nivel_atual", "Iniciante 🌱"))).classes("font-bold")
            with ui.column().classes("p-4 border rounded"):
                ui.label("XP Acumulado").classes("text-sm text-gray-500")
                ui.label(f"{kpis.get('meu_xp', 0)} XP").classes("font-bold")
            with ui.column().classes("p-4 border rounded"):
                ui.label("Posição no Ranking").classes("text-sm text-gray-500")
                ui.label(str(kpis.get("posicao_ranking", "N/A"))).classes("font-bold")
        ui.linear_progress(
            value=kpis.get("progresso_nivel", 0.0),
        ).classes("mt-2")
        ui.label(
            f"✨ Faltam {1000 - (kpis.get('meu_xp', 0) % 1000)} XP para o próximo nível"
        ).classes("text-xs text-gray-500 mt-1")

    # Central de notificações (estrutura simplificada; notificações reais vêm do mesmo serviço)
    notificacoes_atuais = []
    if not df_plantao.empty:
        row = df_plantao.iloc[0]
        ent = row["data_hora_entrada"]
        sai = row["data_hora_saida"]
        if hasattr(ent, "strftime"):
            ent = ent.strftime("%H:%M")
        if hasattr(sai, "strftime"):
            sai = sai.strftime("%H:%M")
        notificacoes_atuais.append({
            "id": "plantao_hoje",
            "icone": "🚨",
            "titulo": "Alerta de Escala: Plantão Hoje",
            "detalhe": f"Você está de plantão hoje, das {ent} às {sai}.",
        })
    for _, row in df_correcoes.iterrows():
        notificacoes_atuais.append({
            "id": f"chamado_{row['nr_chamado']}",
            "icone": "⚠️",
            "titulo": f"Validação Pendente: Chamado {row['nr_chamado']}",
            "detalhe": f"Release {row['versao']} requer sua validação para o chamado {row['nr_chamado']}.",
        })

    lidas = state.notificacoes_lidas()
    nao_lidas = [n for n in notificacoes_atuais if n["id"] not in lidas]

    ui.label(f"🔔 Central de Notificações ({len(nao_lidas)})").classes("text-xl font-semibold mt-4")
    if notificacoes_atuais:
        for n in nao_lidas:
            with ui.expansion(f"{n['icone']} {n['titulo']}", icon="notifications").classes("w-full"):
                ui.label(n["detalhe"])
                ui.button("Marcar como lida", on_click=lambda _, nid=n["id"]: _marcar_lida(nid)).props(
                    "flat size=sm"
                )
        if not nao_lidas:
            ui.label("✅ Tudo limpo! Nenhuma notificação pendente.").classes("text-positive mt-2")
    else:
        ui.label("Você não possui alertas no momento.").classes("text-gray-500 mt-2")


def _marcar_lida(notif_id: str) -> None:
    state.marcar_notificacao_lida(notif_id)
    ui.navigate.reload()


# -----------------------------------------------------------------------------
# Páginas internas (exigem autenticação; mesmo layout)
# -----------------------------------------------------------------------------
def _require_auth(content_fn):
    """Decorator lógico: se não autenticado, redireciona para /."""
    def wrapper():
        if not state.is_authenticated():
            ui.navigate.to("/")
            return
        _render_app_layout(content_fn)
    return wrapper


@ui.page("/dashboard-atendimentos")
def page_dashboard_atendimentos() -> None:
    _require_auth(_content_dashboard_atendimentos)()


def _content_dashboard_atendimentos() -> None:
    ui.label("📊 Dashboard de Atendimentos").classes("text-2xl font-bold")
    ui.label("Análise detalhada dos atendimentos via GoTo e Multi360.").classes("text-gray-600 mb-4")
    ui.label("(Conteúdo migrado: use os mesmos filtros e gráficos Plotly em ui.card + ui.echart)").classes(
        "text-sm text-orange"
    )


@ui.page("/importacao-dados")
def page_importacao() -> None:
    _require_auth(_content_importacao)()


def _content_importacao() -> None:
    ui.label("📁 Importação e Exportação de Relatórios").classes("text-2xl font-bold")
    ui.label("Importe relatórios do GoTo Connect e Multi360.").classes("text-gray-600 mb-4")
    ui.label("(Abas: API GoTo, Importar Mensal, Extrator Plantões — paridade com página 2)").classes(
        "text-sm text-orange"
    )


@ui.page("/dashboard-chamados")
def page_dashboard_chamados() -> None:
    _require_auth(_content_dashboard_chamados)()


def _content_dashboard_chamados() -> None:
    from datetime import timedelta
    hoje = datetime.now().date()
    data_inicio_default = hoje - timedelta(days=365)
    data_fim_default = hoje

    ui.label("🖥️ Dashboard Chamados").classes("text-2xl font-bold")
    ui.label("Análise de chamados, tempo de atendimento e reincidências.").classes("text-gray-600 mb-4")
    with ui.expansion("🤔 Como usar esta página?", icon="help").classes("w-full mb-4"):
        ui.markdown(
            "**Período padrão:** 12 meses. Ajuste **Filtros** e clique **Atualizar**. "
            "A tabela exibe chamados do banco (chamados_tecnuv)."
        )

    data_inicio = ui.date(value=data_inicio_default).props("outlined")
    data_fim = ui.date(value=data_fim_default).props("outlined")
    analistas = lista_analistas_chamados()
    analista_select = ui.select(
        options=analistas,
        value="Todos",
        label="👤 Analista EPSY",
    ).props("outlined").classes("min-w-48")

    @ui.refreshable
    def tabela_chamados() -> None:
        di = data_inicio.value
        d_fim = data_fim.value
        an = analista_select.value or "Todos"
        _, rows = carregar_chamados_tecnuv(
            data_inicio=datetime.combine(di, datetime.min.time()) if di else None,
            data_fim=datetime.combine(d_fim, datetime.min.time()) if d_fim else None,
            analista=an,
        )
        if not rows:
            ui.label("Nenhum chamado no período selecionado.").classes("text-gray-500")
            return
        cols = [{"field": k, "headerName": k.replace("_", " ").title()} for k in rows[0].keys()]
        ui.aggrid({"columnDefs": cols, "rowData": rows}).classes("w-full h-96")

    with ui.row().classes("items-end gap-4 flex-wrap mb-4"):
        ui.label("📅 Início:").classes("self-center")
        data_inicio
        ui.label("📅 Fim:").classes("self-center")
        data_fim
        analista_select
        ui.button("🔄 Atualizar", on_click=tabela_chamados.refresh).props("unelevated color=primary")

    tabela_chamados()


@ui.page("/dashboard-tickets-epsy")
def page_tickets_epsy() -> None:
    _require_auth(_content_tickets_epsy)()


def _content_tickets_epsy() -> None:
    ui.label("📊 Dashboard - Tickets EPSY").classes("text-2xl font-bold")
    ui.label("Visão dos tickets: clientes, assuntos, tempo médio.").classes("text-gray-600 mb-4")


@ui.page("/contribuicoes-suporte")
def page_contribuicoes() -> None:
    _require_auth(_content_contribuicoes)()


def _content_contribuicoes() -> None:
    ui.label("🤝 Contribuições Suporte").classes("text-2xl font-bold")
    ui.label("Base de conhecimento e revisão.").classes("text-gray-600 mb-4")


@ui.page("/registro-atendimentos")
def page_registro_atendimentos() -> None:
    _require_auth(_content_registro)()


def _content_registro() -> None:
    ui.label("📝 Registro de Atendimentos").classes("text-2xl font-bold")
    ui.label("Lançamento diário de atendimentos.").classes("text-gray-600 mb-4")


@ui.page("/feedback")
def page_feedback() -> None:
    _require_auth(_content_feedback)()


def _content_feedback() -> None:
    ui.label("💬 Canal de Feedback").classes("text-2xl font-bold")
    ui.label("Registre sugestões, críticas ou bugs.").classes("text-gray-600 mb-4")


@ui.page("/releases-tecnuv")
def page_releases() -> None:
    _require_auth(_content_releases)()


def _content_releases() -> None:
    ui.label("🧩 Cadastro Manual de Releases Tecnuv").classes("text-2xl font-bold")
    ui.label("Releases e auditoria de homologação.").classes("text-gray-600 mb-4")


@ui.page("/configuracoes")
def page_configuracoes() -> None:
    _require_auth(_content_configuracoes)()


def _content_configuracoes() -> None:
    ui.label("⚙️ Configurações").classes("text-2xl font-bold")
    ui.label("Bots, ramais, usuários, clientes e notificações.").classes("text-gray-600 mb-4")
    perfil = state.get_perfil_normalizado()
    if perfil not in ("dev", "coordenador", "supervisor"):
        ui.label("⛔ Acesso negado.").classes("text-negative mt-2")


# -----------------------------------------------------------------------------
# Execução
# -----------------------------------------------------------------------------
if __name__ in ("__main__", "nicegui"):
    # Servir pastas estáticas da raiz do projeto (mascote, assets)
    from nicegui import app as nicegui_app
    _mascote = os.path.join(_ROOT, "mascote")
    _assets = os.path.join(_ROOT, "assets")
    if os.path.isdir(_mascote):
        nicegui_app.add_static_files("/mascote", _mascote)
    if os.path.isdir(_assets):
        nicegui_app.add_static_files("/assets", _assets)

    ui.run(
        title="WikiSuporte",
        favicon="💡",
        storage_secret=os.getenv("NICEGUI_STORAGE_SECRET", "wikisuporte-nicegui-secret-change-in-prod"),
        port=int(os.getenv("PORT", 8080)),
        reload=False,
    )
