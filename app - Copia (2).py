"""
Dashboard de Suporte - Dashboard do Suporte.
Desenvolvido por: [Rafael Duarte Nasciemento]
Data: 2026-02-19
Descrição:
Este dashboard foi criado para fornecer uma visão abrangente e interativa dos chamados do suporte. 
Ele se conecta diretamente ao banco de dados, garantindo que as informações estejam sempre atualizadas. 
O dashboard é dividido em duas abas principais: a primeira apresenta uma visão geral dos chamados, 
com KPIs e gráficos interativos; a segunda permite a importação de relatórios CSV para cruzamento de dados. 
O acesso é protegido por um sistema de login seguro, garantindo que apenas usuários autorizados possam visualizar as informações sensíveis.
Observação:
- Certifique-se de que as imagens do PSY estejam na pasta 'mascote/' para uma experiência visual completa.
- O sistema de criação de usuários foi atualizado para incluir perfis de acesso, permitindo uma gestão mais granular dos privilégios dentro do dashboard.

"""
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection
import bcrypt  # <-- Biblioteca de criptografia adicionada
import mascote
from mascote import *
from datetime import datetime

# Função simulada para gravar no banco (adapte para sua conexão SQLAlchemy)
def registrar_log_auditoria(usuario_id, acao, detalhes):

    print(f"Audit Log: User {usuario_id} | {acao} | {detalhes}")


def exibir_termos_uso():
    """
    Trava a interface do usuário até que ele aceite as regras de proteção de dados.
    """
    st.title("Dashboard do Suporte- Proteção de Dados 🛡️")
    st.warning("Atenção: Acesso Restrito e Monitorado.")
    
    st.markdown("""
    ### Termo de Confidencialidade e Uso Aceitável (LGPD)
    
    Bem-vindo ao Dashboard do Suporte. Este é um sistema corporativo de uso interno.
    
    **1. O que coletamos e armazenamos:**
    O "PSY" (nosso robô) extrai dados da plataforma Tecnuv (Chamados, Status, Assuntos, Interações) estritamente para fins de análise de métricas e suporte. 
    Todos os dados são armazenados localmente (On-Premise) de forma segura.
    
    **2. Sua Responsabilidade (Usuário):**
    * Os dados exibidos neste painel contêm informações sensíveis e PII (Informações Pessoalmente Identificáveis) de clientes.
    * É terminantemente proibido compartilhar prints, exportar dados não autorizados ou utilizar as informações para fins externos à sua função.
    * Todas as suas ações neste sistema (logins, acessos a relatórios) estão sendo registradas em logs de auditoria por exigência legal.
    
    **3. Administração e Propriedade:**
    Este software e sua lógica (incluindo o mascote PSY) são propriedade intelectual da empresa. 
    Não é permitido copiar, replicar ou utilizar esta solução fora do ambiente corporativo sem autorização expressa.
    """)
    
    aceito = st.checkbox("Li, compreendi as diretrizes da LGPD e aceito as condições de uso e monitoramento.")
    
    if st.button("Confirmar Acesso"):
        if aceito:
            # Atualiza o estado da sessão para liberar o app
            st.session_state['termos_aceitos'] = True
            
            # Grava no banco de dados que o usuário X aceitou os termos no dia/hora Y
            usuario_logado_id = st.session_state.get('usuario_id', 0)
            registrar_log_auditoria(
                usuario_id=usuario_logado_id,
                acao="ACEITE_TERMOS",
                detalhes="Usuário concordou com o Termo de Confidencialidade Interno."
            )
            st.rerun() # Recarrega a página para liberar os gráficos
        else:
            st.error("Você deve aceitar os termos para utilizar o Epsy Central.")
            
# --- LÓGICA PRINCIPAL DO APP ---


if st.session_state.get('autenticado'):
    # Checa se os termos já foram aceitos nesta sessão
    if not st.session_state.get('termos_aceitos'):
        exibir_termos_uso()
        st.stop() # Early Exit: Para a execução aqui até o aceite.
    
    # Se chegou aqui, o usuário está logado e aceitou os termos.
    st.success("Bem-vindo ao Dashboard, PSY está online! 🤖")
    # Aqui entram as suas Abas (Métricas Tecnuv, CSV, etc.)
else:
    st.write("Por favor, faça o login.")

#_______________________________________________________________________________#
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA E ESTILO
#_______________________________________________________________________________#
st.set_page_config(
    page_title="Dashboard Suporte",
    page_icon="mascote/psy_braco_cruzado_aposto.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    st.sidebar.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True,  caption="PSY - Analista de Dados do Suporte", position="center")
except Exception:
    st.sidebar.warning("Imagem do PSY não encontrada na pasta 'mascote/'.")
    
st.sidebar.markdown("<h3 style='text-align: center;'>Olá! Eu sou o PSY 🤖</h3>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: gray;'>Analista de dados e guardião de métricas do suporte.</p>", unsafe_allow_html=True)
st.sidebar.divider()


# Customização de CSS para deixar os KPIs mais bonitos
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
# 2. SISTEMA DE LOGIN SEGURO (A BARREIRA)
# ==========================================
def verificar_login(username, senha_digitada):
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT password_hash FROM usuarios_dashboard WHERE username = :u AND ativo = TRUE")
            resultado = conn.execute(query, {"u": username}).fetchone()
            
            if resultado:
                senha_hash_banco = resultado[0].encode('utf-8')
                # Compara a senha digitada com a criptografia do banco
                if bcrypt.checkpw(senha_digitada.encode('utf-8'), senha_hash_banco):
                    return True
    except Exception as e:
        st.error(f"Erro ao conectar com o banco de dados de usuários: {e}")
    return False

# Inicializa o estado da sessão (Memória do navegador)
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

# Se NÃO estiver logado, exibe a tela de login e PARA o código
if not st.session_state['autenticado']:
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h2 style='text-align: center;'>Acesso ao Dashboard do Suporte</h2>", unsafe_allow_html=True)
        
        # O PSY Padrão dá as boas vindas na tela de login
        col_img1, col_img2, col_img3 = st.columns([1, 1, 1])
        with col_img2:
            try: st.image("mascote/psy_braco_cruzado_aposto.png", width=120)
            except: pass

        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite seu nome de usuário")
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no Dashboard", use_container_width=True)
            
        if btn_login:
            if verificar_login(usuario, senha):
                st.session_state['autenticado'] = True
                st.image("mascote/psy_sorriso.png", width=100)
                st.rerun() # Recarrega a página agora com acesso liberado
            else:
                st.error("Usuário inativo ou senha incorreta.")
                try:
                    # O PSY Fica triste se errar a senha
                    st.image("mascote/psy_triste.png", width=100)
                except: pass

        # Opção de Esqueci a Senha
        with st.expander("Esqueceu a senha?"):
            col_img, col_txt = st.columns([1, 4])
            with col_img:
                try: st.image("mascote/psy_interrogacao.png", width=70)
                except: pass
            with col_txt:
                st.info("O reset de senha deve ser solicitado diretamente ao Administrador do Sistema.")
                
   
    st.stop() 


# ==========================================
# 3. SIDEBAR E LOGOUT (Só aparece se logado)
# ==========================================
try:
    st.sidebar.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
except Exception:
    st.sidebar.warning("⚠️ Imagem do PSY não encontrada na pasta 'mascote/'.")
    
st.sidebar.markdown("<h3 style='text-align: center;'>Olá! Eu sou o PSY 🤖</h3>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: gray;'>Analista de dados e guardião de métricas do suporte.</p>", unsafe_allow_html=True)
st.sidebar.divider()

# Botão para o usuário encerrar a sessão com segurança
if st.sidebar.button("🚪 Sair do Sistema (Logout)", use_container_width=True):
    st.session_state['autenticado'] = False
    st.rerun()


# ==========================================
# 4. CAMADA DE DADOS COM CACHE
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
# 5. CONSTRUÇÃO DA INTERFACE (UI)
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

# ------------------------------------------
# CONTEÚDO DA ABA 1 (TECNUV)
# ------------------------------------------
with aba1:
    st.header("Visão Geral dos Chamados")
    
    df_chamados = carregar_fila_tecnuv()
    
    if not df_chamados.empty:
        
        # --- FILTROS NO TOPO ---
        
        st.divider()
        col_filtro1, col_filtro2 = st.columns(2)
        
        status_unicos = df_chamados['Status'].dropna().unique().tolist()
        filtro_status = col_filtro1.multiselect("Filtrar por Status:", options=status_unicos, default=status_unicos,)
        st.image("mascote/psy_lupa.png", width=50)
        st.divider()
        
        
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
        st.info("O banco de dados está vazio ou não pôde ser lido. Entre em contato com o administrador do sistema.")

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