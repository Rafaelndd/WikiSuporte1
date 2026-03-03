import streamlit as st
import bcrypt
import random
import pandas as pd
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
st.set_page_config(page_title="WikiSuporte </>", page_icon="💡", layout="wide")

# ==========================================
# 2. INICIALIZAÇÃO DE SESSÃO
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'termos_aceitos' not in st.session_state:
    st.session_state['termos_aceitos'] = False

# ==========================================
# 3. FUNÇÕES DE DADOS PARA A HOME (CACHED)
# ==========================================
@st.cache_data(ttl=300) 
def obter_alertas_usuario(usuario_id):
    engine = get_connection()
    try:
        query_plantao = text("SELECT data_hora_entrada, data_hora_saida FROM plantoes_epsy WHERE id_analista_epsy = :uid AND data_hora_entrada::DATE = CURRENT_DATE")
        df_plantao = pd.read_sql(query_plantao, engine, params={"uid": usuario_id})
        
        # Ajustado para usar id_analista_epsy conforme nosso mapa oficial para evitar quebras
        query_release = text("""
            SELECT r.versao, c.nr_chamado 
            FROM release_chamados_correcao rc
            JOIN releases_tecnuv r ON rc.id_release = r.id_release
            JOIN chamados_tecnuv c ON rc.nr_chamado = c.nr_chamado
            WHERE c.id_analista_epsy = :uid AND rc.validado_epsy = FALSE
        """)
        df_release = pd.read_sql(query_release, engine, params={"uid": usuario_id})
        
        return df_plantao, df_release
    except Exception as e:
        st.error(f"Erro ao buscar alertas no banco de dados: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=300)
def obter_kpis_home(usuario_id):
    """Busca os dados de gamificação do analista."""
    engine = get_connection()
    kpis = {
        "minhas_dicas": 0, "meu_xp": 0, "posicao_ranking": "-"
    }
    try:
        with engine.connect() as conn:
            query_dicas = text("SELECT COUNT(id) FROM base_conhecimento WHERE id_analista_autor = :uid AND status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE'")
            kpis["minhas_dicas"] = conn.execute(query_dicas, {"uid": usuario_id}).scalar() or 0
            kpis["meu_xp"] = kpis["minhas_dicas"] * 50
            
            query_rank = text("""
                WITH Ranking AS (
                    SELECT id_analista_autor, COUNT(id) as total,
                           RANK() OVER(ORDER BY COUNT(id) DESC) as posicao
                    FROM base_conhecimento WHERE status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE' GROUP BY id_analista_autor
                )
                SELECT posicao FROM Ranking WHERE id_analista_autor = :uid
            """)
            rank_result = conn.execute(query_rank, {"uid": usuario_id}).scalar()
            if rank_result: kpis["posicao_ranking"] = f"{rank_result}º Lugar"
            
    except Exception as e:
        st.error(f"Erro ao carregar KPIs: {e}")
    return kpis

# ==========================================
# 4. FUNÇÕES DE SEGURANÇA
# ==========================================
def verificar_login(username: str, senha_digitada: str) -> Tuple[bool, Optional[int], Optional[str]]:
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT id, password_hash, perfil FROM usuarios WHERE nome ILIKE :u AND ativo = TRUE")
            resultado = conn.execute(query, {"u": username}).fetchone()
            
            if resultado:
                usuario_id = resultado[0]
                senha_hash_banco = resultado[1]
                perfil = resultado[2]
                
                if isinstance(senha_hash_banco, str):
                    senha_hash_banco = senha_hash_banco.encode('utf-8')
                    
                if bcrypt.checkpw(senha_digitada.encode('utf-8'), senha_hash_banco):
                    return True, usuario_id, perfil
    except Exception as e:
        st.error(f"WikiSuporte encontrou um erro durante a autenticação: {e}")
    
    return False, None, None

def verificar_aceite_termos(usuario_id: int) -> bool:
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM logs_auditoria_sistema WHERE usuario_id = :u AND acao = 'ACEITE_TERMOS' LIMIT 1")
            resultado = conn.execute(query, {"u": usuario_id}).fetchone()
            return bool(resultado)
    except Exception:
        return False

def obter_saudacao() -> str:
    hora_atual = datetime.now().hour
    if 5 <= hora_atual < 12: return "Bom dia"
    elif 12 <= hora_atual < 18: return "Boa tarde"
    else: return "Boa noite"

# ==========================================
# 5. PROTEÇÃO CONTRA INATIVIDADE (TIMEOUT)
# ==========================================
if st.session_state['autenticado']:
    agora = datetime.now()
    ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    
    if agora - ultimo_acesso > timedelta(minutes=50):
        st.session_state.clear() 
        st.warning("⏱️ Sessão expirada por inatividade. Por favor, faça login novamente para continuar.")
        st.stop()
    else:
        st.session_state['ultimo_acesso'] = agora

# ==========================================
# 6. TELAS (VIEWS) DO SISTEMA
# ==========================================
def tela_login() -> None:
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 1.5, 1])

    with col_centro:
        c_img1, c_img2, c_img3 = st.columns([1, 2, 1])
        with c_img2:
            try: st.image("mascote/psy_no_dashbsoard.png", use_container_width=True)
            except: pass
            
        st.markdown("<h2 style='text-align: center;'>WikiSuporte</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Plataforma de Suporte Técnico</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

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
    """Nova Home principal que consolida a antiga Page 0 no App.py"""
    nome_usuario = str(st.session_state.get('usuario_nome', '')).capitalize()
    perfil_usuario = str(st.session_state.get('perfil', 'analista')).lower()
    usuario_id = st.session_state.get('usuario_id', 0)
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

    # --- CORPO DA PÁGINA (HOME) ---
    st.markdown(f"<h1>{obter_saudacao()}, {nome_usuario}! 👋</h1>", unsafe_allow_html=True)
    st.markdown("Este é o seu painel de controle central do **WikiSuporte**. Acompanhe os seus indicadores e os alertas do dia.")
    st.caption(f"📅 Hoje é **{data_atual}** | 🏢 Ambiente Seguro WikiSuporte")
    st.divider()

    # --- SISTEMA DE ALERTAS INTELIGENTES ---
    df_plantao, df_correcoes = obter_alertas_usuario(usuario_id)
    kpis = obter_kpis_home(usuario_id)

    if not df_plantao.empty or not df_correcoes.empty:
        with st.container(border=True):
            if not df_plantao.empty:
                entrada = df_plantao.iloc[0]['data_hora_entrada'].strftime('%H:%M') if isinstance(df_plantao.iloc[0]['data_hora_entrada'], datetime) else str(df_plantao.iloc[0]['data_hora_entrada'])[:5]
                saida = df_plantao.iloc[0]['data_hora_saida'].strftime('%H:%M') if isinstance(df_plantao.iloc[0]['data_hora_saida'], datetime) else str(df_plantao.iloc[0]['data_hora_saida'])[:5]
                st.error(f"🚨 **ALERTA DE ESCALA:** Você está no plantão de hoje! (Horário: {entrada} às {saida})")

            if not df_correcoes.empty:
                chamados_str = ", ".join([str(n) for n in df_correcoes['nr_chamado'].tolist()])
                st.warning(f"⚠️ **AÇÃO REQUERIDA:** Você possui validações pendentes de release nos chamados: **{chamados_str}**.")

    # --- OS MEUS INDICADORES (GAMIFICAÇÃO) ---
    st.markdown("### 🏆 Meu Desempenho")
    col_xp, col_dicas, col_rank = st.columns(3)

    with col_xp:
        with st.container(border=True):
            st.metric(label="⚡ Meu XP Total", value=f"{kpis['meu_xp']} XP", delta="Baseado em aprovações")
    with col_dicas:
        with st.container(border=True):
            st.metric(label="📚 Contribuições Oficiais", value=kpis['minhas_dicas'], delta="Dicas ativas", delta_color="normal")
    with col_rank:
        with st.container(border=True):
            st.metric(label="🏅 Posição na Equipe", value=kpis['posicao_ranking'], delta="Leaderboard")

    st.divider()

    # --- MENSAGEM DO SISTEMA ---
    st.info("💡 **Recado do PSY:** A sua participação faz toda a diferença para manter o WikiSuporte sempre atualizado. Navegue pelo menu lateral, pesquise na Central de Conhecimento e, se encontrar uma solução nova no seu dia a dia, não a guarde só para si. Clique em 'Contribuir' e partilhe com a equipa!")

# ==========================================
# 7. CONTROLADOR DE FLUXO PRINCIPAL
# ==========================================
if not st.session_state['autenticado']:
    tela_login()
elif not st.session_state['termos_aceitos']:
    tela_termos_uso()
else:
    tela_home()