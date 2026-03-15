import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from datetime import datetime, timedelta
from sqlalchemy import text
from modules.database import get_connection
from services.auth_guard import require_login
from services.ui_realtime import render_global_notifications_listener

# ==========================================
# 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# ==========================================
st.set_page_config(
    page_title="WikiSuporte - Dashboard Tickets",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
if not st.session_state.get("autenticado", False):
    st.switch_page("app.py")
render_global_notifications_listener()
perfil_logado = require_login()

# ==========================================
# 2. CARREGAMENTO DE DADOS
# ==========================================
@st.cache_data(ttl=300)
def carregar_tickets_cruzados():
    try:
        engine = get_connection()
        query = text("""
            SELECT 
                t.nr_ticket, 
                t.cliente_nome, 
                t.assunto, 
                t.data_abertura, 
                t.status_atual, 
                t.chamado_vinculado, 
                t.tempo_aberto_str, 
                t.avaliacao,
                t.data_ultima_interacao,
                COALESCE(u.nome, t.nome_analista_epsy, 'Não Atribuído') AS nome_analista, 
                c.status_atual AS status_tecnuv
            FROM tickets_epsy t
            LEFT JOIN usuarios u ON t.id_analista_epsy = u.id
            LEFT JOIN chamados_tecnuv c ON t.chamado_vinculado = c.nr_chamado
            ORDER BY t.data_abertura DESC
        """)
        df = pd.read_sql(query, engine)
        if not df.empty and "data_abertura" in df.columns:
            df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors="coerce")
            df["Mes_Ano"] = df["data_abertura"].dt.strftime("%m/%Y")
        return df
    except Exception as e:
        st.error(f"Erro ao buscar dados dos tickets: {e}")
        return pd.DataFrame()


def _status_eh_aberto(s: str) -> bool:
    """Considera aberto todo status que não for concluído/fechado/resolvido."""
    if pd.isna(s) or not str(s).strip():
        return True
    u = str(s).strip().upper()
    return u not in ("CONCLUÍDO", "CONCLUIDO", "FECHADO", "RESOLVIDO", "CANCELADO")


def _parse_tempo_aberto_str(tempo_str):
    """
    Tenta extrair dias numéricos de tempo_aberto_str (ex: '5 dias', '2 semanas', '3 horas').
    Retorna float (dias) ou None se não conseguir.
    """
    if pd.isna(tempo_str) or not str(tempo_str).strip():
        return None
    s = str(tempo_str).strip().lower()
    m = re.search(r"(\d+)\s*(dia|dias|semana|semanas|hora|horas|mes|meses)", s)
    if not m:
        return None
    num = float(m.group(1))
    un = m.group(2)
    if "dia" in un:
        return num
    if "semana" in un:
        return num * 7
    if "hora" in un:
        return num / 24.0
    if "mes" in un:
        return num * 30
    return None


# ==========================================
# 3. CABEÇALHO E FILTROS
# ==========================================
st.title("📊 Dashboard - Tickets EPSY")
st.markdown(
    "Visão executiva e operacional dos tickets: clientes que mais abrem, principais assuntos, "
    "tempo médio e fila atual. Por padrão são exibidos **somente os tickets em aberto**."
)
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Use os **filtros** para mudar período, status ou analista. O padrão é **Somente abertos**. "
        "Os **gráficos de barras** mostram quais clientes mais abriram tickets e os principais assuntos. "
        "**Tempo médio em aberto** refere-se aos tickets ainda abertos; **tempo médio até fechamento** "
    )

df_raw = carregar_tickets_cruzados()
if df_raw.empty:
    st.warning("Nenhum ticket encontrado no sistema ou falha de conexão.")
    st.stop()

# Enriquecimento: é aberto? dias em aberto? tempo parseado para fechados
df_raw["eh_aberto"] = df_raw["status_atual"].apply(_status_eh_aberto)
agora = pd.Timestamp.now(tz=df_raw["data_abertura"].dt.tz if df_raw["data_abertura"].dt.tz else None)
df_raw["dias_em_aberto"] = (agora - df_raw["data_abertura"]).dt.total_seconds() / 86400.0
df_raw["tempo_fechamento_dias"] = df_raw["tempo_aberto_str"].apply(_parse_tempo_aberto_str)

# Painel de filtros (estilo Dashboard Chamados / Atendimentos)
with st.expander("⚙️ Filtros", expanded=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    with col_f1:
        meses_disp = ["Todos"] + sorted(df_raw["Mes_Ano"].dropna().unique().tolist(), reverse=True)
        mes_filtro = st.selectbox("📅 Período (Mês/Ano):", meses_disp)
    with col_f2:
        # Opção "Somente abertos" como padrão
        tipo_filtro = st.radio(
            "📌 Exibir:",
            ["Somente abertos", "Somente fechados", "Todos"],
            index=0,
            horizontal=True,
        )
    with col_f3:
        analista_disp = ["Todos"] + sorted(df_raw["nome_analista"].dropna().unique().tolist())
        analista_filtro = st.selectbox("👤 Analista:", analista_disp)
    with col_f4:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

# Aplicar filtros
df = df_raw.copy()
if mes_filtro != "Todos":
    df = df[df["Mes_Ano"] == mes_filtro]
if analista_filtro != "Todos":
    df = df[df["nome_analista"] == analista_filtro]
if tipo_filtro == "Somente abertos":
    df = df[df["eh_aberto"]]
elif tipo_filtro == "Somente fechados":
    df = df[~df["eh_aberto"]]

if df.empty:
    st.info("Nenhum ticket corresponde aos filtros. Tente alterar período, status ou analista.")
    st.stop()

# ==========================================
# 4. KPIs (CARDS NO MESMO ESTILO DOS OUTROS DASHBOARDS)
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)

total_filtrado = len(df)
abertos_filtrado = int(df["eh_aberto"].sum())
fechados_filtrado = total_filtrado - abertos_filtrado

# Tempo médio em aberto (apenas dos que estão abertos no conjunto filtrado)
df_abertos = df[df["eh_aberto"]]
tempo_medio_aberto_dias = float(df_abertos["dias_em_aberto"].mean()) if not df_abertos.empty else 0.0
tempo_medio_aberto_str = f"{tempo_medio_aberto_dias:.1f} dias" if tempo_medio_aberto_dias else "—"

# Tempo médio até fechamento (parseado de tempo_aberto_str nos fechados)
df_fechados = df[~df["eh_aberto"]]
tempos_fech = df_fechados["tempo_fechamento_dias"].dropna()
tempo_medio_fechamento_dias = float(tempos_fech.mean()) if len(tempos_fech) else None
tempo_medio_fechamento_str = f"{tempo_medio_fechamento_dias:.1f} dias" if tempo_medio_fechamento_dias is not None else "—"

# Top cliente (mais tickets no filtro atual)
if not df.empty and "cliente_nome" in df.columns:
    cnt = df["cliente_nome"].fillna("Sem nome").value_counts()
    top_cliente = cnt.index[0] if len(cnt) else "—"
    top_cliente_qtd = int(cnt.iloc[0]) if len(cnt) else 0
else:
    top_cliente = "—"
    top_cliente_qtd = 0

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    with st.container(border=True):
        st.metric("📦 Total (filtro)", total_filtrado)
with c2:
    with st.container(border=True):
        st.metric("🔥 Em aberto", abertos_filtrado, delta_color="inverse")
with c3:
    with st.container(border=True):
        st.metric("✅ Fechados (filtro)", fechados_filtrado)
with c4:
    with st.container(border=True):
        st.metric("⏱️ Tempo médio em aberto", tempo_medio_aberto_str)
with c5:
    with st.container(border=True):
        st.metric("📊 Tempo médio até fechamento", tempo_medio_fechamento_str)

st.divider()

# ==========================================
# 5. GRÁFICOS DE BARRAS (CLIENTES, ASSUNTOS, ANALISTA)
# ==========================================
st.markdown("#### 📈 Indicadores para a equipe")
g1, g2 = st.columns(2)

with g1:
    with st.container(border=True):
        st.markdown("#### 🏢 Clientes que mais abriram tickets")
        cliente_nome_ok = df["cliente_nome"].fillna("(Sem nome)")
        top_clientes = cliente_nome_ok.value_counts().head(15)
        if top_clientes.empty:
            st.caption("Nenhum dado no filtro atual.")
        else:
            df_cli = top_clientes.reset_index()
            df_cli.columns = ["Cliente", "Quantidade"]
            fig_cli = px.bar(
                df_cli,
                x="Quantidade",
                y="Cliente",
                orientation="h",
                text="Quantidade",
                color="Quantidade",
                color_continuous_scale="Blues",
            )
            fig_cli.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=24, b=0),
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
            )
            fig_cli.update_traces(textposition="outside")
            st.plotly_chart(fig_cli, use_container_width=True)

with g2:
    with st.container(border=True):
        st.markdown("#### 📌 Principais assuntos")
        assuntos = df["assunto"].fillna("(Sem assunto)").astype(str)
        assuntos_trunc = assuntos.str.slice(0, 48) + np.where(assuntos.str.len() > 48, "…", "")
        top_assuntos = assuntos_trunc.value_counts().head(15)
        if top_assuntos.empty:
            st.caption("Nenhum dado no filtro atual.")
        else:
            df_ass = top_assuntos.reset_index()
            df_ass.columns = ["Assunto", "Quantidade"]
            fig_ass = px.bar(
                df_ass,
                x="Quantidade",
                y="Assunto",
                orientation="h",
                text="Quantidade",
                color="Quantidade",
                color_continuous_scale="Teal",
            )
            fig_ass.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=24, b=0),
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
            )
            fig_ass.update_traces(textposition="outside")
            st.plotly_chart(fig_ass, use_container_width=True)

# Segunda linha: Volume por analista + Distribuição por status
g3, g4 = st.columns(2)
with g3:
    with st.container(border=True):
        st.markdown("#### 🏆 Volume por analista")
        df_ana = df["nome_analista"].value_counts().reset_index()
        df_ana.columns = ["Analista", "Volume"]
        if df_ana.empty:
            st.caption("Nenhum dado no filtro atual.")
        else:
            fig_ana = px.bar(
                df_ana,
                x="Volume",
                y="Analista",
                orientation="h",
                text="Volume",
                color="Volume",
                color_continuous_scale="Blues",
            )
            fig_ana.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=24, b=0),
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
            )
            fig_ana.update_traces(textposition="outside")
            st.plotly_chart(fig_ana, use_container_width=True)

with g4:
    with st.container(border=True):
        st.markdown("#### 🚥 Distribuição por status")
        df_st = df["status_atual"].value_counts().reset_index()
        df_st.columns = ["Status", "Quantidade"]
        if df_st.empty:
            st.caption("Nenhum dado no filtro atual.")
        else:
            fig_st = px.pie(
                df_st,
                values="Quantidade",
                names="Status",
                hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Set1,
            )
            fig_st.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0, r=0, t=24, b=0),
            )
            st.plotly_chart(fig_st, use_container_width=True)

st.divider()

# ==========================================
# 6. TABELA DETALHADA
# ==========================================
with st.container(border=True):
    st.markdown(f"#### 📋 Fila detalhada ({len(df)} registros)")
    df_exibicao = df[
        [
            "nr_ticket",
            "cliente_nome",
            "assunto",
            "status_atual",
            "nome_analista",
            "tempo_aberto_str",
            "chamado_vinculado",
            "status_tecnuv",
        ]
    ].copy()
    df_exibicao.columns = [
        "# Ticket",
        "Cliente",
        "Assunto",
        "Status",
        "Analista",
        "Tempo aberto",
        "Chamado Fornecedor",
        "Status Fornecedor",
    ]
    st.dataframe(df_exibicao, hide_index=True, use_container_width=True, height=400)
