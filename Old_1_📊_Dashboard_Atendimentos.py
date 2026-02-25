import streamlit as st

# CADEADO DE SEGURANÇA
if 'usuario_logado' not in st.session_state or not st.session_state['usuario_logado']:
    st.switch_page("app.py")

import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection

# Tenta importar a auditoria
try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

# ==========================================
# 2. FUNÇÃO DE BUSCA DE DADOS (COM CACHE PARA PERFORMANCE)
# ==========================================
@st.cache_data(ttl=300) # Atualiza a cada 5 minutos para não sobrecarregar o banco
def carregar_dados_chamados():
    """Carrega os chamados do banco de dados para um DataFrame Pandas."""
    engine = get_connection()
    try:
        # Ajuste o nome da tabela 'chamados_tecnuv' conforme o seu banco de dados
        query = "SELECT * FROM chamados_tecnuv" 
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco: {e}")
        return pd.DataFrame()

# ==========================================
# 3. INTERFACE DO DASHBOARD
# ==========================================
st.title("📊 Dashboard de Atendimentos")
st.markdown("Visão analítica em tempo real da operação de suporte.")

# Carrega os dados
df_chamados = carregar_dados_chamados()

if df_chamados.empty:
    st.warning("Nenhum dado encontrado no banco de dados. Aguarde o robô finalizar a raspagem ou importe um arquivo CSV.")
    st.stop()

# --- BARRA DE FILTROS LATERAL (UX) ---
with st.sidebar:
    st.header("🔍 Filtros do Dashboard")
    
    # Filtro de Status
    status_disponiveis = df_chamados['status_atual'].dropna().unique().tolist()
    status_selecionados = st.multiselect("Filtrar por Status:", options=status_disponiveis, default=status_disponiveis)
    
    # Filtro de Cliente
    clientes_disponiveis = df_chamados['cliente_nome'].dropna().unique().tolist()
    cliente_selecionado = st.selectbox("Filtrar por Cliente (Opcional):", options=["Todos"] + clientes_disponiveis)

# --- APLICAÇÃO DOS FILTROS ---
df_filtrado = df_chamados[df_chamados['status_atual'].isin(status_selecionados)]
if cliente_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['cliente_nome'] == cliente_selecionado]

# Registo de auditoria silencioso de que o utilizador acessou os relatórios
registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD", f"Visualizou dashboard. Filtros: {len(status_selecionados)} status.")

# --- SEÇÃO DE KPIs (Métricas Principais) ---
st.subheader("📈 Resumo da Operação")
col1, col2, col3, col4 = st.columns(4)

total_chamados = len(df_filtrado)
em_aberto = len(df_filtrado[df_filtrado['status_atual'].str.contains("Aberto|Andamento|Analise", case=False, na=False)])
encerrados = len(df_filtrado[df_filtrado['status_atual'].str.contains("Encerrado", case=False, na=False)])
pendentes = len(df_filtrado[df_filtrado['status_atual'].str.contains("Pendente", case=False, na=False)])

col1.metric("Total de Chamados", total_chamados)
col2.metric("Em Aberto / Análise", em_aberto)
col3.metric("Encerrados", encerrados)
col4.metric("Pendentes", pendentes, delta_color="inverse")

st.divider()

# --- SEÇÃO DE GRÁFICOS ---
col_grafico1, col_grafico2 = st.columns(2)

with col_grafico1:
    st.markdown("#### Volume por Status")
    # Conta os chamados por status e cria um gráfico de barras nativo
    status_counts = df_filtrado['status_atual'].value_counts()
    st.bar_chart(status_counts)

with col_grafico2:
    st.markdown("#### Chamados por Setor")
    if 'setor' in df_filtrado.columns:
        setor_counts = df_filtrado['setor'].value_counts()
        st.bar_chart(setor_counts)
    else:
        st.info("A coluna 'setor' não está disponível para este gráfico.")

# --- TABELA DE DADOS DETALHADA ---
st.subheader("📋 Detalhamento dos Chamados")
st.markdown("Utilize a tabela abaixo para explorar os dados. Você pode clicar nos cabeçalhos para ordenar.")

# Seleciona apenas as colunas mais importantes para não poluir a tela
colunas_exibicao = ['nr_chamado', 'cliente_nome', 'status_atual', 'setor', 'situacao', 'data_abertura']
colunas_presentes = [col for col in colunas_exibicao if col in df_filtrado.columns]

st.dataframe(
    df_filtrado[colunas_presentes].sort_values(by="nr_chamado", ascending=False),
    use_container_width=True,
    hide_index=True
)