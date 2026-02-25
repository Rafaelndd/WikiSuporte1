import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection

st.set_page_config(page_title="Tickets EPSY", page_icon="📊", layout="wide")
if not st.session_state.get('autenticado'): st.switch_page("app.py")

@st.cache_data(ttl=300)
def carregar_tickets_cruzados():
    engine = get_connection()
    try:
        query = text("""
            SELECT t.*, u.nome as nome_analista, c.status_atual as status_tecnuv
            FROM tickets_epsy t
            LEFT JOIN usuarios_dashboard u ON t.id_usuario_epsy = u.id
            LEFT JOIN chamados_tecnuv c ON t.chamado_vinculado = c.nr_chamado
        """)
        df = pd.read_sql(query, engine)
        if not df.empty and 'data_abertura' in df.columns:
            df['data_abertura'] = pd.to_datetime(df['data_abertura'], errors='coerce')
        return df
    except: return pd.DataFrame()

st.title("📊 Dashboard Analítico - Tickets EPSY")
st.markdown("Monitorização de tickets de clientes integrados com chamados Tecnuv.")

df_raw = carregar_tickets_cruzados()
if df_raw.empty:
    st.warning("Nenhum ticket encontrado. O Bot de Logística importará os dados em breve.")
    st.stop()

with st.expander("⚙️ Filtros da Fila", expanded=True):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filtro = st.selectbox("Status do Ticket:", ["Todos"] + sorted(df_raw['status'].dropna().unique().tolist()))
    with col_f2:
        analista_filtro = st.selectbox("Analista Responsável:", ["Todos"] + sorted(df_raw['nome_analista'].dropna().unique().tolist()))

df = df_raw.copy()
if status_filtro != "Todos": df = df[df['status'] == status_filtro]
if analista_filtro != "Todos": df = df[df['nome_analista'] == analista_filtro]

c1, c2 = st.columns(2)
with c1:
    st.subheader("Fila de Tickets")
    st.dataframe(df[['id_ticket', 'cliente_nome', 'status', 'nome_analista', 'chamado_vinculado', 'status_tecnuv']], hide_index=True, use_container_width=True)
with c2:
    st.subheader("Tickets por Analista")
    df_grafico = df['nome_analista'].value_counts().reset_index()
    df_grafico.columns = ['Analista', 'Volume']
    st.plotly_chart(px.bar(df_grafico, x='Volume', y='Analista', orientation='h', color='Volume', color_continuous_scale='Blues'), use_container_width=True)