import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection
from datetime import datetime

st.set_page_config(page_title="Home WikiSuporte", page_icon="🏠", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

nome_usuario = st.session_state.get('nome', 'Gestor')
id_logado = st.session_state.get('usuario_id', 0)

# ==========================================
# 1. FUNÇÕES DE DADOS (COM CACHE)
# ==========================================
@st.cache_data(ttl=300) 
def obter_alertas_usuario(usuario_id):
    engine = get_connection()
    try:
        query_plantao = text("SELECT data_hora_entrada, data_hora_saida FROM plantoes_epsy WHERE id_analista_epsy = :uid AND data_hora_entrada::DATE = CURRENT_DATE")
        df_plantao = pd.read_sql(query_plantao, engine, params={"uid": usuario_id})
        
        query_release = text("""
            SELECT r.versao, c.nr_chamado 
            FROM release_chamados_correcao rc
            JOIN releases_tecnuv r ON rc.id_release = r.id_release
            JOIN chamados_tecnuv c ON rc.nr_chamado = c.nr_chamado
            WHERE c.id_usuario_epsy = :uid AND rc.validado_epsy = FALSE
        """)
        df_release = pd.read_sql(query_release, engine, params={"uid": usuario_id})
        
        return df_plantao, df_release
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=300)
def obter_kpis_home(usuario_id):
    """Busca os dados de gamificação do analista e o status geral do PSY."""
    engine = get_connection()
    kpis = {
        "minhas_dicas": 0, "meu_xp": 0, "posicao_ranking": "-",
        "chamados_ativos": 0, "total_chamados": 0, "atualizados_hoje": 0, "ultima_verificacao": "Aguardando..."
    }
    try:
        with engine.connect() as conn:
            # 1. KPIs Pessoais (Gamificação)
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
            
            # 2. Radar do Assistente Virtual PSY (Tabela de Chamados)
            
            # Chamados Ativos (Blindado com as novas regras de Maiúsculas e Data de Encerramento Nula)
            query_ativos = text("""
                SELECT COUNT(*) FROM chamados_tecnuv 
                WHERE status_atual NOT IN ('Encerrado', 'Cancelado', 'ENCERRADO', 'CANCELADO') 
                AND data_encerramento IS NULL
                AND status_atual IS NOT NULL 
                AND TRIM(status_atual) != ''
            """)
            kpis["chamados_ativos"] = conn.execute(query_ativos).scalar() or 0
            
            # Total Histórico de Chamados (Todos os válidos já abertos pela EPSY)
            query_total = text("""
                SELECT COUNT(*) FROM chamados_tecnuv 
                WHERE status_atual IS NOT NULL 
                AND TRIM(status_atual) != ''
            """)
            kpis["total_chamados"] = conn.execute(query_total).scalar() or 0
            
            # Atualizados Hoje
            query_hoje = text("SELECT COUNT(*) FROM chamados_tecnuv WHERE DATE(ultima_alteracao_tecnuv) = CURRENT_DATE OR DATE(ultima_verificacao_robo) = CURRENT_DATE")
            kpis["atualizados_hoje"] = conn.execute(query_hoje).scalar() or 0
            
            # Última Verificação
            query_hora = text("SELECT MAX(ultima_verificacao_robo) FROM chamados_tecnuv")
            ultima_hora = conn.execute(query_hora).scalar()
            if ultima_hora: kpis["ultima_verificacao"] = ultima_hora.strftime("%H:%M")
            
    except Exception:
        pass
    return kpis

# ==========================================
# 2. CABEÇALHO E ALERTAS
# ==========================================
st.title(f"Bem-vindo(a), {nome_usuario}! 👋")
st.markdown("Este é o seu painel de controle central do **WikiSuporte**. Acompanhe os seus indicadores, os alertas do dia e o que o nosso assistente virtual tem feito nos bastidores.")

df_plantao, df_correcoes = obter_alertas_usuario(id_logado)
kpis = obter_kpis_home(id_logado)

# --- SISTEMA DE ALERTAS INTELIGENTES ---
if not df_plantao.empty or not df_correcoes.empty:
    with st.container(border=True):
        if not df_plantao.empty:
            entrada = df_plantao.iloc[0]['data_hora_entrada'].strftime('%H:%M') if isinstance(df_plantao.iloc[0]['data_hora_entrada'], datetime) else str(df_plantao.iloc[0]['data_hora_entrada'])[:5]
            saida = df_plantao.iloc[0]['data_hora_saida'].strftime('%H:%M') if isinstance(df_plantao.iloc[0]['data_hora_saida'], datetime) else str(df_plantao.iloc[0]['data_hora_saida'])[:5]
            st.error(f"🚨 **ALERTA DE ESCALA:** Você está no plantão de hoje! (Horário: {entrada} às {saida})")

        if not df_correcoes.empty:
            chamados_str = ", ".join([str(n) for n in df_correcoes['nr_chamado'].tolist()])
            st.warning(f"⚠️ **AÇÃO REQUERIDA:** Você possui validações pendentes de release nos chamados: **{chamados_str}**.")

# ==========================================
# 3. OS MEUS INDICADORES (GAMIFICAÇÃO)
# ==========================================
st.markdown("### 🏆 Meu Desempenho")
col_xp, col_dicas, col_rank = st.columns(3)

with col_xp:
    st.metric(label="⚡ Meu XP Total", value=f"{kpis['meu_xp']} XP", delta="Baseado em aprovações")
with col_dicas:
    st.metric(label="📚 Contribuições Oficiais", value=kpis['minhas_dicas'], delta="Dicas ativas", delta_color="normal")
with col_rank:
    st.metric(label="🏅 Posição na Equipe", value=kpis['posicao_ranking'], delta="Leaderboard")

st.divider()

# ==========================================
# 4. RADAR DO ASSISTENTE VIRTUAL PSY & ACESSO RÁPIDO
# ==========================================
col_radar, col_acoes = st.columns([1.5, 2.5])

with col_radar:
    st.markdown("### 📡 Radar do PSY")
    with st.container(border=True):
        st.markdown(f"**Status:** 🟢 Online")
        st.markdown(f"**Última Varredura:** {kpis['ultima_verificacao']}")
        st.markdown(f"**Total Histórico EPSY:** {kpis['total_chamados']} chamados")
        st.markdown(f"**Chamados na Fila Ativa:** {kpis['chamados_ativos']}")
        st.markdown(f"**Atualizados Hoje:** {kpis['atualizados_hoje']}")
        st.caption("O Assistente Virtual PSY monitoriza a fila da Tecnuv a cada 30 minutos em busca de órfãos e cobranças.")

with col_acoes:
    st.markdown("### 🚀 Acesso Rápido")
    # Busca interativa que redireciona o usuário para aproveitar a IA
    with st.form("form_busca_rapida"):
        st.markdown("Tem alguma dúvida técnica agora?")
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            busca = st.text_input("Pesquisar no WikiSuporte:", placeholder="Ex: Erro de comunicação bico 00", label_visibility="collapsed")
        with col_btn:
            btn_buscar = st.form_submit_button("🔍 Perguntar ao PSY", use_container_width=True, type="primary")
            
        if btn_buscar:
            st.info("💡 Dica: Para usar a Inteligência Artificial, acesse a aba 'Pesquisar com PSY IA' no menu Contribuições.")
            st.switch_page("pages/7_🤝_Contribuicoes_Suporte.py")

    # Botões de navegação elegantes
    st.write("")
    btn_m1, btn_m2, btn_m3, btn_m4 = st.columns(4)
    if btn_m1.button("📖 Manuais", use_container_width=True): st.switch_page("pages/8_📖_Manuais_PG.py")
    if btn_m2.button("📊 Tickets", use_container_width=True): st.switch_page("pages/5_📊_Dashboard_Tickets_EPSY.py")
    if btn_m3.button("📚 Wikis", use_container_width=True): st.switch_page("pages/6_📚_Wikis_HP.py")
    if btn_m4.button("🤝 Contribuir", use_container_width=True): st.switch_page("pages/7_🤝_Contribuicoes_Suporte.py")

st.divider()

# ==========================================
# 5. MENSAGEM DO SISTEMA
# ==========================================
st.info("💡 **Recado do PSY:** A sua participação faz toda a diferença para manter o WikiSuporte sempre atualizado. Se encontrar uma solução nova no seu dia a dia, não a guarde só para si. Clique em 'Contribuir' e partilhe com a equipa!")