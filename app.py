
#*** IMPORTAÇÕES ***#

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import streamlit as st
import random
import pandas as pd
import requests
import logging
import json
import tempfile 
import openmeteo_requests
import requests_cache
import numpy as np
from config import Config
from datetime import datetime, timedelta



from retry_requests import retry
from datetime import datetime, timedelta
from sqlalchemy import text
from typing import Tuple, Optional
from modules.database import get_connection
from dotenv import load_dotenv
from modules.auditoria import registrar_log_auditoria
from typing import Union
from typing import Optional, Dict, Union  
from modules.utils import inicializar_usuario, calcular_patente
from services.ui_realtime import (
    render_global_notifications_listener,
    show_gamification_upgrade_card,
)




#======================================================================================================================#

#*** Carrega variáveis de ambiente (DB_HOST, DB_NAME, DB_USER, DB_PASS) ***#
load_dotenv()

#======================================================================================================================#

# Configura o registro de logs: define destino (arquivo), modo de escrita (anexo) e formato da mensagem

pasta_logs = "logs"
if not os.path.exists(pasta_logs):
    os.makedirs(pasta_logs)
caminho_do_log = os.path.join(pasta_logs, "sistema.log")

logging.basicConfig(
    filename= caminho_do_log,
    filemode='a',               
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO          
)

logging.info("--- Aplicação iniciada e logs configurados  ---")

#======================================================================================================================#
# Tenta importar a função de auditoria (Ajuste o caminho se necessário)
try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    # Fallback caso o ficheiro não exista ainda
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass

# Configura a página: título, ícone, layout expandido e barra lateral recolhida por padrão
st.set_page_config(
    page_title="Wiki-Suporte", 
    page_icon="💡", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Inicializa variáveis de estado da sessão para controle de login e histórico de notificações
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
if 'notificacoes_lidas' not in st.session_state:
    st.session_state['notificacoes_lidas'] = []



# ==========================================
# 3. FUNÇÕES DE DADOS PARA A HOME (CACHED)
# ==========================================
@st.cache_data(ttl=300) 
def obter_alertas_usuario(usuario_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Busca alertas de plantão e validações pendentes para o usuário logado.
    Refatorado para utilizar context manager na conexão, garantindo estabilidade no Pandas.
    """
    if not usuario_id:
        return pd.DataFrame(), pd.DataFrame()

    engine = get_connection()
    try:
        # Uso do context manager para garantir que a conexão seja fechada corretamente
        with engine.connect() as conn:
            query_plantao = text("""
                SELECT data_hora_entrada, data_hora_saida 
                FROM plantoes_epsy 
                WHERE id_analista_epsy = :uid 
                AND data_hora_entrada::DATE = CURRENT_DATE
            """)
            df_plantao = pd.read_sql(query_plantao, conn, params={"uid": usuario_id})
            
            query_release = text("""
                SELECT r.versao_release AS versao, c.id_chamado AS nr_chamado
                FROM ciclos_homologacao ch
                JOIN releases r ON ch.id_release = r.id_release
                JOIN chamados c ON ch.id_chamado = c.id_chamado
                JOIN chamados_tecnuv ct ON ct.nr_chamado::text = c.id_chamado AND ct.id_analista_epsy = :uid
                WHERE ch.status_teste = 'Aguardando'
            """)
            df_release = pd.read_sql(query_release, conn, params={"uid": usuario_id})
            
            return df_plantao, df_release
            
    except Exception as e:
        logging.error(f"Erro ao buscar alertas no banco de dados para o usuário {usuario_id}: {e}")
        st.error(f"Erro ao buscar alertas no banco de dados. Contate o administrador.")
        return pd.DataFrame(), pd.DataFrame()

# @st.cache_data(ttl=300)
# def obter_kpis_home(usuario_id):
#     """Busca os dados de gamificação do analista."""
#     engine = get_connection()
#     kpis = {
#         "minhas_dicas": 0, "meu_xp": 0, "posicao_ranking": "-"
#     }
#     try:
#         with engine.connect() as conn:
#             query_dicas = text("SELECT COUNT(id) FROM base_conhecimento WHERE id_analista_autor = :uid AND status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE'")
#             kpis["minhas_dicas"] = conn.execute(query_dicas, {"uid": usuario_id}).scalar() or 0
#             kpis["meu_xp"] = kpis["minhas_dicas"] * 50
            
#             query_rank = text("""
#                 WITH Ranking AS (
#                     SELECT id_analista_autor, COUNT(id) as total,
#                            RANK() OVER(ORDER BY COUNT(id) DESC) as posicao
#                     FROM base_conhecimento WHERE status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE' GROUP BY id_analista_autor
#                 )
#                 SELECT posicao FROM Ranking WHERE id_analista_autor = :uid
#             """)
#             rank_result = conn.execute(query_rank, {"uid": usuario_id}).scalar()
#             if rank_result: kpis["posicao_ranking"] = f"{rank_result}º Lugar"
            
#     except Exception as e:
#         st.error(f"Erro ao carregar KPIs: {e}")
#     return kpis

#@st.cache_data(ttl=300)
def obter_kpis_home(usuario_id):
    engine = get_connection()
    kpis = {
        "minhas_dicas": 0, "meu_xp": 0, "posicao_ranking": "-",
        "impacto_visualizacoes": 0, "upvotes_recebidos": 0,
        "nivel_atual": "Iniciante 🌱", "progresso_nivel": 0.0,
        "missoes_ativas": []
    }
    try:
        with engine.connect() as conn:
            # 1. BUSCA DADOS DO USUÁRIO (Garante que o usuário sempre retorne algo)
            query_user = text("""
                SELECT 
                    COALESCE(xp_total, 0) as xp, 
                    COALESCE(medalha_atual, 'Iniciante 🌱') as medalha 
                FROM usuarios WHERE id = :uid
            """)
            res_user = conn.execute(query_user, {"uid": usuario_id}).fetchone()
            
            if res_user:
                kpis["meu_xp"] = res_user.xp
                kpis["nivel_atual"] = res_user.medalha
                # Calcula progresso (evita divisão por zero)
                kpis["progresso_nivel"] = float((res_user.xp % 1000) / 1000.0)

            # 2. BUSCA ESTATÍSTICAS DE POSTS (Separado para evitar erros de GROUP BY)
            query_stats = text("""
                SELECT 
                    COUNT(id) as total_posts,
                    COALESCE(SUM(qtd_upvotes), 0) as total_upvotes,
                    COALESCE(SUM(qtd_visualizacoes), 0) as total_views
                FROM base_conhecimento 
                WHERE id_analista_autor = :uid 
                  AND status = 'APROVADO' 
                  AND origem = 'CONHECIMENTO_SUPORTE'
            """)
            res_stats = conn.execute(query_stats, {"uid": usuario_id}).fetchone()
            
            if res_stats:
                kpis["minhas_dicas"] = res_stats.total_posts
                kpis["upvotes_recebidos"] = res_stats.total_upvotes
                kpis["impacto_visualizacoes"] = res_stats.total_views

            # 3. RANKING (Simplificado)
            query_rank = text("""
                SELECT posicao FROM (
                    SELECT id, RANK() OVER(ORDER BY xp_total DESC) as posicao
                    FROM usuarios WHERE ativo = true
                ) r WHERE id = :uid
            """)
            rank_val = conn.execute(query_rank, {"uid": usuario_id}).scalar()
            kpis["posicao_ranking"] = f"{rank_val}º Lugar" if rank_val else "N/A"

            # 4. MISSÕES (Engajamento)
            if kpis["upvotes_recebidos"] < 10:
                kpis["missoes_ativas"].append("⭐ **Missão:** Alcance 10 curtidas para subir de nível!")
            
            # Verifica voto nas últimas 24h
            voto_hoje = conn.execute(text("""
                SELECT EXISTS(
                    SELECT 1 FROM base_conhecimento_votos 
                    WHERE id_analista_votante = :uid AND data_voto >= now() - interval '24 hours'
                )
            """), {"uid": usuario_id}).scalar()
            
            if not voto_hoje:
                kpis["missoes_ativas"].append("🔍 **Missão:** Avalie a dica de um colega hoje!")

    except Exception as e:
        st.error(f"Erro Crítico nos KPIs: {e}")
    
    return kpis


# ==========================================
# 4. FUNÇÕES DE SEGURANÇA E LOGIN
# ==========================================
def verificar_login(username: str, senha_digitada: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """ Verifica as credenciais delegando a validação de hash da senha 100% para o PostgreSQL. """
    engine = get_connection()
    try:
        with engine.connect() as conn:
            # AJUSTE DE SEGURANÇA: Usando a função nativa crypt() do Postgres para comparar o hash.
            # O Python NUNCA sabe qual é a senha real ou o hash, ele apenas repassa o texto limpo para o banco julgar.
            query = text("""
                SELECT id, perfil 
                FROM usuarios 
                WHERE nome ILIKE :u 
                AND password_hash = crypt(:p, password_hash) 
                AND ativo = TRUE
            """)
           # Passamos 'u' para o nome e 'p' para a senha em texto puro
            resultado = conn.execute(query, {"u": username, "p": senha_digitada}).fetchone()
            
            if resultado:
                # Retorna ID e Perfil para a sessão do Streamlit
                return True, resultado[0], resultado[1]
                
    except Exception as e:
        st.error(f"WikiSuporte encontrou um erro durante a autenticação: {e}")
    
    return False, None, None


# --- 1. FUNÇÃO DE CONSUMO DE API (COM CACHE) ---
# O TTL=3600 significa que o sistema só vai na internet buscar o clima a cada 1 hora (3600 segundos).
# Nos outros acessos, ele pega da memória RAM do servidor, ficando instantâneo!
# --- 1. CONFIGURAÇÃO DO CLIENTE OPEN-METEO (GLOBAL) ---
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# --- MAPEAMENTO DOS CÓDIGOS DE CLIMA ---
CODIGOS_CLIMA = {
    0: {"texto": "Céu limpo", "icone": "☀️", "alerta": False},
    1: {"texto": "Principalmente limpo", "icone": "🌤️", "alerta": False},
    2: {"texto": "Parcialmente nublado", "icone": "⛅", "alerta": False},
    3: {"texto": "Nublado", "icone": "☁️", "alerta": False},
    45: {"texto": "Neblina", "icone": "🌫️", "alerta": False},
    48: {"texto": "Neblina com geada", "icone": "🌫️❄️", "alerta": False},
    51: {"texto": "Chuvisco leve", "icone": "🌦️", "alerta": False},
    53: {"texto": "Chuvisco moderado", "icone": "🌦️", "alerta": False},
    55: {"texto": "Chuvisco intenso", "icone": "🌧️", "alerta": True},
    61: {"texto": "Chuva leve", "icone": "🌧️", "alerta": False},
    63: {"texto": "Chuva moderada", "icone": "🌧️", "alerta": False},
    65: {"texto": "Chuva pesada", "icone": "🌧️", "alerta": True},
    71: {"texto": "Neve leve", "icone": "🌨️", "alerta": False},
    73: {"texto": "Neve moderada", "icone": "🌨️", "alerta": False},
    75: {"texto": "Neve pesada", "icone": "🌨️", "alerta": True},
    80: {"texto": "Pancadas de chuva leves", "icone": "🌦️", "alerta": False},
    81: {"texto": "Pancadas de chuva moderadas", "icone": "🌧️", "alerta": False},
    82: {"texto": "Pancadas de chuva violentas", "icone": "🌧️", "alerta": True},
    95: {"texto": "Tempestade", "icone": "⛈️", "alerta": True},
    96: {"texto": "Tempestade com granizo leve", "icone": "⛈️🌨️", "alerta": True},
    99: {"texto": "Tempestade com granizo pesado", "icone": "⛈️🌨️", "alerta": True},
}

# --- FUNÇÃO DE CONSUMO À API (COM CACHE DO STREAMLIT) ---
@st.cache_data(ttl=3600)   # <-- decorador agora aplicado corretamente
def obter_previsao_tempo(lat="-28.935", lon="-49.486"):
    """
    Obtém dados meteorológicos atuais da API Open-Meteo usando o cliente global.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "current": [
            "weather_code", "cloud_cover", "precipitation", "rain",
            "showers", "is_day", "apparent_temperature",
            "relative_humidity_2m", "temperature_2m", "wind_speed_10m",
            "wind_gusts_10m", "wind_direction_10m"
        ],
        "forecast_days": 1
    }

    try:
        responses = openmeteo.weather_api(url, params=params)
        response = responses[0]
        current = response.Current()

        # Extrai os valores na mesma ordem dos parâmetros
        current_weather_code = current.Variables(0).Value()
        current_cloud_cover = current.Variables(1).Value()
        current_precipitation = current.Variables(2).Value()
        current_rain = current.Variables(3).Value()
        current_showers = current.Variables(4).Value()
        current_is_day = current.Variables(5).Value()
        current_apparent_temperature = current.Variables(6).Value()
        current_relative_humidity_2m = current.Variables(7).Value()
        current_temperature_2m = current.Variables(8).Value()
        current_wind_speed_10m = current.Variables(9).Value()
        current_wind_gusts_10m = current.Variables(10).Value()
        current_wind_direction_10m = current.Variables(11).Value()

        info_condicao = CODIGOS_CLIMA.get(int(current_weather_code), {"texto": "Desconhecido", "icone": "❓", "alerta": False})

        alertas = [{"event": "Condição severa detectada", "description": info_condicao["texto"]}] if info_condicao["alerta"] else []

        return {
            "temperature": current_temperature_2m,
            "windspeed": current_wind_speed_10m,
            "condicao_texto": info_condicao["texto"],
            "icone_url": info_condicao["icone"],
            "alertas": alertas,
            # campos extras (opcionais)
            "weather_code": current_weather_code,
            "cloud_cover": current_cloud_cover,
            "precipitation": current_precipitation,
            "rain": current_rain,
            "showers": current_showers,
            "is_day": current_is_day,
            "apparent_temperature": current_apparent_temperature,
            "relative_humidity": current_relative_humidity_2m,
            "wind_gusts": current_wind_gusts_10m,
            "wind_direction": current_wind_direction_10m,
        }
    except Exception as e:
        st.error(f"Erro ao buscar dados do Open-Meteo: {e}")
        return None

# INTERFACE DO WIDGET PARA A HOME (adaptada com cache)
@st.cache_data(ttl=300)  # Cache de 5 minutos
def exibir_widget_clima():
    with st.container(border=True):
        st.subheader("Temperatura atual - Araranguá - SC")
        clima = obter_previsao_tempo()  # usa coordenadas padrão

        if clima:
            col1, col2 = st.columns(2)
            with col1:
                st.write(clima["icone_url"])  # Emoji; se usar URL, trocar por st.image
                st.metric(label="Temperatura", value=f"{clima['temperature']:.1f} °C")
            with col2:
                st.metric(label="Velocidade do Vento", value=f"{clima['windspeed']:.1f} km/h")
                st.write(f"Condição: {clima['condicao_texto']}")

            if clima["alertas"]:
                with st.expander("Alertas Meteorológicos", expanded=True):
                    for alerta in clima["alertas"]:
                        st.warning(f"{alerta['event']}: {alerta['description']}")
        else:
            st.warning("Não foi possível carregar os dados do clima no momento.")


def obter_saudacao() -> str:
    hora_atual = datetime.now().hour
    if 5 <= hora_atual < 12: return "Bom dia"
    elif 12 <= hora_atual < 18: return "Boa tarde"
    else: return "Boa noite"

# # ==========================================#
# # PROTEÇÃO CONTRA INATIVIDADE (TIMEOUT)
# # ==========================================#
# if st.session_state.get('autenticado'):   # <-- correção aqui
#     agora = datetime.now()
#     ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    
#     if agora - ultimo_acesso > timedelta(minutes=30):
#         st.session_state.clear() 
#         st.warning("⏱️ Sessão expirada por inatividade. Por favor, faça login novamente para continuar.")
#         st.stop()
#     else:
#         st.session_state['ultimo_acesso'] = agora

# ==========================================
# 6. TELAS (VIEWS) DO SISTEMA
# ==========================================
def tela_login() -> None:
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] {display: none;}
            [data-testid="stSidebar"] {display: none;}
            /* Força a centralização de textos dentro de elementos de alerta e captions */
            .stAlert p, .stCaption {
                text-align: center;
                display: block;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    col_vazia1, col_centro, col_vazia2 = st.columns([1, 1.5, 1])

    with col_centro:
        c_img1, c_img2, c_img3 = st.columns([1, 2, 1])
        with c_img2:
            try: st.image("mascote/psy_no_dashbsoard.png", width='stretch')
            except: pass
            
        st.markdown("<h2 style='text-align: center;'>WikiSuporte</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>Plataforma de Suporte Técnico</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown("<h4 style='text-align: center;'>🔐 Login </h4>", unsafe_allow_html=True)
            
            with st.form("form_login"):
                usuario = st.text_input("👤 Usuário", placeholder="Insira o seu nome de usuário")
                senha = st.text_input("🔑 Senha", type="password", placeholder="••••••••")
                st.markdown("<br>", unsafe_allow_html=True)
                btn_login = st.form_submit_button("Entrar", type="primary", use_container_width='stretch')
                
            if btn_login:
                if usuario and senha:
                    sucesso, user_id, user_perfil = verificar_login(usuario, senha)
                    if sucesso:
                        st.session_state['autenticado'] = True
                        st.session_state['usuario_id'] = user_id
                        st.session_state['usuario_nome'] = usuario
                        st.session_state['perfil'] = user_perfil 
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
                    "Aquele que quer ser o maior entre vós, seja o que serve. Jesus",
                    "A imaginação é mais importante que o conhecimento. Albert Einstein",
                    "Seja a mudança que você deseja ver no mundo. Mahatma Gandhi",
                    "Paciência é um elemento fundamental do sucesso. Bill Gates",
                    "A persistência é o caminho do êxito. Charles Chaplin",
                    "Saber que não sabemos nada é o começo da sabedoria. Sócrates",
                    "O que importa não é o que acontece com você, mas como você reage. Epicteto",
                    "Comece onde você está, use o que você tem, faça o que você pode. Arthur Ashe",
                    "O homem é o que ele pensa o dia todo. Ralph Waldo Emerson",
                    "Não espere por circunstâncias ideais, elas nunca chegam. Napoleon Hill",
                    "A alegria de fazer o bem é a única felicidade verdadeira. Leon Tolstói",
                    "Quanto maior a dificuldade, maior a glória em superá-la. Epicuro",
                    "Se você não pode fazer grandes coisas, faça pequenas coisas de forma grandiosa. Napoleon Hill",
                    "A simplicidade é o último grau da sofisticação. Leonardo da Vinci",
                    "Onde há amor pela humanidade, há amor pela arte de curar. Hipócrates",
                    "Viver é a coisa mais rara do mundo. A maioria das pessoas apenas existe. Oscar Wilde",
                    "A vida é 10% o que acontece comigo e 90% como eu reajo a isso. Charles Swindoll",
                    "Sempre parece impossível até que seja feito. Nelson Mandela",
                    "A única coisa que se coloca entre você e seu objetivo é a história que você conta a si mesmo. Jordan Belfort",
                    "Procure ser um homem de valor, em vez de ser um homem de sucesso. Albert Einstein",
                    "Nós somos o que fazemos repetidamente. Excelência, então, não é um ato, mas um hábito. Will Durant",
                    "O melhor modo de prever o futuro é criá-lo. Alan Kay",
                    "Nossa maior fraqueza está em desistir. Thomas Edison",
                    "Para ganhar conhecimento, adicione coisas todos os dias. Para ganhar sabedoria, elimine coisas todos os dias. Lao Tzu",
                    "Qualidade significa fazer certo quando ninguém está olhando. Henry Ford",
                    "Um cliente satisfeito é a melhor estratégia de negócios de todas. Michael LeBoeuf",
                    "A maior descoberta da minha geração é que um ser humano pode alterar sua vida ao alterar suas atitudes. William James",
                    "Se você quer ir rápido, vá sozinho. Se você quer ir longe, vá acompanhado. Provérbio Africano",
                    "A tecnologia é apenas uma ferramenta. O professor é o mais importante. Bill Gates",
                    
                ]

        with col_centro:
                # ... (seu formulário de login)
                st.markdown("<br>", unsafe_allow_html=True)
                
                # Frase centralizada
                st.success(f"💡 **Pensamento do dia:**\n\n_{random.choice(frases)}_")
                
                # Rodapé centralizado com HTML
                st.markdown("<p style='text-align: center; color: gray; font-size: 0.8rem;'>© 2026 WikiSuporte — Desenvolvido por Rafael D. Nascimento.</p>", unsafe_allow_html=True)


def tela_home() -> None:
    """Nova Home principal que consolida a antiga Page 0 no App.py"""
    render_global_notifications_listener()
    nome_usuario = str(st.session_state.get('usuario_nome', '')).capitalize()
    perfil_usuario = str(st.session_state.get('perfil', 'analista')).lower()
    usuario_id = st.session_state.get('usuario_id', 0)
    
    # --- PREPARAÇÃO DA DATA E DIA DA SEMANA ---
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    hoje = datetime.now()
    dia_semana_str = dias_semana[hoje.weekday()]
    data_atual = f"{dia_semana_str}, {hoje.strftime('%d/%m/%Y')}"
    
    # --- CONSTRUÇÃO DA BARRA LATERAL (PÓS-LOGIN) ---
    st.sidebar.markdown(f"## 👤 {nome_usuario}")
    st.sidebar.markdown(f"### {obter_saudacao()}!")
    st.sidebar.caption(f"🛡️ Perfil: **{perfil_usuario.title()}**")
    st.sidebar.divider()
    # --- Onboarding / Ajuda rápida (nativo Streamlit) ---
    st.sidebar.markdown("### 💡 Ajuda rápida")
    st.sidebar.info(
        "**Bem-vindo ao WikiSuporte.** Use o **menu no topo** para abrir cada área "
        "(Dashboards, Importação, Releases, etc.). Esta barra mostra quem está logado e atalhos."
    )
    with st.sidebar.expander("🤔 Mini-FAQ"):
        st.markdown(
            """
**Onde começo?**  
Home → confira alertas. Depois abra **Importação** se for subir relatórios, ou os **Dashboards** para análise.

**Como sair?**  
Use o botão **Sair** abaixo (encerra a sessão neste navegador).

**Não vejo uma página**  
Algumas telas são só para **coordenação** ou **desenvolvimento** — peça acesso ao gestor.

**Documentação completa**  
Na pasta do projeto: `MANUAL_USUARIO.md` (uso), `DOC_TECNICA.md` (TI).
            """
        )
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sair do Sistema", use_container_width='stretch'):
        registrar_log_auditoria(usuario_id, "LOGOUT", "Usuário saiu do sistema.")
        st.session_state.clear()
        st.rerun()

# --- AJUSTE VISUAL PROFISSIONAL ---
    # Mata o espaço em branco inútil do topo do Streamlit
    st.markdown("<style>.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }</style>", unsafe_allow_html=True)

    # --- LOGO DA EPSY SISTEMAS ---
    # As colunas [3, 1, 3] centralizam a logo e deixam ela com um tamanho elegante
    _, col_logo, _ = st.columns([3, 1, 3])
    with col_logo:
        st.image("assets/imgepsy.png", use_container_width='stretch')

    st.divider() # Linha para separar a logo do seu painel

    # SAUDAÇÃO E CLIMA USANDO COMPONENTES NATIVOS
    col_texto, col_clima = st.columns([2.5, 1])

    with col_texto:
        # Determina o ícone da saudação baseado no período do dia
        saudacao = obter_saudacao()
        if "Boa noite" in saudacao:
            icone_saudacao = "🌕 💻"
        elif "Boa tarde" in saudacao:
            icone_saudacao = "🌤️ 💻"
        else:
            icone_saudacao = "☀️ 💻"
        
# Cabeçalho com saudação personalizada
        st.header(f"{saudacao}, {nome_usuario}! {icone_saudacao}", anchor=False)
        
        # Descrição do painel
        st.markdown(
            "Este é o seu painel de controle central do **WikiSuporte**. "
            "Acompanhe os seus indicadores e os alertas do dia."
        )
        with st.expander("🤔 Como usar esta página?"):
            st.markdown(
                "**Alertas** incluem plantão, validações de release e avisos de **pendente representante** (release + cobrança 7 em 7 dias). "
                "**Clima** é informativo. Use o **menu superior** para ir a Importação, Dashboards ou Releases. "
                "Dúvidas: veja **Ajuda rápida** na barra lateral."
            )
        # --- AJUSTE CIRÚRGICO: CÁLCULO REAL DE ALERTAS ---
        # 1. Desempacotamos a tupla nos dois DataFrames correspondentes
        df_plantao, df_correcoes = obter_alertas_usuario(usuario_id)
        
        # 2. Contamos quantas linhas (registros reais) existem em cada um
        total_alertas_reais = len(df_plantao) + len(df_correcoes)
        
        # Exibição da data e dos alertas (se houver) em uma linha horizontal
        if total_alertas_reais > 0:
            st.write(f"📅 {data_atual}   |   ⚡ **{total_alertas_reais}** alerta(s) no sistema")
        else:
            st.write(f"📅 {data_atual}")
       
        st.write("")

    with col_clima:
        obter_previsao_tempo()
        exibir_widget_clima()
    
    st.divider()

    # 1. Primeiro recuperamos o ID e os dados (KPIs)
    usuario_id = st.session_state.get('usuario_id') 

    if usuario_id:
        # BUSCA DOS DADOS (Aqui a variável kpis ganha vida)
        kpis = obter_kpis_home(usuario_id)
        medalha_atual = str(kpis.get("nivel_atual", "Iniciante 🌱"))
        medalha_antiga = str(st.session_state.get("ws_last_medalha", medalha_atual))
        if medalha_antiga != medalha_atual:
            show_gamification_upgrade_card(
                "Subida de nível!",
                f"Parabéns! Você alcançou: <b>{medalha_atual}</b>",
            )
        st.session_state["ws_last_medalha"] = medalha_atual
        df_plantao, df_correcoes = obter_alertas_usuario(usuario_id)

        # 2. RENDERIZAÇÃO DOS TROFÉUS (Logo após o divisor, antes das notificações)
        if kpis:
            renderizar_dashboard_conquistas(kpis)
        else:
            st.warning("Não foi possível carregar seus indicadores de desempenho.")
        
        st.divider() # Divisor entre o Ranking e as Notificações

        # 1. Padronização dos Alertas em uma Lista de Dicionários
        notificacoes_atuais = []

        try:
            from services.notificacoes_representante import rodar_sincronizacao_completa, listar_notificacoes_usuario

            rodar_sincronizacao_completa()
            for n in listar_notificacoes_usuario(usuario_id, apenas_nao_lidas=True):
                notificacoes_atuais.append(
                    {
                        "id": f"db_notif_{n['id']}",
                        "db_id": n["id"],
                        "icone": "📌",
                        "titulo": n["titulo"],
                        "detalhe": n["mensagem"]
                        + (f"\n\n_Chamado {n['nr_chamado']}_ — {n['tipo']}" if n.get("nr_chamado") else ""),
                    }
                )
        except Exception:
            pass

        if not df_plantao.empty:
            entrada_raw = df_plantao.iloc[0]['data_hora_entrada']
            saida_raw = df_plantao.iloc[0]['data_hora_saida']
            entrada = entrada_raw.strftime('%H:%M') if isinstance(entrada_raw, datetime) else str(entrada_raw)[:5]
            saida = saida_raw.strftime('%H:%M') if isinstance(saida_raw, datetime) else str(saida_raw)[:5]
            
            notificacoes_atuais.append({
                'id': f"plantao_{datetime.now().strftime('%Y%m%d')}",
                'icone': '🚨',
                'titulo': 'Alerta de Escala: Plantão Hoje',
                'detalhe': f"Você está de plantão hoje, das {entrada} às {saida}. Mantenha-se atento e saia no Horário."
            })

        if not df_correcoes.empty:
            for _, row in df_correcoes.iterrows():
                notificacoes_atuais.append({
                    'id': f"chamado_{row['nr_chamado']}",
                    'icone': '⚠️',
                    'titulo': f"Validação Pendente: Chamado {row['nr_chamado']}",
                    'detalhe': f"A release {row['versao']} requer a sua validação para o chamado {row['nr_chamado']}. Por favor, realize a conferência técnica."
                })

        # 2. Separação Lógica (Lidas vs Não Lidas)
        nao_lidas = [n for n in notificacoes_atuais if n['id'] not in st.session_state['notificacoes_lidas']]
        lidas = [n for n in notificacoes_atuais if n['id'] in st.session_state['notificacoes_lidas']]

        # 3. Renderização da Interface
        st.subheader(f"🔔 Central de Notificações ({len(nao_lidas)})", anchor=False)
        
        if notificacoes_atuais:
            aba_pendentes, aba_historico = st.tabs(["Pendentes", "Histórico (Lidas)"])
            
            with aba_pendentes:
                if nao_lidas:
                    for notif in nao_lidas:
                        with st.expander(f"{notif['icone']} {notif['titulo']}", expanded=False):
                            st.write(notif['detalhe'])
                            # Botão para mover para o histórico
                            if st.button("Marcar como lida", key=f"btn_read_{notif['id']}"):
                                st.session_state['notificacoes_lidas'].append(notif['id'])
                                if notif.get("db_id"):
                                    try:
                                        from services.notificacoes_representante import marcar_lida
                                        marcar_lida(int(notif["db_id"]), usuario_id)
                                    except Exception:
                                        pass
                                st.rerun() # Atualiza a tela imediatamente
                else:
                    st.info("✅ Tudo limpo! Você não possui notificações pendentes no momento.")
                    
            with aba_historico:
                if lidas:
                    for notif in lidas:
                        with st.expander(f"✅ (Lida) {notif['titulo']}", expanded=False):
                            st.write(notif['detalhe'])
                            # Permite ao usuário voltar a notificação para a tela principal
                            if st.button("Restaurar notificação", key=f"btn_restore_{notif['id']}"):
                                st.session_state['notificacoes_lidas'].remove(notif['id'])
                                st.rerun()
                else:
                    st.caption("Nenhuma notificação foi lida nesta sessão.")
        else:
            st.info("Você não possui alertas no momento.")
    else:
        st.error("Erro de contexto: Sessão inválida. Por favor, faça login novamente.", icon="🛑")

#===============================================================================================================================================================#
def renderizar_dashboard_conquistas(kpis):
    # 1. CABEÇALHO DE NÍVEL E PROGRESSO (UX Gamificada)
    with st.container(border=True):
        col_rank_icon, col_progress = st.columns([1, 4])
        with col_rank_icon:
            # Mostra o ícone grande do nível atual
            st.markdown(f"<h1 style='text-align: center; margin:0;'>{kpis['nivel_atual'].split()[-1]}</h1>", unsafe_allow_html=True)
        with col_progress:
            st.markdown(f"**Nível Atual:** {kpis['nivel_atual']}")
            st.progress(kpis['progresso_nivel'])
            proximo_xp = 1000 - (kpis['meu_xp'] % 1000)
            st.caption(f"✨ Faltam **{proximo_xp} XP** para o próximo nível")

    st.write("") # Espaçamento

    # 2. GRID DE KPIs PRINCIPAIS (3 Colunas)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        with st.container(border=True):
            st.metric(
                label="⭐ XP Acumulado", 
                value=f"{kpis['meu_xp']} XP", 
                delta="Pontos Totais"
            )
            st.caption("Baseado em Posts + Upvotes")

    with col2:
        with st.container(border=True):
            # Mostra a posição com o troféu se for Top 3
            pos = kpis['posicao_ranking']
            label_rank = "🏆 Posição no Ranking" if "1º" in pos or "2º" in pos or "3º" in pos else "🏅 Posição na Equipe"
            st.metric(label=label_rank, value=pos)
            st.caption("Ranking de Qualidade")

    with col3:
        with st.container(border=True):
            # Impacto Real: Soma de Views + Upvotes
            impacto_total = kpis['impacto_visualizacoes'] + (kpis['upvotes_recebidos'] * 5)
            st.metric(label="🚀 Impacto Total", value=impacto_total)
            st.caption(f"👀 {kpis['impacto_visualizacoes']} views | 👍 {kpis['upvotes_recebidos']} úteis")

    st.write("") # Espaçamento

    # 3. SEÇÃO DE ENGAJAMENTO (Missões e Próximos Passos)
    if kpis['missoes_ativas']:
        with st.expander("🎯 **Missões e Desafios da Semana**", expanded=True):
            for missao in kpis['missoes_ativas']:
                st.markdown(f"{missao}")
            st.caption("Complete missões para ganhar bônus de XP e medalhas exclusivas.")

    st.divider()

    # 4. MINI-RESUMO DE CONTRIBUIÇÕES (Opcional)
    st.subheader("📚 Minhas Estatísticas", anchor=False)
    c1, c2, c3 = st.columns(3)
    c1.write(f"📂 **Posts Aprovados:** {kpis['minhas_dicas']}")
    c2.write(f"👍 **Votos Recebidos:** {kpis['upvotes_recebidos']}")
    c3.write(f"📅 **Última Atividade:** Hoje") # Você pode puxar isso do banco depois


    # # --- OS MEUS INDICADORES Contribuições ---
    # st.subheader("🏆 Meu Desempenho", anchor=False)
    # col_xp, col_dicas, col_rank = st.columns(3)

    # with col_xp:
    #     with st.container(border=True):
    #         st.metric(label="⚡ Meu XP Total", value=f"{kpis.get('meu_xp', 0)} XP", delta="Baseado em aprovações")
    # with col_dicas:
    #     with st.container(border=True):
    #         st.metric(label="📚 Contribuições Oficiais", value=kpis.get('minhas_dicas', 0), delta="Dicas ativas", delta_color="normal")
    # with col_rank:
    #     with st.container(border=True):
    #         st.metric(label="🏅 Posição na Equipe", value=kpis.get('posicao_ranking', 'N/A'), delta="Leaderboard")

    # st.divider()
# ==========================================
# 7. CONTROLADOR DE FLUXO PRINCIPAL
# ==========================================
if not st.session_state['autenticado']:
    tela_login()
else:
    render_global_notifications_listener()
    tela_home()