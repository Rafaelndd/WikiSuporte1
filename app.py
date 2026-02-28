import streamlit as st
import bcrypt
import random
from datetime import datetime, timedelta
from sqlalchemy import text
from modules.database import get_connection

# Tenta importar a função de auditoria (Ajuste o caminho se necessário)
try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    # Fallback caso o ficheiro não exista ainda
    def registrar_log_auditoria(user_id, acao, detalhe): pass

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
def verificar_login(username, senha_digitada):
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
        st.error(f"Ocorreu um erro de comunicação com o banco de dados: {e}")
    
    return False, None, None

def verificar_aceite_termos(usuario_id):
    """Verifica nos logs de auditoria se o utilizador já aceitou os termos no passado."""
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM logs_auditoria_sistema WHERE usuario_id = :u AND acao = 'ACEITE_TERMOS' LIMIT 1")
            resultado = conn.execute(query, {"u": usuario_id}).fetchone()
            return bool(resultado)
    except Exception as e:
        return False

def obter_saudacao():
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
    
    # Se passou mais de 15 minutos sem interação, desloga o utilizador
    if agora - ultimo_acesso > timedelta(minutes=15):
        st.session_state.clear() 
        st.warning("⏱️ A sua sessão expirou por inatividade (15 minutos de proteção). Faça login novamente.")
        st.stop()
    else:
        st.session_state['ultimo_acesso'] = agora

# ==========================================
# 5. TELAS (VIEWS) DO SISTEMA
# ==========================================
def tela_login():
    """Interface de Login (Com bloqueio de menu lateral)."""
    # Esconde as páginas do menu lateral para quem não tem login
    st.markdown("""<style>[data-testid="stSidebarNav"] {display: none;}</style>""", unsafe_allow_html=True)

    with st.sidebar:
        try: st.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
        except: pass
        
        st.markdown("## 👋 Bem-vindo(a) ao WikiSuporte")
        st.info("**Versão 1.0.0** (Beta)")
        
        st.markdown("### 🤖 O que é o sistema?")
        st.markdown("O WikiSuporte é uma central de inteligência desenvolvida para gerir, analisar e proteger os dados dos atendimentos. Garantimos segurança e conformidade total com a LGPD.")
        
        frases = ["A persistência realiza o impossível.", "Falar é barato. Mostre-me o código.", "A melhor forma de prever o futuro é inventá-lo."]
        st.success(f"💡 **Pensamento do dia:**\n\n_{random.choice(frases)}_")
        st.divider()
        st.caption("WikiSuporte | Desenvolvido e pensado por Rafael D. Nascimento | © 2026.")

    # Formulário centralizado
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("")
        st.write("")
        st.markdown("<h1 style='text-align: center;'>🔐 WikiSuporte - Login</h1>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario = st.text_input("👤 Usuário", placeholder="Digite o seu nome de usuário")
            senha = st.text_input("🔑 Senha", type="password")
            btn_login = st.form_submit_button("Entrar no WikiSuporte", use_container_width=True)
            
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
                    
                    registrar_log_auditoria(user_id, "LOGIN", "Login realizado com sucesso.")
                    st.success("Autenticação bem sucedida!")
                    st.rerun() 
                else:
                    st.error("Usuário inativo ou senha incorreta.")
            else:
                st.warning("Preencha todos os campos para continuar.")

def tela_termos_uso():
    """Tela de bloqueio LGPD. O utilizador não passa daqui sem aceitar."""
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    
    st.title("WikiSuporte - Termo de Uso e Confidencialidade")
    st.warning("⚠️ **Atenção:** Este é um ambiente restrito e protegido. O acesso e uso deste sistema estão sujeitos a termos de confidencialidade e proteção de dados. Leia atentamente.")
    
    st.markdown("""
    ### 📜 Proteção de Dados (LGPD)
    Este sistema processa dados pessoais e informações estratégicas protegidas pela **Lei Geral de Proteção de Dados (Lei nº 13.709/2018)**.
    Ao acessar este sistema, WikiSuporte, você assume o compromisso de sigilo:
    
    **1. Confidencialidade**
    Os dados exibidos (nomes de clientes, históricos e mensagens) são confidenciais. É **terminantemente proibido**:
    * Partilhar capturas de ecrã (prints) ou credenciais com terceiros.
    * Armazenar exportações de dados em dispositivos pessoais.
    
    **2. Monitorização e Auditoria**
    Para fins de segurança e *compliance*, **todas as ações realizadas neste sistema são registadas em logs de auditoria**.
    
    **3. Responsabilidade**
    O acesso e uso deste sistema são da sua responsabilidade exclusiva.
    """)
    
    aceito = st.checkbox("Eu li, compreendo e concordo com os termos de uso e confidencialidade descritos acima.")
    
    if st.button("Assinar Termo e Confirmar Acesso", type="primary"):
        if aceito:
            st.session_state['termos_aceitos'] = True
            registrar_log_auditoria(st.session_state.get('usuario_id'), "ACEITE_TERMOS", "Usuário leu e aceitou os termos da LGPD.")
            st.rerun() 
        else:
            st.error("Você deve marcar a caixa de seleção aceitando os termos para utilizar o WikiSuporte.")

def tela_home():
    """Página Inicial após login e aceite dos termos."""
    
    nome_usuario = str(st.session_state.get('usuario_nome', '')).capitalize()
    perfil_usuario = str(st.session_state.get('perfil', 'analista')).lower()
    
    # --- CONSTRUÇÃO DA BARRA LATERAL (PÓS-LOGIN) ---
    st.sidebar.markdown(f"## 👤 {nome_usuario}")
    st.sidebar.markdown(f"### {obter_saudacao()}!")
    st.sidebar.caption(f"🛡️ Perfil: **{perfil_usuario.title()}**")
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sair do Sistema"):
        registrar_log_auditoria(st.session_state.get('usuario_id'), "LOGOUT", "Usuário saiu do sistema.")
        st.session_state.clear()
        st.rerun()
    # -----------------------------------------------

    # --- CORPO DA PÁGINA HOME ---
    st.title(f"{obter_saudacao()}, {nome_usuario}! 👋")
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("Bem-vindo(a) à sua central de operações.")
        st.write("Utilize o **menu lateral esquerdo** para navegar entre as páginas e aceder aos módulos de relatórios, robôs de raspagem ou painéis de utilizadores.")
        st.info("💡 **Dica de UX:** Se estiver a utilizar um telemóvel ou ecrã pequeno, clique no ícone `>` no canto superior esquerdo para abrir o menu.")
        
    with col2:
        st.success("🛡️ **Conformidade Ativa**\n\nO seu acesso está a ser auditado para proteção da sua operação e dos dados dos clientes (LGPD).")

# ==========================================
# 6. CONTROLADOR DE FLUXO PRINCIPAL
# ==========================================
# A magia acontece aqui: A ordem das verificações define o que o utilizador vê.

if not st.session_state['autenticado']:
    tela_login()
elif not st.session_state['termos_aceitos']:
    tela_termos_uso()
else:
    tela_home()