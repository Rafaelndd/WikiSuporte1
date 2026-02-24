"""
PSY BI Analytic.
Desenvolvido por: [Rafael D. Nasciemento]
Data: 2026-02-19
Descrição:
Este é o código principal do Dashboard de Suporte, onde implementamos a interface, a lógica de autenticação, controle de acesso (RBAC) e as visualizações dos dados. O PSY é o assistente virtual que automatiza a coleta de dados e facilita a análise das métricas do suporte técnico.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection
from modules.auditoria import registrar_log_auditoria 
import bcrypt  
from datetime import datetime, timedelta # Adicionado timedelta para o cálculo de inatividade
import random
from tela_crm import tela_vinculacao_crm

#_______________________________________________________________________________#
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA E ESTILO
#_______________________________________________________________________________#
st.set_page_config(
    page_title="PSY BI Analytic - Dashboard de Suporte",
    page_icon="mascote/psy_braco_cruzado_aposto.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
# 2. CONFIGURAÇÕES DE RBAC 
# ==========================================
MENU_CONFIGURACOES = {
    1: "01 - Alterar senha dos usuários",
    2: "02 - Alterar Perfil dos usuários",
    3: "03 - Visualizar Relatórios com dados dos chamados",
    4: "04 - Visualizar Relatórios com dados dos atendimentos (Multi360 & Goto)",
    5: "05 - Visualizar Dashboard com dados dos chamados",
    6: "06 - Visualizar Dashboard com dados dos atendimentos (Multi360 & Goto)",
    7: "07 - Visualizar usuários ativos",
    8: "08 - Visualizar contribuições dos usuários",
    9: "09 - Testar comunicação com Banco de dados (Tempo real)",
    10: "10 - Testar qualidade da internet na Rede (Tempo real)",
    11: "11 - Monitor de recursos (Servidor e Rede)",
    12: "12 - Alterar senha do usuário Administrador (SuperAdmin)",
    13: "13 - Vínculo CRM (Clientes)"
}

PERMISSOES_POR_PERFIL = {
    3: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], # SuperAdmin
    2: [1, 2, 3, 4, 5, 6, 7, 8, 13],                # Coordenação
    1: [3, 5, 8]                                    # Analista de Suporte
}

# ==========================================
# 3. FUNÇÕES DE SEGURANÇA E LGPD
# ==========================================
def verificar_login(username, senha_digitada):
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT id, password_hash, perfil FROM usuarios_dashboard WHERE username = :u AND ativo = TRUE")
            resultado = conn.execute(query, {"u": username}).fetchone()
            
            if resultado:
                usuario_id = resultado[0]
                senha_hash_banco = resultado[1].encode('utf-8')
                perfil = resultado[2]
                
                if bcrypt.checkpw(senha_digitada.encode('utf-8'), senha_hash_banco):
                    return True, usuario_id, perfil
    except Exception as e:
        st.error(f"O PSY encontrou um erro durante a autenticação: {e}")
    
    return False, None, None

def verificar_aceite_termos(usuario_id):
    """Verifica no banco de dados se o usuário já aceitou os termos anteriormente"""
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM logs_auditoria_sistema WHERE usuario_id = :u AND acao = 'ACEITE_TERMOS' LIMIT 1")
            resultado = conn.execute(query, {"u": usuario_id}).fetchone()
            return bool(resultado) # Retorna True se encontrou, False se não encontrou
    except Exception as e:
        return False

def exibir_termos_uso():
    # Esconde a Sidebar inteira nesta tela
    st.markdown("""
        <style>
            [data-testid="stSidebar"] {display: none;}
        </style>
    """, unsafe_allow_html=True)
    
    st.title("PSY BI Analytic - Termo de Uso e Confidencialidade")
    st.warning("**Atenção:** Este é um ambiente restrito e protegido. O acesso e uso deste sistema estão sujeitos a termos de uso e de confidencialidade e proteção de dados. Leia atentamente antes de prosseguir.")
    
    st.markdown("""
    ### 📜 Termo de Uso e Confidencialidade de Dados (LGPD)
    Este sistema processa dados pessoais e informações estratégicas protegidas pela **Lei Geral de Proteção de Dados (Lei nº 13.709/2018)**.
    Ao acessar o Dashboard do PSY BI Analytic, você assume o compromisso de sigilo e responsabilidade conforme as cláusulas abaixo:
    
    **1. Confidencialidade e Proteção de Dados**
    Os dados exibidos (nomes de clientes, telefones, históricos de chamados e mensagens) são estritamente confidenciais.
    É **terminantemente proibido**:
    * Compartilhar capturas de tela (prints), relatórios ou credenciais com terceiros não autorizados.
    * Utilizar os dados para fins pessoais ou alheios à operação de suporte técnico.
    * Armazenar exportações de dados em dispositivos pessoais ou nuvens públicas não homologadas.
    
    **2. Monitoramento e Auditoria**
    Para fins de segurança e compliance, **todas as ações realizadas neste sistema são registradas em logs de auditoria**.
    Isso inclui horários de login, visualização de relatórios e tentativas de exportação. O "PSY" atua como agente de coleta automatizada e seus logs também são auditados.
.
    """)
    
    aceito = st.checkbox("Eu li e concordo com os termos de uso e confidencialidade acima.")
    
    if st.button("Confirmar Acesso"):
        if aceito:
            st.session_state['termos_aceitos'] = True
            usuario_logado_id = st.session_state.get('usuario_id', 0)
            
            registrar_log_auditoria(
                usuario_id=usuario_logado_id,
                acao="ACEITE_TERMOS",
                detalhes="Usuário aceitou os termos de uso e confidencialidade para acessar o PSY BI Analytic."
            )
            st.rerun() 
        else:
            st.error("Você deve aceitar os termos para utilizar o PSY BI Analytic.")

# ==========================================
# 4. BARREIRA DE ACESSO (LOGIN, TERMOS E TIMEOUT)
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

# --- Lógica de Timeout (15 Minutos de Inatividade) ---
if st.session_state['autenticado']:
    agora = datetime.now()
    ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    
    # Se a diferença entre agora e o último acesso for maior que 15 minutos
    if agora - ultimo_acesso > timedelta(minutes=15):
        st.session_state.clear() # Limpa a sessão
        st.warning("⏱️ Sua sessão expirou por inatividade (15 minutos). Por favor, faça login novamente para sua segurança.")
        st.stop()
    else:
        # Atualiza o cronômetro para o momento atual de interação
        st.session_state['ultimo_acesso'] = agora

# --- Tela de Login ---
if not st.session_state['autenticado']:
    st.markdown("""
        <style>
            [data-testid="stSidebarNav"] {display: none;}
        </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        try: st.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
        except: pass
        
        st.markdown("## 👋 Olá! Bem-vindo(a) ao PSY BI Analytic")
        st.info("**Versão 1.0.0** (Beta)")
        
        st.markdown("### 🤖 Quem é o Mascote PSY?")
        st.markdown("Seu assistente virtual de análise de dados. \n\n**Minha Missão:**\nAutomatizar a coleta de métricas e gerar insights para otimizar o atendimento do suporte.")
        
        frases_psy = ["A persistência realiza o impossível. — Provérbio Chinês", "Falar é barato. Mostre-me o código. — Linus Torvalds"]
        st.info(f"💡 ** A frase do PSY hoje é :**\n\n_{random.choice(frases_psy)}_")
        st.divider()
        st.caption("*PSY BI Analytic - Dashboard de Suporte* \nDesenvolvido por Rafael D. Nascimento - copyright © 2026")

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h2 style='text-align: center;'>Acesso ao PSY BI Analytic</h2>", unsafe_allow_html=True)
        col_img1, col_img2, col_img3 = st.columns([1, 1, 1])
        with col_img2:
            try: st.image("mascote/psy_no_dashboard.png", width=150)
            except: pass

        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite seu nome de usuário")
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no PSY BI Analytic", use_container_width=True)
            
        if btn_login:
            sucesso, user_id, user_perfil = verificar_login(usuario, senha)
            if sucesso:
                st.session_state['autenticado'] = True
                st.session_state['usuario_id'] = user_id
                st.session_state['perfil'] = user_perfil 
                
                # NOVO: Verifica no banco se já aceitou os termos no passado!
                st.session_state['termos_aceitos'] = verificar_aceite_termos(user_id)
                st.session_state['ultimo_acesso'] = datetime.now() # Inicia o cronômetro
                
                registrar_log_auditoria(user_id, "LOGIN", "Login realizado com sucesso.")
                st.rerun() 
            else:
                st.error("Usuário inativo ou senha incorreta.")

    st.stop()

# --- Tela de Termos de Uso ---
if not st.session_state.get('termos_aceitos'):
    exibir_termos_uso()
    st.stop() 

# ==========================================
# 5. CAMADA DE DADOS COM CACHE
# ==========================================
@st.cache_data(ttl=300) 
def carregar_fila_tecnuv():
    engine = get_connection()
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
            if "Última Interação (Tecnuv)" in df.columns:
                df["Última Interação (Tecnuv)"] = pd.to_datetime(df["Última Interação (Tecnuv)"])
            return df
    except Exception as e:
        st.error(f"Erro ao conectar com o banco de dados: {e}")
        return pd.DataFrame()

# ==========================================
# 6. SIDEBAR REORGANIZADA E MENU DE NAVEGAÇÃO
# ==========================================
perfil_atual = st.session_state.get('perfil', 1)
nome_perfil = "Analista" if perfil_atual == 1 else ("Coordenador" if perfil_atual == 2 else "Desenvolvedor/Administrador")

st.sidebar.title("Navegação")
opcoes_menu = ["Início", "Dashboards sobre chamados"]
if perfil_atual in [2, 3]: 
    opcoes_menu.append("Dashboards Atendimentos (Multi360 e Goto)")
opcoes_menu.append("Configurações")

menu_principal = st.sidebar.radio("Selecione o módulo:", opcoes_menu)

submenu_escolhido = None
if menu_principal == "Configurações":
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Menu de Configurações")
    
    ids_permitidos = PERMISSOES_POR_PERFIL.get(perfil_atual, [])
    opcoes_filtradas = [MENU_CONFIGURACOES[i] for i in ids_permitidos]
    
    submenu_escolhido = st.sidebar.selectbox("Selecione a funcionalidade:", opcoes_filtradas)

st.sidebar.markdown("---")

try: st.sidebar.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
except Exception: pass
    
st.sidebar.markdown("<h3 style='text-align: center;'>Olá! Eu sou o PSY 🤖</h3>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: gray;'>Seu Analista de dados.</p>", unsafe_allow_html=True)
st.sidebar.info(f"Acesso: {nome_perfil}")

frases_psy = ["Tudo parece impossível até que seja feito. — Nelson Mandela", "Falar é barato. Mostre-me o código. — Linus Torvalds"]
st.sidebar.success(f"💡 **Frase do dia:**\n_{random.choice(frases_psy)}_")

if st.sidebar.button("Sair do Sistema (Logout)", use_container_width=True):
    registrar_log_auditoria(st.session_state.get('usuario_id'), "LOGOUT", "Usuário encerrou a sessão.")
    st.session_state.clear()
    st.rerun()

# ==========================================
# 7. ROTEAMENTO DAS PÁGINAS 
# ==========================================
col_logo, col_titulo = st.columns([1, 11])
with col_logo:
    try: st.image("mascote/psy_notebook.png", width=70)
    except: pass
with col_titulo:
    st.title("PSY BI Analytic - Dashboard de Suporte")
    st.markdown("Tudo sobre o suporte em um único lugar! 🚀")

if menu_principal == "Início":
    st.write(f"Bem-vindo(a) ao seu espaço, **{nome_perfil}**! Utilize o menu lateral para navegar pelas funcionalidades e relatórios.")
    
elif menu_principal == "Dashboards sobre chamados":
    st.header("Acompanhamento dos Chamados")
    df_chamados = carregar_fila_tecnuv()
    
    if not df_chamados.empty:
        st.divider()
        col_filtro1, col_filtro2 = st.columns(2)
        status_unicos = df_chamados['Status'].dropna().unique().tolist()
        filtro_status = col_filtro1.multiselect("Filtrar por Status:", options=status_unicos, default=status_unicos)
        
        clientes_unicos = df_chamados['Cliente'].dropna().unique().tolist()
        filtro_cliente = col_filtro2.multiselect("Filtrar por Cliente (Opcional):", options=clientes_unicos)
        
        df_filtrado = df_chamados[df_chamados['Status'].isin(filtro_status)]
        if filtro_cliente: 
            df_filtrado = df_filtrado[df_filtrado['Cliente'].isin(filtro_cliente)]

        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Chamados", len(df_filtrado))
        col2.metric("Em Desenvolvimento", len(df_filtrado[df_filtrado['Status'].str.contains('Desenvolvimento', case=False, na=False)]))
        col3.metric("Pendentes", len(df_filtrado[df_filtrado['Status'].str.contains('Pendente', case=False, na=False)]))
        col4.metric("Sem Atendente Definido", len(df_filtrado[df_filtrado['Atendente'] == 'Não Atribuído']))

        st.divider()
        st.markdown("Análise Gráfica dos Chamados")
        graf_col1, graf_col2 = st.columns(2)

        with graf_col1:
            df_status_count = df_filtrado['Status'].value_counts().reset_index()
            df_status_count.columns = ['Status', 'Quantidade']
            fig_status = px.bar(df_status_count, x='Quantidade', y='Status', orientation='h', title="Volume por Status", color='Quantidade', color_continuous_scale='Blues')
            fig_status.update_layout(showlegend=False, xaxis_title="", yaxis_title="", margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_status, use_container_width=True)

        with graf_col2:
            df_clientes_count = df_filtrado['Cliente'].value_counts().head(10).reset_index()
            df_clientes_count.columns = ['Cliente', 'Quantidade']
            fig_clientes = px.pie(df_clientes_count, names='Cliente', values='Quantidade', hole=0.4, title="Top 10 Clientes com Mais Chamados")
            fig_clientes.update_traces(textposition='inside', textinfo='percent+value')
            st.plotly_chart(fig_clientes, use_container_width=True)

        st.divider()
        df_exibicao = df_filtrado.copy()
        df_exibicao["Última Interação (Tecnuv)"] = df_exibicao["Última Interação (Tecnuv)"].dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True, height=400)
        
        if perfil_atual == 3:
            if st.button("Atualizar Dados (Admin)"):
                registrar_log_auditoria(st.session_state.get('usuario_id'), "CLEAR_CACHE", "Admin forçou atualização.")
                st.cache_data.clear()
                st.rerun()

elif menu_principal == "Dashboards Atendimentos (Multi360 e Goto)":
    st.header("Gestão dos Atendimentos - Multi360 e GoTo")
    st.markdown("Aqui você pode fazer upload dos arquivos CSV exportados do Multi360 e GoTo para análise.")
    arquivo_csv = st.file_uploader("Selecione um arquivo CSV para upload:", type=["csv"])
    
    if arquivo_csv is not None:
        registrar_log_auditoria(st.session_state.get('usuario_id'), "UPLOAD_CSV", f"Upload arquivo: {arquivo_csv.name}")
        st.success("Arquivo carregado com sucesso! Processando os dados...")
        try:
            df_csv = pd.read_csv(arquivo_csv, nrows=5, sep=None, engine='python') 
            st.write("Exemplo dos dados carregados: ")
            st.dataframe(df_csv, use_container_width=True)
        except Exception as e:
            st.error(f"Ocorreu um erro ao processar o arquivo CSV:{e}")

elif menu_principal == "Configurações":
    st.header("⚙️ Configurações do Sistema")
    st.write("Você está na área de administração.")
    
    if submenu_escolhido == MENU_CONFIGURACOES[13]:
        st.divider()
        tela_vinculacao_crm() 
    else:
        st.info(f"Você selecionou: **{submenu_escolhido}**. Esta funcionalidade está em desenvolvimento pelo oráculo.")