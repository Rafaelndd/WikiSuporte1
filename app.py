
#*** IMPORTAÇÕES ***#

import sys
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_BASE_DIR)

from pathlib import Path

from dotenv import load_dotenv

# Antes de importar `modules.database` (que monta o engine com DB_*).
load_dotenv(Path(_BASE_DIR) / ".env")
load_dotenv()

import random
import streamlit as st
import pandas as pd
import requests
import logging
import json
import base64
import tempfile 
import openmeteo_requests
import requests_cache
import numpy as np
import streamlit.components.v1 as components

from datetime import datetime, timedelta
from datetime import datetime
from retry_requests import retry
from datetime import datetime, timedelta
from sqlalchemy import text
from typing import Tuple, Optional
from modules.database import get_connection
from modules.auditoria import registrar_log_auditoria
from typing import Union
from typing import Optional, Dict, Union  
from modules.utils import inicializar_usuario, calcular_patente
from services.ui_realtime import (
    render_global_notifications_listener,
    show_gamification_upgrade_card,
)
from services.wiki_authenticator import (
    ensure_stauth_cookie_restored,
    get_wiki_authenticator,
    load_credentials_for_stauth,
    sync_wiki_session_from_stauth,
    wiki_force_logout,
)
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.release_notes_banner import render_home_release_nudge

#======================================================================================================================#
# Variáveis de ambiente: carregadas no topo (antes de database / wiki_authenticator).
#======================================================================================================================#
import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
pasta_logs = os.path.join(BASE_DIR, "logs")
# Garante que a pasta de logs existe
pasta_logs = "logs"
os.makedirs(pasta_logs, exist_ok=True)

# Define caminho do arquivo
caminho_do_log = os.path.join(pasta_logs, "sistema.log")

# Configura logging
logging.basicConfig(
    filename=caminho_do_log,
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True   # importante para Streamlit
)

logging.info("--- Aplicação iniciada e logs configurados ---")

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

# Restaura login via cookie do streamlit-authenticator (F5 / nova aba)
if not st.session_state.get("autenticado"):
    ensure_stauth_cookie_restored()

# Alinha sessão Wiki com stauth (evita um frame da tela de login após credenciais válidas)
if st.session_state.get("authentication_status") and not st.session_state.get("autenticado"):
    sync_wiki_session_from_stauth()

# Oculta sidebar e menus (pages) na tela de login — aplicado cedo para evitar piscar
if not st.session_state['autenticado']:
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] { display: none !important; }
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarNav"], [data-testid="stSidebarNavItems"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. FUNÇÕES DE DADOS PARA A HOME (CACHED)
# ==========================================
@st.cache_data(ttl=600, show_spinner=False) 
def obter_alertas_usuario(usuario_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Busca alertas de plantão e validações pendentes para o usuário logado.
    Totalmente otimizado com Connection Pooling e Cache Seguro (sem UI).
    """
    if not usuario_id:
        return pd.DataFrame(), pd.DataFrame()

    engine = get_connection()
    try:
        # Context manager: Garante que a conexão volta para o Pool imediatamente após o uso
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
        # Grava o erro silenciosamente nos logs do servidor para o Dev ver, 
        # mas NÃO desenha nada na tela do usuário aqui dentro do cache!
        logging.error(f"Erro ao buscar alertas no BD para o usuário {usuario_id}: {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300)
def obter_kpis_home(usuario_id):
    engine = get_connection()
    kpis = {
        "minhas_dicas": 0,
        "meu_xp": 0,
        "posicao_ranking": "-",
        "impacto_visualizacoes": 0,
        "upvotes_recebidos": 0,
        "nivel_atual": "Iniciante 🌱",
        "progresso_nivel": 0.0,
        "missoes_ativas": [],
        "caminho_foto_perfil": None,
        "em_pausa": False,
        "dias_sem_contribuir": 0,
        "penalidade_sofrida_semana": 0,
        "bonus_recebido_semana": False,
    }
    try:
        with engine.connect() as conn:
            # 1. BUSCA DADOS DO USUÁRIO (Garante que o usuário sempre retorne algo)
            query_user = text("""
                SELECT
                    COALESCE(xp_total, 0) AS xp,
                    COALESCE(medalha_atual, 'Iniciante 🌱') AS medalha,
                    NULLIF(TRIM(COALESCE(caminho_foto_perfil, '')), '') AS caminho_foto,
                    COALESCE(em_ferias, FALSE) AS em_ferias,
                    COALESCE(em_atendimento_externo, FALSE) AS em_atendimento_externo
                FROM usuarios
                WHERE id = :uid
            """)
            res_user = conn.execute(query_user, {"uid": usuario_id}).fetchone()

            if res_user:
                row_u = res_user._mapping
                kpis["meu_xp"] = int(row_u["xp"])
                kpis["nivel_atual"] = str(row_u["medalha"])
                kpis["progresso_nivel"] = float((row_u["xp"] % 1000) / 1000.0)
                kpis["caminho_foto_perfil"] = row_u.get("caminho_foto") or None
                kpis["em_pausa"] = bool(
                    row_u.get("em_ferias") or row_u.get("em_atendimento_externo")
                )

            # 1b. Dias desde última contribuição APROVADA (data_avaliacao, UTC)
            try:
                q_dias = text("""
                    SELECT CASE
                        WHEN MAX(data_avaliacao) IS NULL THEN 999
                        ELSE (
                            DATE(timezone('UTC', CURRENT_TIMESTAMP))
                            - DATE(timezone('UTC', MAX(data_avaliacao)))
                        )::integer
                    END
                    FROM base_conhecimento
                    WHERE id_analista_autor = :uid
                      AND status = 'APROVADO'
                      AND origem = 'CONHECIMENTO_SUPORTE'
                      AND data_avaliacao IS NOT NULL
                """)
                dval = conn.execute(q_dias, {"uid": usuario_id}).scalar()
                kpis["dias_sem_contribuir"] = int(dval) if dval is not None else 999
            except Exception as ex_dias:
                logging.warning(
                    "KPI dias_sem_contribuir indisponível (migração/coluna?): %s", ex_dias
                )
                kpis["dias_sem_contribuir"] = 0

            # 1c. Penalidades e bônus na semana ISO (UTC) — user_xp_events
            try:
                q_pen = text("""
                    SELECT COALESCE(SUM(pontos), 0) AS total_neg
                    FROM user_xp_events
                    WHERE usuario_id = :uid
                      AND pontos < 0
                      AND to_char(timezone('UTC', criado_em), 'IYYY-IW')
                          = to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY-IW')
                """)
                pval = conn.execute(q_pen, {"uid": usuario_id}).scalar()
                kpis["penalidade_sofrida_semana"] = int(pval or 0)
            except Exception as ex_pen:
                logging.warning(
                    "KPI penalidade_sofrida_semana indisponível (tabela user_xp_events?): %s",
                    ex_pen,
                )
                kpis["penalidade_sofrida_semana"] = 0

            try:
                q_bon = text("""
                    SELECT EXISTS(
                        SELECT 1
                        FROM user_xp_events
                        WHERE usuario_id = :uid
                          AND tipo_evento = 'BONUS_SEMANAL'
                          AND to_char(timezone('UTC', criado_em), 'IYYY-IW')
                              = to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY-IW')
                    )
                """)
                kpis["bonus_recebido_semana"] = bool(
                    conn.execute(q_bon, {"uid": usuario_id}).scalar()
                )
            except Exception as ex_bon:
                logging.warning(
                    "KPI bonus_recebido_semana indisponível (tabela user_xp_events?): %s",
                    ex_bon,
                )
                kpis["bonus_recebido_semana"] = False

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
        logging.exception("Erro crítico em obter_kpis_home para usuario_id=%s: %s", usuario_id, e)

    return kpis


def _html_avatar_perfil_circular(caminho: str | None, tamanho_px: int = 76) -> str:
    """Retorna <img> em data-URI para uso em st.markdown, ou string vazia."""
    if not caminho:
        return ""
    p = Path(caminho)
    if not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
    except OSError:
        return ""
    b64 = base64.b64encode(raw).decode("ascii")
    ext = p.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")
    return (
        f'<img src="data:{mime};base64,{b64}" alt="Foto de perfil" '
        f'style="width:{tamanho_px}px;height:{tamanho_px}px;border-radius:50%;'
        f'object-fit:cover;border:3px solid #1e5fbf;display:block;margin:0 auto;" />'
    )



def obter_saudacao() -> str:
    hora_atual = datetime.now().hour
    if 5 <= hora_atual < 12: return "Bom dia"
    elif 12 <= hora_atual < 18: return "Boa tarde"
    else: return "Boa noite"

# ==========================================#
# PROTEÇÃO CONTRA INATIVIDADE (TIMEOUT)
# ==========================================#
if st.session_state.get('autenticado'):   # <-- correção aqui
    agora = datetime.now()
    ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    
    if agora - ultimo_acesso > timedelta(minutes=50):
        wiki_force_logout()
        st.session_state.clear()
        st.warning("⏱️ Sessão expirada por inatividade (50 min). Por favor, faça login novamente para continuar.")
        st.stop()
    else:
        st.session_state['ultimo_acesso'] = agora

# ==========================================
# 6. TELA DE LOGIN E HOME PRINCIPAL
# ==========================================
def tela_login() -> None:
    st.markdown("""
        <style>
            [data-testid="collapsedControl"] { display: none !important; }
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebarNav"], [data-testid="stSidebarNavItems"] { display: none !important; }
            [data-testid="stAppViewContainer"] .main .block-container {
                min-height: calc(100vh - 4.5rem);
                display: flex !important;
                flex-direction: column !important;
                justify-content: center !important;
                padding-top: clamp(0.75rem, 3vh, 2rem) !important;
                padding-bottom: clamp(1rem, 4vh, 2.5rem) !important;
                max-width: 100% !important;
            }
            .ws-login-brand { text-align: center; margin: 0 auto 0.15rem auto; max-width: 100%; }
            .ws-login-title {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-weight: 800;
                font-size: clamp(2rem, 5.5vw, 3.35rem);
                line-height: 1.12;
                letter-spacing: -0.03em;
                margin: 0;
                padding: 0;
            }
            .ws-login-title .wiki { color: #1e5fbf; }
            .ws-login-title .suporte { color: #0d9488; }
            html[data-theme="dark"] .ws-login-title .wiki { color: #93c5fd; }
            html[data-theme="dark"] .ws-login-title .suporte { color: #5eead4; }
            .ws-login-subtitle {
                text-align: center;
                color: #6b7280;
                font-size: clamp(0.88rem, 2.2vw, 1.05rem);
                margin: 0 0 1.1rem 0;
                line-height: 1.4;
            }
            html[data-theme="dark"] .ws-login-subtitle { color: #9ca3af; }
            .ws-login-footer {
                text-align: center;
                color: #9ca3af;
                font-size: clamp(0.72rem, 1.8vw, 0.82rem);
                margin-top: 1.25rem;
            }
            html[data-theme="dark"] .ws-login-footer { color: #6b7280; }
            .stAlert p, .stCaption { text-align: center; display: block; }
            @media (max-width: 480px) {
                .ws-login-title { font-size: clamp(1.65rem, 9vw, 2.35rem); }
            }
        </style>
    """, unsafe_allow_html=True)

    col_vazia1, col_centro, col_vazia2 = st.columns([1, 1.5, 1])

    with col_centro:
        st.markdown(
            """
            <div class="ws-login-brand">
                <h1 class="ws-login-title" aria-label="WikiSuporte">
                    <span class="wiki">Wiki</span><span class="suporte">Suporte</span>
                </h1>
            </div>
            <p class="ws-login-subtitle">Plataforma de Suporte Técnico</p>
            """,
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown("<h4 style='text-align: center;'>🔐 Login </h4>", unsafe_allow_html=True)

            with st.form("form_login"):
                usuario = st.text_input("👤 Usuário", placeholder="Insira o seu nome de usuário")
                senha = st.text_input("🔑 Senha", type="password", placeholder="••••••••")
                st.markdown("<br>", unsafe_allow_html=True)
                btn_login = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if btn_login:
                if usuario and senha:
                    # Evita credenciais em cache (TTL 120s) após cadastro/alteração no banco
                    load_credentials_for_stauth.clear()
                    auth = st.session_state.get("_wiki_authenticator_ref") or get_wiki_authenticator()
                    st.session_state["_wiki_authenticator_ref"] = auth
                    login_ok = auth.authentication_controller.login(
                        usuario.strip().lower(),
                        senha,
                        None,
                        None,
                        None,
                        single_session=False,
                        callback=None,
                        captcha=False,
                        entered_captcha=None,
                    )
                    if login_ok:
                        auth.cookie_controller.set_cookie()
                        sync_wiki_session_from_stauth()
                        uid = st.session_state.get("usuario_id")
                        if uid:
                            registrar_log_auditoria(
                                int(uid), "LOGIN", "Usuário autenticou-se com sucesso."
                            )
                        st.session_state["ultimo_acesso"] = datetime.now()
                        st.rerun()
                    elif login_ok is False:
                        st.error("❌ Usuário ou senha incorretos. Por favor, tente novamente.")
                    else:
                        st.error("❌ Não foi possível validar o login. Tente novamente.")
                else:
                    st.warning("⚠️ Por favor, preencha ambos os campos de usuário e senha.")

        st.markdown(
            "<p class='ws-login-footer'>© 2026 WikiSuporte — Desenvolvido por Rafael D. Nascimento.</p>",
            unsafe_allow_html=True,
        )


def tela_home() -> None:

    render_global_notifications_listener()
    wiki_theme_apply_authenticated()

    # --- DADOS DO USUÁRIO ---
    nome_usuario = str(st.session_state.get('usuario_nome', '')).capitalize()
    perfil_usuario = str(st.session_state.get('perfil', 'analista')).lower()
    usuario_id = st.session_state.get('usuario_id', 0)

    # Busca alertas de plantão e correções logo no início
    df_plantao, df_correcoes = obter_alertas_usuario(usuario_id)
    
    # --- CONSTRUÇÃO DA BARRA LATERAL (PÓS-LOGIN) ---
    st.sidebar.markdown(f"## 👤 {nome_usuario}")
    st.sidebar.markdown(f"### {obter_saudacao()}!")
    st.sidebar.caption(f"🛡️ Perfil: **{perfil_usuario.title()}**")
    st.sidebar.divider()

    # Aviso de Plantão
    if not df_plantao.empty:
        st.sidebar.error("🚨 Você tem Plantão hoje!")
        st.sidebar.divider()

    # --- CONTROLE DE PONTO (SEMPRE VISÍVEL) ---
    st.sidebar.markdown("### 🕒 Ponto VR")
    
    agora = datetime.now()
    em_dia_util = agora.weekday() < 5  # 0 a 4 = Segunda a Sexta
    hora_min_atual = agora.hour * 60 + agora.minute
    
    # Lista de horários convertidos em minutos
    horarios_ponto = [480, 720, 810, 1100]  # 08:00, 12:00, 13:30, 18:20
    
    if em_dia_util:
        # Pega o primeiro horário da lista que seja maior que a hora atual
        proximo_ponto = next((h for h in horarios_ponto if h > hora_min_atual), None)
        
        if proximo_ponto is not None:
            # Cálculo de horas e minutos restantes
            diff = proximo_ponto - hora_min_atual
            horas_restantes = diff // 60
            minutos_restantes = diff % 60
            
            # Formatação limpa
            tempo_str = f"{horas_restantes:02d}h {minutos_restantes:02d}m"
            
            # Faltando 5 minutos ou menos, muda a cor do aviso para alertar o usuário
            if diff <= 5:
                st.sidebar.warning(f"⏰ Atenção! Faltam apenas **{minutos_restantes} min** para o ponto.")
            else:
                st.sidebar.info(f"⏳ Próximo ponto em: **{tempo_str}**")
        else:
            st.sidebar.success("✅ Todos os pontos de hoje foram concluídos!")
    else:
        st.sidebar.info("☕ Fim de semana (Sem ponto obrigatório)")

    # Botão de Ponto (Agora independente, sempre fixo na tela)
    st.sidebar.link_button(
        "📍 Bater ponto no VR",
        "https://app2.pontomais.com.br/registrar-ponto",
        use_container_width=True
    )

    st.sidebar.divider()

    # --- BOTÃO DE SAIR (SEMPRE POR ÚLTIMO NA SIDEBAR) ---
    if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True, type="secondary"):
        registrar_log_auditoria(usuario_id, "LOGOUT", "Usuário saiu do sistema.")
        wiki_force_logout()
        st.session_state.clear()
        st.rerun()

    # ==========================================
    # --- ÁREA PRINCIPAL DA TELA (CONTEÚDO) ---
    # ==========================================
    render_home_release_nudge()

    st.markdown(
        """
        <style>
            .block-container { padding-top: 1.25rem; padding-bottom: 1rem; }
            .ws-home-hero {
                text-align: center;
                max-width: 46rem;
                margin: 0 auto 1.25rem auto;
                padding: 0.5rem 0.75rem 0.75rem;
            }
            .ws-home-hero .ws-home-title {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
                font-size: clamp(1.25rem, 3vw, 1.85rem);
                font-weight: 800;
                line-height: 1.35;
                margin: 0 0 0.65rem 0;
                letter-spacing: -0.03em;
            }
            .ws-home-hero .wiki { color: #1e5fbf; }
            .ws-home-hero .suporte { color: #0d9488; }
            html[data-theme="dark"] .ws-home-hero .wiki { color: #93c5fd; }
            html[data-theme="dark"] .ws-home-hero .suporte { color: #5eead4; }
            .ws-home-hero .ws-name-amp {
                color: #4b5563;
                font-weight: 700;
                margin: 0 0.15em;
            }
            html[data-theme="dark"] .ws-home-hero .ws-name-amp { color: #d1d5db; }
            .ws-home-hero a.epsy-home-link {
                display: inline-flex;
                align-items: baseline;
                flex-wrap: wrap;
                justify-content: center;
                text-decoration: none;
                background: transparent;
                padding: 0;
                border-radius: 0;
                margin-left: 0.1em;
                vertical-align: middle;
                box-shadow: none;
            }
            html[data-theme="dark"] .ws-home-hero a.epsy-home-link {
                background: transparent;
                box-shadow: none;
            }
            .ws-home-hero a.epsy-home-link:hover {
                background: transparent;
                text-decoration: underline;
                text-underline-offset: 0.12em;
            }
            html[data-theme="dark"] .ws-home-hero a.epsy-home-link:hover {
                background: transparent;
            }
            .ws-home-hero .epsy-e-mirror {
                display: inline-block;
                color: #ea580c;
                font-weight: 800;
                transform: scaleX(-1);
                margin-right: 0.05em;
            }
            .ws-home-hero .epsy-rest,
            .ws-home-hero .epsy-sistemas {
                color: #0f172a !important;
                font-weight: 700;
            }
            html[data-theme="dark"] .ws-home-hero .epsy-rest,
            html[data-theme="dark"] .ws-home-hero .epsy-sistemas {
                color: #f1f5f9 !important;
            }
            .ws-home-hero .epsy-sistemas { font-weight: 600; }
            .ws-home-hero .ws-home-tagline {
                font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
                font-size: clamp(0.95rem, 2.1vw, 1.125rem);
                line-height: 1.5;
                margin: 0;
                color: #374151;
            }
            html[data-theme="dark"] .ws-home-hero .ws-home-tagline { color: #d1d5db; }
            .ws-home-hero .ws-home-tagline em {
                font-style: italic;
                font-weight: 500;
            }
        </style>
        <header class="ws-home-hero" role="banner" aria-labelledby="ws-home-heading">
            <h1 id="ws-home-heading" class="ws-home-title">
                <span class="wiki">Wiki</span><span class="suporte">Suporte</span>
                <span class="ws-name-amp">&amp;</span>
                <a href="https://epsy.com.br/" target="_blank" rel="noopener noreferrer"
                   class="epsy-home-link"
                   title="EPSY Sistemas — site oficial (abre em nova aba)"
                   aria-label="EPSY Sistemas, site oficial em nova aba">
                    <span class="epsy-e-mirror" aria-hidden="true">E</span><span class="epsy-rest">PSY</span><span class="epsy-sistemas"> Sistemas</span>
                </a>
            </h1>
            <p class="ws-home-tagline"><em>Onde o conhecimento de cada um se une para entregar excelência.</em></p>
        </header>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # SAUDAÇÃO E CLIMA USANDO COMPONENTES NATIVOS
    col_texto = st.container()

    with col_texto:
        # --- 1. Definição segura e local da data (Sem o import aqui dentro!) ---
        hoje = datetime.now()
        dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        data_atual = f"{dias_semana[hoje.weekday()]}, {hoje.strftime('%d/%m/%Y')}"

        # --- 2. OTIMIZAÇÃO: Saudação à prova de bugs de formatação ---
        saudacao = obter_saudacao()
        saudacao_lower = saudacao.lower() 
        
        if "noite" in saudacao_lower:
            icone_saudacao = "🌕 💻"
        elif "tarde" in saudacao_lower:
            icone_saudacao = "🌤️ 💻"
        else:
            icone_saudacao = "☀️ 💻"
        
        # --- 3. UI: Cabeçalho e Descrição ---
        st.header(f"{saudacao}, {nome_usuario}! {icone_saudacao}", anchor=False)

        # --- 4. EXIBIÇÃO: Alertas dinâmicos ---
        total_alertas_reais = len(df_plantao) + len(df_correcoes)
        
        if total_alertas_reais > 0:
            st.markdown(f"**📅 {data_atual}** &nbsp;|&nbsp; ⚡ **{total_alertas_reais}** alerta(s) no sistema")
        else:
            st.markdown(f"**📅 {data_atual}**")
        
        st.write("")

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

        # 2. RENDERIZAÇÃO DOS TROFÉUS (Logo após o divisor, antes das notificações)
        if kpis:
            renderizar_dashboard_conquistas(kpis)
        else:
            st.warning("Não foi possível carregar seus indicadores de desempenho.")
        
        st.divider()  # Divisor entre o Ranking e as Notificações

        # 1. Padronização dos Alertas em uma Lista de Dicionários
        notificacoes_atuais: list[dict] = []

        try:
            from services.notificacoes_representante import (
                rodar_sincronizacao_completa,
                listar_notificacoes_usuario,
            )
            agora = datetime.now()
            ultima_sync = st.session_state.get("ws_last_notif_sync")
            # Executa a sincronização no máximo a cada 5 minutos nesta sessão
            if not ultima_sync or (agora - ultima_sync).total_seconds() > 300:
                rodar_sincronizacao_completa()
                st.session_state["ws_last_notif_sync"] = agora
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

        # Notificação de plantão (se houver)
        if not df_plantao.empty:
            entrada_raw = df_plantao.iloc[0]['data_hora_entrada']
            saida_raw = df_plantao.iloc[0]['data_hora_saida']
            entrada = entrada_raw.strftime('%H:%M') if isinstance(entrada_raw, datetime) else str(entrada_raw)[:5]
            saida = saida_raw.strftime('%H:%M') if isinstance(saida_raw, datetime) else str(saida_raw)[:5]
                
            notificacoes_atuais.append({
                'id': f"plantao_{datetime.now().strftime('%Y%m%d')}",
                'icone': '🚨',
                'titulo': 'Alerta de Escala: Plantão Hoje',
                'detalhe': (
                    f"Você está de plantão hoje, das {entrada} às {saida}. "
                    f"Mantenha-se atento, saia no horário e não esqueça de bater o ponto no VR."
                ),
                'url_botao': "https://app2.pontomais.com.br/registrar-ponto",
                'label_botao': "🕒 Bater ponto no VR",
            })

        # Notificações de correções pendentes (releases)
        if not df_correcoes.empty:
            for _, row in df_correcoes.iterrows():
                notificacoes_atuais.append({
                    'id': f"chamado_{row['nr_chamado']}",
                    'icone': '⚠️',
                    'titulo': f"Validação Pendente: Chamado {row['nr_chamado']}",
                    'detalhe': (
                        f"A release {row['versao']} requer a sua validação para o chamado {row['nr_chamado']}. "
                        f"Por favor, realize a conferência técnica."
                    )
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

                            # Se quiser, aqui também pode usar o URL da notificação de plantão,
                            # por exemplo exibindo um botão dentro do expander:
                            if notif.get("url_botao"):
                                st.link_button(
                                    notif.get("label_botao", "🕒 Bater ponto no VR"),
                                    notif["url_botao"],
                                    use_container_width=True,
                                )

                            # Botão para mover para o histórico
                            if st.button("Marcar como lida", key=f"btn_read_{notif['id']}"):
                                st.session_state['notificacoes_lidas'].append(notif['id'])
                                if notif.get("db_id"):
                                    try:
                                        from services.notificacoes_representante import marcar_lida
                                        marcar_lida(int(notif["db_id"]), usuario_id)
                                    except Exception:
                                        pass
                                st.rerun()  # Atualiza a tela imediatamente
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
    if kpis.get("em_pausa"):
        st.info(
            "🏖️ Seu perfil está em modo de pausa (Férias/Atendimento Externo). "
            "Suas metas de contribuição e penalidades estão suspensas nesta semana."
        )

    nivel_txt = str(kpis.get("nivel_atual", "Iniciante 🌱"))
    partes_nivel = nivel_txt.split()
    icone_nivel = partes_nivel[-1] if partes_nivel else "🌱"
    avatar_html = _html_avatar_perfil_circular(kpis.get("caminho_foto_perfil"))

    # 1. CABEÇALHO DE NÍVEL E PROGRESSO (UX Gamificada)
    with st.container(border=True):
        if avatar_html:
            col_foto, col_rank_icon, col_progress = st.columns([1, 1, 3])
            with col_foto:
                st.markdown(avatar_html, unsafe_allow_html=True)
            with col_rank_icon:
                st.markdown(
                    f"<h1 style='text-align: center; margin:0;'>{icone_nivel}</h1>",
                    unsafe_allow_html=True,
                )
            with col_progress:
                st.markdown(f"**Nível Atual:** {nivel_txt}")
                st.progress(float(kpis.get("progresso_nivel", 0.0)))
                proximo_xp = 1000 - (int(kpis.get("meu_xp", 0)) % 1000)
                st.caption(f"✨ Faltam **{proximo_xp} XP** para o próximo nível")
        else:
            col_rank_icon, col_progress = st.columns([1, 4])
            with col_rank_icon:
                st.markdown(
                    f"<h1 style='text-align: center; margin:0;'>{icone_nivel}</h1>",
                    unsafe_allow_html=True,
                )
            with col_progress:
                st.markdown(f"**Nível Atual:** {nivel_txt}")
                st.progress(float(kpis.get("progresso_nivel", 0.0)))
                proximo_xp = 1000 - (int(kpis.get("meu_xp", 0)) % 1000)
                st.caption(f"✨ Faltam **{proximo_xp} XP** para o próximo nível")

    st.write("")

    # 2. GRID DE KPIs PRINCIPAIS (3 Colunas)
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.metric(
                label="⭐ XP Acumulado",
                value=f"{kpis['meu_xp']} XP",
                delta="Pontos Totais",
            )
            st.caption("Baseado em Posts + Upvotes")

    with col2:
        with st.container(border=True):
            pos = kpis["posicao_ranking"]
            label_rank = (
                "🏆 Posição no Ranking"
                if "1º" in pos or "2º" in pos or "3º" in pos
                else "🏅 Posição na Equipe"
            )
            st.metric(label=label_rank, value=pos)
            st.caption("Ranking de Qualidade")

    with col3:
        with st.container(border=True):
            impacto_total = kpis["impacto_visualizacoes"] + (kpis["upvotes_recebidos"] * 5)
            st.metric(label="🚀 Impacto Total", value=impacto_total)
            st.caption(
                f"👀 {kpis['impacto_visualizacoes']} views | 👍 {kpis['upvotes_recebidos']} úteis"
            )

    st.write("")

    # 3. SEÇÃO DE ENGAJAMENTO (Missões + alertas XP / penalidades / bônus)
    tem_missoes = bool(kpis.get("missoes_ativas"))
    dias_sem = int(kpis.get("dias_sem_contribuir", 0))
    em_pausa = bool(kpis.get("em_pausa"))
    pen_sem = int(kpis.get("penalidade_sofrida_semana", 0))
    bonus_sem = bool(kpis.get("bonus_recebido_semana"))
    tem_alertas_xp = (
        (not em_pausa and dias_sem >= 5)
        or bonus_sem
        or (pen_sem < 0)
        or tem_missoes
    )

    if tem_alertas_xp:
        with st.expander("🎯 **Missões e Desafios da Semana**", expanded=True):
            if not em_pausa and dias_sem >= 5:
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(90deg, #fff3e0 0%, #ffebee 100%);
                        border-left: 4px solid #e65100;
                        padding: 0.75rem 1rem;
                        border-radius: 6px;
                        margin-bottom: 0.75rem;
                    ">
                        <strong style="color:#bf360c;">⚠️ Atenção — risco de penalidade</strong><br/>
                        <span style="color:#5d4037;">
                            Já se passaram <strong>{}</strong> dia(s) sem uma contribuição
                            <strong>aprovada</strong>. Após <strong>7 dias</strong> sem aprovação na janela
                            de XP, pode aplicar-se desconto no fechamento semanal (se não estiver em pausa).
                        </span>
                    </div>
                    """.format(dias_sem),
                    unsafe_allow_html=True,
                )

            if bonus_sem:
                st.success(
                    "🎉 **Bônus da semana!** Você recebeu XP extra pelo desempenho "
                    "(ex.: meta semanal de aprovações — típico **+1000 XP**). Parabéns!"
                )

            if pen_sem < 0:
                st.caption(
                    f"📉 No último fechamento semanal foi aplicado desconto de **{pen_sem} XP** "
                    "em eventos de penalidade registados nesta semana ISO."
                )

            if tem_missoes:
                for missao in kpis["missoes_ativas"]:
                    st.markdown(f"{missao}")
                st.caption("Complete missões para ganhar bônus de XP e medalhas exclusivas.")

    st.divider()

    # 4. MINI-RESUMO DE CONTRIBUIÇÕES
    st.subheader("📚 Minhas Estatísticas", anchor=False)
    c1, c2, c3 = st.columns(3)
    c1.write(f"📂 **Posts Aprovados:** {kpis['minhas_dicas']}")
    c2.write(f"👍 **Votos Recebidos:** {kpis['upvotes_recebidos']}")
    dias_u = int(kpis.get("dias_sem_contribuir", 0))
    if dias_u >= 999:
        ultima_txt = "Nenhuma contribuição aprovada registada (com data de avaliação)"
    elif dias_u <= 0:
        ultima_txt = "Dados indisponíveis ou migração pendente (`data_avaliacao`)"
    else:
        ultima_txt = f"{dias_u} dia(s) desde a última contribuição aprovada"
    c3.write(f"📅 **Última contribuição aprovada:** {ultima_txt}")



    # st.divider()
# ==========================================
# 7. CONTROLADOR DE FLUXO PRINCIPAL
# ==========================================
if not st.session_state['autenticado']:
    tela_login()
else:
    tela_home()