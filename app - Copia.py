# app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection
import mascote
from mascote import*

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA (Executa primeiro)
# ==========================================

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA (Executa primeiro)
# ==========================================
st.set_page_config(
    page_title="Dashboard Suporte",
    page_icon="mascote/psy_braco_cruzado_aposto.png", # O PSY na aba do navegador!
    layout="wide",
    initial_sidebar_state="expanded"
)


# Customização de CSS para deixar os KPIs mais bonitos
# ==========================================
# SIDEBAR - IDENTIDADE VISUAL
# ==========================================
# ==========================================
# SIDEBAR - IDENTIDADE VISUAL DO PSY
# ==========================================
try:
    st.sidebar.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
except Exception:
    st.sidebar.warning("⚠️ Imagem do PSY não encontrada na pasta 'mascote/'.")
    
st.sidebar.markdown("<h3 style='text-align: center;'>Olá! Eu sou o PSY 🤖</h3>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: gray;'>Analista de dados e guardião de métricas do suporte.</p>", unsafe_allow_html=True)
st.sidebar.divider()

st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 5% 5% 5% 10%;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CAMADA DE DADOS COM CACHE
# ==========================================
@st.cache_data(ttl=300) 
# ==========================================
# 2. CAMADA DE DADOS COM CACHE
# ==========================================
@st.cache_data(ttl=300) 
def carregar_fila_tecnuv():
    engine = get_connection()
    
    # Query SQL cirurgicamente ajustada para as suas colunas reais
    query = """
        SELECT 
            nr_chamado AS "Chamado",
            cliente_nome AS "Cliente",
            atendente_tecnuv AS "Atendente",
            status_atual AS "Status",
            assunto_html AS "Assunto",
            motivo_abertura_html AS "Motivo",
            ultima_alteracao_tecnuv AS "Última Interação (Tecnuv)"
        FROM chamados_tecnuv
        ORDER BY ultima_alteracao_tecnuv DESC NULLS LAST
    """
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            
            # Converte a data e já deixa pronta para o Pandas trabalhar
            if "Última Interação (Tecnuv)" in df.columns:
                df["Última Interação (Tecnuv)"] = pd.to_datetime(df["Última Interação (Tecnuv)"])
                
            return df
    except Exception as e:
        st.error(f"Erro ao conectar com o banco de dados: {e}")
        return pd.DataFrame()
# ==========================================
# 3. CONSTRUÇÃO DA INTERFACE (UI)
# ==========================================
# ==========================================
# 3. CONSTRUÇÃO DA INTERFACE (UI)
# ==========================================
col_logo, col_titulo = st.columns([1, 11])

with col_logo:
    try:
        st.image("mascote/psy_notebook.png", width=70)
    except Exception:
        pass # Ignora silenciosamente se a imagem falhar aqui

with col_titulo:
    st.title("Metrics – Atendimento e Suporte")
    st.markdown("Tudo sobre o suporte em um único lugar.")

# Correção definitiva das abas (Apenas 2 textos, sem a imagem aqui)
aba1, aba2 = st.tabs(["🤖 Acompanhamento dos Chamados", "📈 Gestão do Suporte (Multi360/GoTo)"])

# st.title("📊Metrics – Atendimento e Suporte")
# st.markdown("Tudo sobre o suporte em um único lugar.")

# aba1, aba2 = st.tabs(["Tudo sobre o suporte em um único lugar)", "📈 Gestor (Métricas GoTo/Multi360)"])

# ------------------------------------------
# CONTEÚDO DA ABA 1 (TECNUV)
# ------------------------------------------
with aba1:
    st.header("Visão Geral dos Chamados")
    
    df_chamados = carregar_fila_tecnuv()
    
    if not df_chamados.empty:
        
        # --- FILTROS NO TOPO ---
        st.markdown("### 🔍 Filtros")
        col_filtro1, col_filtro2 = st.columns(2)
        
        status_unicos = df_chamados['Status'].dropna().unique().tolist()
        filtro_status = col_filtro1.multiselect("Filtrar por Status:", options=status_unicos, default=status_unicos)
        
        clientes_unicos = df_chamados['Cliente'].dropna().unique().tolist()
        filtro_cliente = col_filtro2.multiselect("Filtrar por Cliente (Opcional):", options=clientes_unicos)
        
        # Aplica os filtros
        df_filtrado = df_chamados[df_chamados['Status'].isin(filtro_status)]
        if filtro_cliente: # Se escolheu algum cliente, filtra também
            df_filtrado = df_filtrado[df_filtrado['Cliente'].isin(filtro_cliente)]

        st.divider()

        # --- KPIS (Indicadores Chave) ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Chamados Filtrados", len(df_filtrado))
        
        em_dev = len(df_filtrado[df_filtrado['Status'].str.contains('Desenvolvimento', case=False, na=False)])
        col2.metric("Em Desenvolvimento", em_dev)
        
        pendentes = len(df_filtrado[df_filtrado['Status'].str.contains('Pendente', case=False, na=False)])
        col3.metric("Pendentes", pendentes)
        
        # Conta chamados não atribuídos
        nao_atribuidos = len(df_filtrado[df_filtrado['Atendente'] == 'Não Atribuído'])
        col4.metric("Sem Atendente Definido", nao_atribuidos, delta="- Atenção" if nao_atribuidos > 0 else "OK", delta_color="inverse")

        st.divider()

        # --- GRÁFICOS INTERATIVOS (PLOTLY) ---
        st.markdown("### 📈 Análise Gráfica")
        graf_col1, graf_col2 = st.columns(2)

        with graf_col1:
            # Gráfico de Barras: Status
            df_status_count = df_filtrado['Status'].value_counts().reset_index()
            df_status_count.columns = ['Status', 'Quantidade']
            
            fig_status = px.bar(
                df_status_count, x='Quantidade', y='Status', orientation='h',
                title="Volume por Status", text='Quantidade',
                color='Quantidade', color_continuous_scale='Blues'
            )
            fig_status.update_layout(showlegend=False, xaxis_title="", yaxis_title="", margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_status, use_container_width=True)

        with graf_col2:
            # Gráfico de Rosca: Top 10 Clientes
            df_clientes_count = df_filtrado['Cliente'].value_counts().head(10).reset_index()
            df_clientes_count.columns = ['Cliente', 'Quantidade']
            
            fig_clientes = px.pie(
                df_clientes_count, names='Cliente', values='Quantidade', hole=0.4,
                title="Top 10 Clientes com Mais Chamados"
            )
            fig_clientes.update_traces(textposition='inside', textinfo='percent+value')
            fig_clientes.update_layout(margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_clientes, use_container_width=True)

        st.divider()

        # --- TABELA DE DADOS ---
        st.markdown("### 📋 Detalhamento dos Chamados")
        
        # Formata a data apenas para a exibição na tabela (mantendo o DataFrame original intacto)
        df_exibicao = df_filtrado.copy()
        df_exibicao["Última Interação (Tecnuv)"] = df_exibicao["Última Interação (Tecnuv)"].dt.strftime('%d/%m/%Y %H:%M')
        
        st.dataframe(
            df_exibicao, 
            use_container_width=True,
            hide_index=True,
            height=400
        )
        
        # Botão para limpar cache
        col_btn1, col_btn2 = st.columns([1, 5])
        with col_btn1:
            if st.button("🔄 Atualizar Dados Agora"):
                st.cache_data.clear()
                st.rerun()
                
    else:
        st.info("O banco de dados está vazio ou não pôde ser lido. Execute o robô de extração primeiro.")

# ------------------------------------------
# CONTEÚDO DA ABA 2 (GESTÃO DE CSV)
# ------------------------------------------
with aba2:
    st.header("Importação e Cruzamento de Dados (Suporte)")
    st.markdown("Faça o upload dos relatórios do **Multi360** e **GoTo** para cruzar com a base de clientes.")
    
    arquivo_csv = st.file_uploader("Selecione o arquivo CSV exportado:", type=["csv"])
    
    if arquivo_csv is not None:
        st.success("Arquivo carregado com sucesso!")
        try:
            df_csv = pd.read_csv(arquivo_csv, nrows=5, sep=None, engine='python') # sep=None tenta descobrir se é vírgula ou ponto-e-vírgula
            st.write("Pré-visualização do Arquivo:")
            st.dataframe(df_csv, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo CSV: {e}")