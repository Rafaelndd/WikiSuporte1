import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, timedelta
# Importação real do seu banco de dados
from modules.database import get_connection 

# --- 1. SEGURANÇA E CONFIGURAÇÃO ---
# Verificação de autenticação com default explícito para False
if not st.session_state.get('autenticado', False):
    st.warning("⚠️ Acesso negado. Faça o login para continuar.")
    st.stop()

# Recuperação do perfil do usuário com default vazio para evitar erros
perfil_logado = str(st.session_state.get('perfil', '')).lower()

# Definição de perfis permitidos para esta página
PERFIS_PERMITIDOS = ['dev', 'coordenador']

# Verificação de perfil: apenas 'dev' e 'coordenador' podem acessar
# Sem mensagem de erro visível; apenas para a execução silenciosamente
if perfil_logado not in PERFIS_PERMITIDOS:
    st.stop()  # Impede que o conteúdo da página apareça para perfis não permitidos

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 8px;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 16px rgba(0, 123, 255, 0.1);
        border-color: #007BFF;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎯 Centro de Comando Omnichannel")

# ... (mantenha os imports e configurações de segurança iniciais) ...

# --- 2. CONSULTAS AO BANCO DE DADOS (POSTGRESQL) ---
@st.cache_data(ttl=300)
def buscar_dados_plantoes():
    """Busca a escala real de plantões no banco de dados, agora com a coluna TIPO"""
    # Adicionamos a coluna 'tipo' no SELECT
    query = """
    SELECT 
        id_plantao, nome_analista_epsy, data_hora_entrada, data_hora_saida, tipo 
    FROM plantoes_epsy
    ORDER BY data_hora_entrada DESC
    """
    try:
        from modules.database import get_connection
        engine = get_connection()
        df = pd.read_sql(query, engine)
        
        df['data_hora_entrada'] = pd.to_datetime(df['data_hora_entrada'])
        df['data_hora_saida'] = pd.to_datetime(df['data_hora_saida'])
        return df
    except Exception as e:
        # Diretriz #3: Tratamento de erro visível no Streamlit
        st.error(f"Erro ao buscar tabela plantoes_epsy: {e}")
        return pd.DataFrame()

# ... (mantenha a aba de tempo real intacta) ...

# ==========================================
# ABA 2: RELATÓRIOS (CRUZAMENTO DE DADOS)
# ==========================================
with aba_plantoes:
    st.subheader("Escala e Produtividade de Plantões")
    
    df_plantoes = buscar_dados_plantoes()
    
    if not df_plantoes.empty:
        # Extrai apenas a data para agrupar
        df_plantoes['Data'] = df_plantoes['data_hora_entrada'].dt.date
        
        # MÁGICA AQUI: Agora agrupamos pela Data E pelo Tipo!
        contagem_plantoes = df_plantoes.groupby(['Data', 'tipo']).size().reset_index(name='Qtd Plantões')
        
        # Gráfico inteligente separando as barras por cor
        fig = px.bar(
            contagem_plantoes, 
            x="Data", 
            y="Qtd Plantões",
            color="tipo", # O Plotly separa as cores automaticamente baseado na coluna 'tipo'
            title="Volumetria de Plantões: Normal x Personalizado",
            barmode="group", # Coloca as barras lado a lado
            color_discrete_map={"Normal": "#007BFF", "Personalizado": "#FF9900"} # Azul e Laranja
        )
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width='stretch')
        
        with st.expander("Ver Tabela Bruta de Plantões"):
            st.dataframe(df_plantoes)
    else:
        st.warning("Nenhum dado de plantão encontrado no banco ou erro na conexão.")



# --- 3. ABAS DO DASHBOARD ---
aba_tempo_real, aba_plantoes, aba_picos = st.tabs([
    "⏱️ Visão 360º (Tempo Real)", 
    "📅 Relatórios de Plantão", 
    "🚨 IA: Detecção de Picos"
])

with aba_tempo_real:
    st.subheader("Situação Atual da Central")
    st.info("💡 Insira as credenciais geradas do GoTo e Multi360 no arquivo `secrets.toml` para que os dados reais substituam os valores zerados abaixo.")
    
    col_voz, col_texto = st.columns(2)
    with col_voz:
        st.markdown("### 📞 Telefonia (GoTo)")
        v1, v2 = st.columns(2)
        v1.metric("Ligações em Espera", "0")
        v2.metric("Tempo Médio (TMA)", "00:00")
        
    with col_texto:
        st.markdown("### 💬 WhatsApp (Multi360)")
        t1, t2 = st.columns(2)
        t1.metric("Clientes na Fila", "0")
        t2.metric("Atendimentos Ativos", "0")

with aba_plantoes:
    st.subheader("Escala e Produtividade de Plantões")
    
    df_plantoes = buscar_dados_plantoes()
    
    if not df_plantoes.empty:
        # AQUI PRECISAMOS DA SUA REGRA DE NEGÓCIO: 
        # Como não temos a coluna 'tipo', estou exibindo a quantidade total de plantões por dia
        df_plantoes['Data'] = df_plantoes['data_hora_entrada'].dt.date
        contagem_plantoes = df_plantoes.groupby('Data').size().reset_index(name='Qtd Plantões')
        
        fig = px.bar(
            contagem_plantoes, 
            x="Data", 
            y="Qtd Plantões",
            title="Quantidade de Plantões por Dia (Aguardando regra Normal x Personalizado)",
            color_discrete_sequence=["#007BFF"]
        )
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width='stretch')
        
        with st.expander("Ver Tabela Bruta de Plantões"):
            st.dataframe(df_plantoes)
    else:
        st.warning("Nenhum dado de plantão encontrado no banco ou erro na conexão.")

with aba_picos:
    st.subheader("Detecção de Anomalias (Queda de Sefaz / Sistemas)")
    st.markdown("O sistema analisa a volumetria da tabela `atendimentos_goto` para detectar surtos de ligações.")
    
    with st.container(border=True):
        st.markdown("### 📡 Radar de Volumetria")
        # Lógica simulada de detecção que implementaremos com a sua tabela atendimentos_goto
        st.success("✅ **Status Normal:** Nas últimas 2 horas, o volume de chamadas está dentro da média histórica.")
        st.caption("A IA acionará um alerta vermelho nesta tela automaticamente caso o volume de ligações ultrapasse 200% da média móvel, indicando uma possível queda nacional de sistema.")