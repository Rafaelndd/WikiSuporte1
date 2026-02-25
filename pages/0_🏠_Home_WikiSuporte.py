import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection

st.set_page_config(page_title="Home WikiSuporte", page_icon="🏠", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

nome_usuario = st.session_state.get('nome', 'Gestor')
id_logado = st.session_state.get('usuario_id', 0)

@st.cache_data(ttl=60) # Atualiza a cada 1 min para não perder plantões
def obter_alertas_usuario(usuario_id):
    engine = get_connection()
    try:
        # 1. Verifica Plantão de Hoje
        query_plantao = text("SELECT data_hora_entrada, data_hora_saida FROM plantoes_epsy WHERE id_usuario_epsy = :uid AND data_hora_entrada::DATE = CURRENT_DATE")
        df_plantao = pd.read_sql(query_plantao, engine, params={"uid": usuario_id})
        
        # 2. Verifica Releases (Correções pendentes de validação)
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

st.title(f"Bem-vindo(a), {nome_usuario} 👋")
st.markdown("Cockpit Executivo - Alertas, Plantões e Base de Conhecimento.")

df_plantao, df_correcoes = obter_alertas_usuario(id_logado)

# --- SISTEMA DE ALERTAS INTELIGENTES ---
if not df_plantao.empty:
    entrada = df_plantao.iloc[0]['data_hora_entrada'].strftime('%H:%M')
    saida = df_plantao.iloc[0]['data_hora_saida'].strftime('%H:%M')
    st.error(f"🚨 **ALERTA DE PLANTÃO:** Você está escalado para o plantão de hoje! (Horário: {entrada} às {saida})")

if not df_correcoes.empty:
    chamados_str = ", ".join([str(n) for n in df_correcoes['nr_chamado'].tolist()])
    st.warning(f"⚠️ **AÇÃO REQUERIDA:** A Tecnuv liberou correções num Release recente para os seus chamados: **{chamados_str}**. Por favor, valide no sistema e encerre-os.")

st.divider()

# --- BUSCA GLOBAL ---
st.markdown("### 🔍 Pesquisa Rápida Global")
st.text_input("Procure por erros, manuais ou wikis na base de dados (Em breve: Busca Full-Text):", placeholder="Ex: Rejeição SEFAZ...")

st.write("")
col_graficos, col_alertas = st.columns([2.5, 1])

with col_graficos:
    st.subheader("Acesso Rápido aos Módulos")
    btn_m1, btn_m2, btn_m3, btn_m4 = st.columns(4)
    if btn_m1.button("📖 Manuais PostoGestor", use_container_width=True): st.switch_page("pages/8_📖_Manuais_PG.py")
    if btn_m2.button("📊 Tickets EPSY", use_container_width=True): st.switch_page("pages/5_📊_Dashboard_Tickets_EPSY.py")
    if btn_m3.button("📚 Wikis HelpDesk", use_container_width=True): st.switch_page("pages/6_📚_Wikis_HP.py")
    if btn_m4.button("🤝 Contribuições", use_container_width=True): st.switch_page("pages/7_🤝_Contribuicoes_Suporte.py")

with col_alertas:
    st.subheader("📌 Recados Operacionais")
    st.info("Mantenha a base de conhecimento atualizada. Registe as suas soluções diárias na aba de Contribuições.")