import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection
from services.auth_guard import require_login

# ==========================================
# 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# ==========================================
st.set_page_config(page_title="Wiki Suporte", page_icon="📊", layout="wide")

# Exige login (todos os perfis autenticados podem ver este dashboard)
perfil_logado = require_login()

# ==========================================
# 2. CARREGAMENTO DE DADOS E CORREÇÃO SQL
# ==========================================
@st.cache_data(ttl=300)
def carregar_tickets_cruzados():
    try:
        engine = get_connection()
        # Query corrigida: Usando as colunas reais mapeadas no schema
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
                COALESCE(u.nome, t.nome_analista_epsy, 'Não Atribuído') as nome_analista, 
                c.status_atual as status_tecnuv
            FROM tickets_epsy t
            LEFT JOIN usuarios u ON t.id_analista_epsy = u.id
            LEFT JOIN chamados_tecnuv c ON t.chamado_vinculado = c.nr_chamado
            ORDER BY t.data_abertura DESC
        """)
        df = pd.read_sql(query, engine)
        
        if not df.empty and 'data_abertura' in df.columns:
            df['data_abertura'] = pd.to_datetime(df['data_abertura'], errors='coerce')
            df['Mes_Ano'] = df['data_abertura'].dt.strftime('%m/%Y')
            
        return df
    except Exception as e:
        st.error(f"❌ Erro ao buscar dados dos Tickets: {e}")
        return pd.DataFrame()

# ==========================================
# 3. CABEÇALHO DO DASHBOARD
# ==========================================
st.title("📊 Dashboard Analítico - Tickets EPSY")
st.markdown("Visão executiva e operacional do atendimento. Acompanhe gargalos, volume por analista e o ciclo de vida dos tickets integrados ao fornecedor.")

df_raw = carregar_tickets_cruzados()

if df_raw.empty:
    st.warning("⚠️ WikiSuporte - Nenhum ticket encontrado no sistema ou falha de conexão.")
    st.stop()

# ==========================================
# 4. CARDS DE MÉTRICAS (KPIs)
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)

# Cálculo dinâmico de KPIs
total_tickets = len(df_raw)
tickets_abertos = len(df_raw[~df_raw['status_atual'].str.upper().isin(['CONCLUÍDO', 'FECHADO', 'RESOLVIDO'])])
tickets_avaliados = len(df_raw[df_raw['avaliacao'].notna() & (df_raw['avaliacao'] != '')])
taxa_resolucao = round(((total_tickets - tickets_abertos) / total_tickets) * 100, 1) if total_tickets > 0 else 0

c1, c2, c3, c4 = st.columns(4)
with c1:
    with st.container(border=True):
        st.metric("📦 Total de Tickets", total_tickets)
with c2:
    with st.container(border=True):
        st.metric("🔥 Tickets em Aberto", tickets_abertos, delta_color="inverse")
with c3:
    with st.container(border=True):
        st.metric("⭐ Avaliados pelo Cliente", tickets_avaliados)
with c4:
    with st.container(border=True):
        st.metric("✅ Taxa de Resolução", f"{taxa_resolucao}%")

st.divider()

# ==========================================
# 5. MOTOR DE FILTROS INTELIGENTES
# ==========================================
with st.container(border=True):
    st.markdown("#### ⚙️ Filtros Avançados")
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        meses_disp = ["Todos"] + sorted(df_raw['Mes_Ano'].dropna().unique().tolist(), reverse=True)
        mes_filtro = st.selectbox("📅 Período (Mês/Ano):", meses_disp)
    with col_f2:
        status_disp = ["Todos"] + sorted(df_raw['status_atual'].dropna().unique().tolist())
        status_filtro = st.selectbox("🚥 Status Interno:", status_disp)
    with col_f3:
        analista_disp = ["Todos"] + sorted(df_raw['nome_analista'].dropna().unique().tolist())
        analista_filtro = st.selectbox("👤 Analista Responsável:", analista_disp)

# Aplicação dos Filtros no Pandas
df = df_raw.copy()
if mes_filtro != "Todos": df = df[df['Mes_Ano'] == mes_filtro]
if status_filtro != "Todos": df = df[df['status_atual'] == status_filtro]
if analista_filtro != "Todos": df = df[df['nome_analista'] == analista_filtro]

if df.empty:
    st.info("Nenhum dado corresponde aos filtros selecionados.")
    st.stop()

# ==========================================
# 6. VISUALIZAÇÕES GRÁFICAS (UX Enterprise Plotly)
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
g1, g2 = st.columns([1, 1])

with g1:
    with st.container(border=True):
        st.markdown("#### 🏆 Volume de Tickets por Analista")
        df_analista = df['nome_analista'].value_counts().reset_index()
        df_analista.columns = ['Analista', 'Volume']
        
        fig_bar = px.bar(
            df_analista, 
            x='Volume', 
            y='Analista', 
            orientation='h', 
            text='Volume',
            color='Volume', 
            color_continuous_scale='Blues'
        )
        fig_bar.update_layout(
            template='plotly_dark', 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0),
            coloraxis_showscale=False # Esconde a barra lateral de cor para ficar mais limpo
        )
        fig_bar.update_traces(textposition='outside')
        st.plotly_chart(fig_bar, width='stretch')

with g2:
    with st.container(border=True):
        st.markdown("#### 🚥 Distribuição por Status (Fila Atual)")
        df_status = df['status_atual'].value_counts().reset_index()
        df_status.columns = ['Status', 'Quantidade']
        
        fig_donut = px.pie(
            df_status, 
            values='Quantidade', 
            names='Status', 
            hole=0.6,
            color_discrete_sequence=px.colors.sequential.Blues_r
        )
        fig_donut.update_layout(
            template='plotly_dark', 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig_donut, width='stretch')

# ==========================================
# 7. TABELA DE DADOS DETALHADA
# ==========================================
with st.container(border=True):
    st.markdown(f"#### 📋 Fila Detalhada ({len(df)} registros)")
    
    # Preparando dataframe para exibição (renomeando colunas para UX)
    df_exibicao = df[[
        'nr_ticket', 'cliente_nome', 'assunto', 'status_atual', 
        'nome_analista', 'tempo_aberto_str', 'chamado_vinculado', 'status_tecnuv'
    ]].copy()
    
    df_exibicao.columns = [
        '# Ticket', 'Cliente', 'Assunto', 'Status Interno', 
        'Analista', 'Tempo Aberto', 'Chamado Fornecedor', 'Status Fornecedor'
    ]
    
    st.dataframe(
        df_exibicao, 
        hide_index=True, 
        width='stretch',
        height=400 # Altura fixa para permitir scroll sem quebrar a tela
    )