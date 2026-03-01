import streamlit as st
import bcrypt
import random
from datetime import datetime, timedelta
from sqlalchemy import text
from typing import Tuple, Optional
from modules.database import get_connection

# Tenta importar a função de auditoria (Ajuste o caminho se necessário)
try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    # Fallback caso o ficheiro não exista ainda
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass

# ==========================================
# 1. CONFIGURAÇÃO GLOBAL E ESTILO
# ==========================================
st.set_page_config(page_title="WikiSuporte", page_icon="💡", layout="wide")

# ==========================================
# 2. INICIALIZAÇÃO DE SESSÃO
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'termos_aceitos' not in st.session_state:
    st.session_state['termos_aceitos'] = False

# ==========================================
# 3. FUNÇÕES DE SEGURANÇA E BANCO DE DADOS
# ==========================================
def verificar_login(username: str, senha_digitada: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """Valida as credenciais comparando o Hash bcrypt no banco de dados."""
    engine = get_connection()
    try:
        with engine.connect() as conn:
            # Garante que apenas utilizadores ATIVOS possam fazer login
            query = text("SELECT id, password_hash, perfil FROM usuarios WHERE nome ILIKE :u AND ativo = TRUE")
            resultado = conn.execute(query, {"u": username}).fetchone()
            
            if resultado:
                usuario_id = resultado[0]
                senha_hash_banco = resultado[1]
                perfil = resultado[2]
                
                # O banco devolve string, o bcrypt precisa de bytes
                if isinstance(senha_hash_banco, str):
                    senha_hash_banco = senha_hash_banco.encode('utf-8')
                    
                if bcrypt.checkpw(senha_digitada.encode('utf-8'), senha_hash_banco):
                    return True, usuario_id, perfil
    except Exception as e:
        st.error(f"WikiSuporte encontrou um erro durante a autenticação:{e}")
    
    return False, None, None

def verificar_aceite_termos(usuario_id: int) -> bool:
    """Verifica nos logs de auditoria se o utilizador já aceitou os termos no passado."""
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM logs_auditoria_sistema WHERE usuario_id = :u AND acao = 'ACEITE_TERMOS' LIMIT 1")
            resultado = conn.execute(query, {"u": usuario_id}).fetchone()
            return bool(resultado)
    except Exception:
        return False

def obter_saudacao() -> str:
    """Retorna a saudação correta baseada no fuso horário do utilizador."""
    hora_atual = datetime.now().hour
    if 5 <= hora_atual < 12: return "Bom dia"
    elif 12 <= hora_atual < 18: return "Boa tarde"
    else: return "Boa noite"

# ==========================================
# 4. PROTEÇÃO CONTRA INATIVIDADE (TIMEOUT)
# ==========================================
if st.session_state['autenticado']:
    agora = datetime.now()
    ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    
    # Se passou mais de 50 minutos sem interação, desloga o utilizador
    if agora - ultimo_acesso > timedelta(minutes=50):
        st.session_state.clear() 
        st.warning("⏱️ Sessão expirada por inatividade. Por favor, faça login novamente para continuar.")
        st.stop()
    else:
        st.session_state['ultimo_acesso'] = agora

# ==========================================
# 5. TELAS (VIEWS) DO SISTEMA
# ==========================================
def tela_login() -> None:
    """Interface de Login Segura e Centralizada."""
    
    # 🚨 MÁSCARA DE SEGURANÇA MÁXIMA: Oculta completamente a barra lateral e o botão de expandir
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
        </style>
    """, unsafe_allow_html=True)

    # Espaçamento no topo
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # Layout em 3 colunas para centralizar o formulário no meio da tela
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 1.5, 1])

    with col_centro:
        # 1. ÁREA DE BRANDING (Logotipo e Título)
        c_img1, c_img2, c_img3 = st.columns([1, 2, 1])
        with c_img2:
            try:
                st.image("mascote/psy_no_dashbsoard.png", use_container_width=True)
            except: pass
            
        st.markdown("<h2 style='text-align: center;'>WikiSuporte</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Gestão e Centralização de Atendimentos</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # 2. CAIXA DO FORMULÁRIO (Card com borda)
        with st.container(border=True):
            st.markdown("<h4 style='text-align: center;'>🔐 Acesso Restrito</h4>", unsafe_allow_html=True)
            
            with st.form("form_login"):
                usuario = st.text_input("👤 Usuário", placeholder="Insira o seu nome de usuário")
                senha = st.text_input("🔑 Senha", type="password", placeholder="••••••••")
                st.markdown("<br>", unsafe_allow_html=True)
                btn_login = st.form_submit_button("Acessar Sistema", type="primary", use_container_width=True)
                
            if btn_login:
                if usuario and senha:
                    sucesso, user_id, user_perfil = verificar_login(usuario, senha)
                    if sucesso:
                        st.session_state['autenticado'] = True
                        st.session_state['usuario_id'] = user_id
                        st.session_state['usuario_nome'] = usuario
                        st.session_state['perfil'] = user_perfil 
                        st.session_state['termos_aceitos'] = verificar_aceite_termos(user_id)
                        st.session_state['ultimo_acesso'] = datetime.now() 
                        
                        registrar_log_auditoria(user_id, "LOGIN", "Usuário autenticou-se com sucesso.")
                        st.success("✅ Login bem-sucedido! Redirecionando...")
                        st.rerun() 
                    else:
                        st.error("❌ Usuário ou senha incorretos. Por favor, tente novamente.")
                else:
                    st.warning("⚠️ Por favor, preencha ambos os campos de usuário e senha.")

        # 3. PENSAMENTO DO DIA (Rodapé)
        st.markdown("<br>", unsafe_allow_html=True)
        frases = [
            "“Conhecereis a verdade, e a verdade vos libertará.” — Jesus Cristo",
            "“A persistência realiza o impossível.” — Confúcio",
            "“A qualidade nunca é um acidente; é sempre o resultado de um esforço inteligente.” — John Ruskin",
            "“Você não precisa ser grande para começar, mas precisa começar para ser grande.” — Zig Ziglar",
            "“O sucesso é a soma de pequenos esforços repetidos dia após dia.” — Robert Collier",
            "“O trabalho em equipe é o combustível que permite a pessoas comuns alcançarem resultados incomuns.” — Andrew Carnegie",
            "“A excelência não é um ato, mas um hábito.” — Aristóteles",
            "“A única maneira de fazer um excelente trabalho é amar o que você faz.” — Steve Jobs",
            "“O talento vence jogos, mas o trabalho em equipe ganha campeonatos.” — Michael Jordan"
        ]
        st.success(f"💡 **Pensamento do dia:**\n\n_{random.choice(frases)}_")
        st.caption("© 2026 WikiSuporte — Desenvolvido por Rafael D. Nascimento.")

def tela_termos_uso() -> None:
    """Tela de bloqueio LGPD. O utilizador não passa daqui sem aceitar."""
    # Oculta a barra lateral também na tela de LGPD
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
        </style>
    """, unsafe_allow_html=True)
    
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 3, 1])
    with col_centro:
        st.title("📜 Termo de Uso e Confidencialidade")
        st.warning("⚠️ **Atenção:** Ambiente restrito e protegido. O acesso e uso deste sistema estão condicionados às políticas de confidencialidade vigentes.")
        
        with st.container(border=True):
            st.markdown("""
            ### Proteção de Dados (LGPD)
            Este sistema processa dados pessoais e informações estratégicas protegidas pela **Lei nº 13.709/2018**.
            
            **1. Confidencialidade**
            Os dados exibidos são confidenciais. É **terminantemente proibido**:
            * Partilhar capturas de tela (prints) ou credenciais com terceiros.
            * Armazenar exportações de dados em dispositivos pessoais.
            
            **2. Monitorização e Auditoria**
            Para fins de segurança, todas as ações realizadas neste sistema são registadas em logs de auditoria.
            """)
        
        st.markdown("<br>", unsafe_allow_html=True)
        aceito = st.checkbox("Eu li, compreendo e concordo com os termos de uso e confidencialidade descritos acima.")
        
        if st.button("Aceitar Termos e Entrar", type="primary", use_container_width=True):
            if aceito:
                st.session_state['termos_aceitos'] = True
                registrar_log_auditoria(st.session_state.get('usuario_id'), "ACEITE_TERMOS", "Usuário leu e aceitou os termos da LGPD.")
                st.rerun() 
            else:
                st.error("❌ É obrigatório marcar a caixa de seleção para aceitar os termos e prosseguir.")

def tela_home() -> None:
    """Hub de Lançamento (Launchpad) interativo Pós-Login."""
    nome_usuario = str(st.session_state.get('usuario_nome', '')).capitalize()
    perfil_usuario = str(st.session_state.get('perfil', 'analista')).lower()
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # --- CONSTRUÇÃO DA BARRA LATERAL (PÓS-LOGIN) ---
    st.sidebar.markdown(f"## 👤 {nome_usuario}")
    st.sidebar.markdown(f"### {obter_saudacao()}!")
    st.sidebar.caption(f"🛡️ Perfil: **{perfil_usuario.title()}**")
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True):
        registrar_log_auditoria(st.session_state.get('usuario_id'), "LOGOUT", "Usuário saiu do sistema.")
        st.session_state.clear()
        st.rerun()
    # -----------------------------------------------

    # --- CORPO DA PÁGINA (LAUNCHPAD) ---
    st.markdown(f"<h1>{obter_saudacao()}, {nome_usuario}! 👋</h1>", unsafe_allow_html=True)
    st.caption(f"📅 Hoje é **{data_atual}** | 🏢 Ambiente Seguro WikiSuporte")
    st.divider()

    # Layout Principal
    col_principal, col_lateral = st.columns([2.5, 1])

    with col_principal:
        st.markdown("### 🚀 O que vamos fazer hoje?")
        st.write("A WikiSuporte centraliza a nossa operação. Escolha o seu destino abaixo:")
        st.markdown("<br>", unsafe_allow_html=True)

        # Cards Visuais de Navegação com Botões Interativos
        c_card1, c_card2, c_card3 = st.columns(3)
        
        with c_card1:
            with st.container(border=True):
                st.markdown("#### 🏠 Home")
                st.caption("Visão geral, comunicados e avisos da equipe.")
                st.markdown("<br>", unsafe_allow_html=True)
                # O botão interativo que leva para a página 0
                if st.button("Ir para Home", key="btn_home", type="primary", use_container_width=True):
                    st.switch_page("pages/0_🏠_Home_WikiSuporte.py")
                
        with c_card2:
            with st.container(border=True):
                st.markdown("#### 📊 Dashboards")
                st.caption("Acompanhe o desempenho da equipe e a telefonia.")
                st.markdown("<br>", unsafe_allow_html=True)
                # O botão interativo que leva para a página 1
                if st.button("Ir para Dashboards", key="btn_dash", type="primary", use_container_width=True):
                    st.switch_page("pages/1_📊_Dashboard_Atendimentos.py")
                
        with c_card3:
            with st.container(border=True):
                st.markdown("#### 📁 Importação")
                st.caption("Alimente o banco de dados e faça a gestão do CRM.")
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Validação visual de permissão baseada no perfil + Bloqueio do Botão
                if perfil_usuario in ["desenvolvedor", "coordenação"]:
                    # O botão interativo que leva para a página 2 (Apenas para gestão)
                    if st.button("Ir para Importação", key="btn_imp", type="primary", use_container_width=True):
                        st.switch_page("pages/2_📁_Importacao_Dados.py")
                else:
                    st.error("⛔ Acesso Restrito")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Mural de Atualizações
        with st.container(border=True):
            st.markdown("#### 📌 Atualizações do Sistema")
            st.write("✅ **Telefonia:** Filtros de Caixa Postal e Transferências aplicados com sucesso aos KPIs.")
            st.write("✅ **Segurança:** Anonimização (LGPD) ativa em todas as importações de planilhas.")

    with col_lateral:
        # Tenta carregar a mascote
        try:
            st.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
        except:
            pass

        with st.container(border=True):
            st.markdown("#### 💡 Dica Rápida")
            st.write("Você também pode usar o menu lateral escondido à esquerda para navegar rapidamente entre as telas sem precisar voltar aqui!")

# ==========================================
# 6. CONTROLADOR DE FLUXO PRINCIPAL
# ==========================================
if not st.session_state['autenticado']:
    tela_login()
elif not st.session_state['termos_aceitos']:
    tela_termos_uso()
else:
    tela_home()