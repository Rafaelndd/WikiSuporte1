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
    """Interface de Login (Com bloqueio de menu lateral)."""
    # Esconde as páginas do menu lateral para quem não tem login
    st.markdown("""<style>[data-testid="stSidebarNav"] {display: none;}</style>""", unsafe_allow_html=True)

    with st.sidebar:
        try: st.image("mascote/psy_no_dashboard.png", use_container_width=True)
        except: pass
        
        st.markdown("## 👋 Bem-vindo(a) ao WikiSuporte")
        st.info("**Versão 1.0 - Beta**\n\nDesenvolvido para analistas de suporte e gestores do suporte")
        
        st.markdown("### 🤖 O que é a WikiSuporte?")
        st.markdown("A WikiSuporte centraliza informações e organiza atendimentos, ajudando a equipe de suporte a trabalhar com mais agilidade, controle e qualidade no atendimento ao cliente.")
        
        frases = [
            "“Conhecereis a verdade, e a verdade vos libertará.” — Jesus Cristo",
            "“A persistência realiza o impossível.” — Confúcio",
            "“Só sei que nada sei.” — Sócrates",
            "“A qualidade nunca é um acidente; é sempre o resultado de um esforço inteligente.” — John Ruskin",
            "“Você não precisa ser grande para começar, mas precisa começar para ser grande.” — Zig Ziglar",
            "“A educação é a arma mais poderosa que você pode usar para mudar o mundo.” — Nelson Mandela",
            "“O sucesso é a soma de pequenos esforços repetidos dia após dia.” — Robert Collier",
            "“A melhor maneira de prever o futuro é criá-lo.” — Peter Drucker",
            "“O trabalho em equipe é o combustível que permite a pessoas comuns alcançarem resultados incomuns.” — Andrew Carnegie",
            "“Aprender é a única coisa de que a mente nunca se cansa.” — Leonardo da Vinci",
            "“A disciplina é a ponte entre metas e realizações.” — Jim Rohn",
            "“Se vi mais longe, foi por estar sobre ombros de gigantes.” — Isaac Newton",
            "“Grandes realizações são possíveis quando se dá importância aos pequenos começos.” — Lao Tsé",
            "“O entusiasmo move o mundo.” — Arthur Balfour",
            "“A excelência não é um ato, mas um hábito.” — Aristóteles",
            "“A união faz a força.” — Esopo",
            "“O homem que move montanhas começa carregando pequenas pedras.” — Confúcio",
            "“Nunca é tarde para ser aquilo que se poderia ter sido.” — George Eliot",
            "“A única maneira de fazer um excelente trabalho é amar o que você faz.” — Steve Jobs",
            "“A paciência e a perseverança têm o efeito mágico de fazer as dificuldades desaparecerem.” — John Quincy Adams",
            "“O aprendizado contínuo é o mínimo requisito para o sucesso.” — Brian Tracy",
            "“Quem quer fazer algo encontra um meio; quem não quer encontra uma desculpa.” — Benjamin Franklin",
            "“A força não provém da capacidade física, mas de uma vontade indomável.” — Mahatma Gandhi",
            "“Não encontre defeitos, encontre soluções.” — Henry Ford",
            "“O sucesso normalmente vem para quem está ocupado demais para procurar por ele.” — Henry David Thoreau",
            "“O talento vence jogos, mas o trabalho em equipe ganha campeonatos.” — Michael Jordan",
            "“A simplicidade é o último grau de sofisticação.” — Leonardo da Vinci",
            "“Você se torna aquilo que acredita.” — Oprah Winfrey",
            "“Coragem é resistência ao medo, domínio do medo, e não ausência do medo.” — Mark Twain",
            "“A melhoria contínua é melhor do que a perfeição adiada.” — Mark Twain"
        ]
        st.success(f"💡 **Pensamento do dia:**\n\n_{random.choice(frases)}_")
        st.divider()
        st.caption("© 2026 WikiSuporte — Plataforma de gestão e centralização de atendimentos de suporte, desenvolvida por Rafael D. Nascimento. Todos os direitos reservados.")

    # Formulário centralizado
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write("")
        st.write("")
        st.markdown("<h1 style='text-align: center;'>🔐 WikiSuporte - Login</h1>", unsafe_allow_html=True)
        
        with st.form("form_login"):
            usuario = st.text_input("👤 Usuário", placeholder="Insira o seu nome de usuário")
            senha = st.text_input("🔑 Senha", type="password")
            btn_login = st.form_submit_button("Acessar", use_container_width=True)
            
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
                    st.success("Login bem-sucedido! Redirecionando...")
                    st.rerun() 
                else:
                    st.error("Usuário ou senha incorretos. Por favor, tente novamente.")
            else:
                st.warning("Por favor, preencha ambos os campos de usuário e senha para acessar o sistema.")

def tela_termos_uso() -> None:
    """Tela de bloqueio LGPD. O utilizador não passa daqui sem aceitar."""
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    
    st.title("WikiSuporte - Termo de Uso e Confidencialidade 📜")
    st.warning("⚠️ **Atenção:** Ambiente restrito e protegido. O acesso e uso deste sistema estão condicionados às políticas de confidencialidade e proteção de dados vigentes. Leia atentamente antes de prosseguir.")
    
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
    
    if st.button("Aceitar Termos de Uso", type="primary"):
        if aceito:
            st.session_state['termos_aceitos'] = True
            registrar_log_auditoria(st.session_state.get('usuario_id'), "ACEITE_TERMOS", "Usuário leu e aceitou os termos da LGPD.")
            st.rerun() 
        else:
            st.error("Você deve aceitar os termos de uso para acessar o sistema. Por favor, marque a caixa de seleção para prosseguir.")

def tela_home() -> None:
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
        st.write("Bem-vindo(a) à WikiSuporte, Uma plataforma de gestão e centralização de atendimentos de suporte, desenvolvida para analistas de suporte e gestores do suporte.")
        st.write("Utilize o menu lateral para navegar entre as diferentes seções do sistema, como a gestão de clientes, visualização de atendimentos e relatórios de desempenho.")
        st.info("💡 Dica: Em smartphones ou telas menores, toque no ícone > no canto superior esquerdo para abrir o menu.")
        
    with col2:
        st.success("🛡️ Perfil: **{perfil_usuario.title()}**")

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