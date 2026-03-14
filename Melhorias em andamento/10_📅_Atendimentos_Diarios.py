"""
Painel: Atendimentos Diários.
Exibe os registros de atendimentos (GoTo e Multi360) realizados pelos analistas,
com filtro por data e por analista.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from sqlalchemy import text

st.set_page_config(page_title="Atendimentos Diários", page_icon="📅", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

try:
    from modules.database import get_connection
except ImportError:
    get_connection = None

if get_connection is None:
    st.error("Módulo de banco de dados não disponível.")
    st.stop()

engine = get_connection()

st.title("📅 Atendimentos Diários")
st.markdown("Visualize os registros de atendimentos (ligações GoTo e chats Multi360) por data e analista.")
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Escolha a **data** e o **analista** (ou **Todos**). Abaixo aparecem tabelas separadas para **GoTo** (ligações) e **Multi360** (chats). "
        "Os dados vêm das importações/API; se estiver vazio, confira **Importação** e se há registros naquele dia."
    )

# Filtros
with st.container(border=True):
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        data_filtro = st.date_input(
            "Data",
            value=date.today(),
            max_value=date.today(),
        )
    with c2:
        # Lista de analistas a partir dos dados
        try:
            with engine.connect() as conn:
                analistas = pd.read_sql(
                    text("""
                        SELECT DISTINCT COALESCE(nome_analista_epsy, 'Não informado') as nome
                        FROM (
                            SELECT nome_analista_epsy FROM atendimentos_goto WHERE nome_analista_epsy IS NOT NULL
                            UNION
                            SELECT nome_analista_epsy FROM atendimentos_multi360 WHERE nome_analista_epsy IS NOT NULL
                        ) u
                        ORDER BY nome
                    """),
                    conn
                )
            opcoes_analista = ["Todos"] + analistas["nome"].tolist()
        except Exception:
            opcoes_analista = ["Todos"]
        analista_filtro = st.selectbox("Analista", opcoes_analista)
    with c3:
        st.caption("Dados importados do GoTo Connect e Multi360.")

# Consulta GoTo (ligações)
data_inicio = datetime.combine(data_filtro, datetime.min.time())
data_fim = data_inicio + timedelta(days=1)

try:
    params_goto = {"dt_inicio": data_inicio, "dt_fim": data_fim}
    q_goto = """
        SELECT
            id_conversa as "ID",
            data_chamada as "Data/Hora",
            duracao_ms as "Duração (ms)",
            direcao as "Direção",
            resultado as "Resultado",
            nome_analista_epsy as "Analista"
        FROM atendimentos_goto
        WHERE data_chamada >= :dt_inicio AND data_chamada < :dt_fim
    """
    if analista_filtro != "Todos":
        q_goto += " AND nome_analista_epsy = :analista"
        params_goto["analista"] = analista_filtro

    with engine.connect() as conn:
        df_goto = pd.read_sql(text(q_goto), conn, params=params_goto)
except Exception as e:
    df_goto = pd.DataFrame()
    st.caption(f"GoTo: sem dados ou erro ({e})")

# Consulta Multi360 (chats)
try:
    params_multi = {"dt_inicio": data_inicio, "dt_fim": data_fim}
    q_multi = """
        SELECT
            protocolo as "Protocolo",
            data_inicio as "Início",
            data_finalizacao as "Fim",
            status as "Status",
            avaliacao as "Avaliação",
            nome_analista_epsy as "Analista"
        FROM atendimentos_multi360
        WHERE data_inicio >= :dt_inicio AND data_inicio < :dt_fim
    """
    if analista_filtro != "Todos":
        q_multi += " AND nome_analista_epsy = :analista"
        params_multi["analista"] = analista_filtro

    with engine.connect() as conn:
        df_multi = pd.read_sql(text(q_multi), conn, params=params_multi)
except Exception as e:
    df_multi = pd.DataFrame()
    st.caption(f"Multi360: sem dados ou erro ({e})")

# Exibição
tab_go, tab_multi, tab_resumo = st.tabs(["📞 GoTo (Ligações)", "💬 Multi360 (Chats)", "📊 Resumo"])

with tab_go:
    if df_goto.empty:
        st.info("Nenhum atendimento por ligação (GoTo) no período.")
    else:
        st.dataframe(df_goto, use_container_width='strech', hide_index=True)
        st.caption(f"Total: {len(df_goto)} registro(s)")

with tab_multi:
    if df_multi.empty:
        st.info("Nenhum atendimento por chat (Multi360) no período.")
    else:
        st.dataframe(df_multi, use_container_width='strech', hide_index=True)
        st.caption(f"Total: {len(df_multi)} registro(s)")

with tab_resumo:
    total_go = len(df_goto)
    total_multi = len(df_multi)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Ligações (GoTo)", total_go)
    with col2:
        st.metric("Chats (Multi360)", total_multi)
    with col3:
        st.metric("Total do dia", total_go + total_multi)
