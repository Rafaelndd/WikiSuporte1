import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection

st.set_page_config(page_title="Home WikiSuporte", page_icon="🏠", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

nome_usuario = st.session_state.get('nome', 'Gestor')
id_logado = st.session_state.get('usuario_id', 0)

@st.cache_data(ttl=600) 
def obter_alertas_usuario(usuario_id):
    engine = get_connection()
    try:
        # 1. Verifica Plantão de Hoje
        query_plantao = text("SELECT data_hora_entrada, data_hora_saida FROM plantoes_epsy WHERE id_analista_epsy = :uid AND data_hora_entrada::DATE = CURRENT_DATE")
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
st.markdown("Este é o painel de controle do WikiSuporte, onde você pode acessar rapidamente os recursos essenciais para o seu dia a dia no suporte técnico. Fique atento(a) aos alertas abaixo para não perder nenhuma informação importante!")

df_plantao, df_correcoes = obter_alertas_usuario(id_logado)

# --- SISTEMA DE ALERTAS INTELIGENTES ---
if not df_plantao.empty:
    entrada = df_plantao.iloc[0]['data_hora_entrada'].strftime('%H:%M')
    saida = df_plantao.iloc[0]['data_hora_saida'].strftime('%H:%M')
    st.error(f"Você está escalado para o plantão de hoje! (Horário: {entrada} às {saida})")

if not df_correcoes.empty:
    chamados_str = ", ".join([str(n) for n in df_correcoes['nr_chamado'].tolist()])
    st.warning(f"Importante! {chamados_str}.")

st.divider()

# ---  ---
st.markdown("### Dúvidas? Encontre Soluções Rápidas!")
st.text_input("Informe sua dúvida ou problema abaixo: ", placeholder="Ex: Bico 00...")

st.write("")
col_graficos, col_alertas = st.columns([2.5, 1])

with col_graficos:
    st.subheader("📚 Acesso Rápido as funcionalidades do WikiSuporte.")
    btn_m1, btn_m2, btn_m3, btn_m4 = st.columns(4)
    if btn_m1.button("📖 Manuais PostoGestor", use_container_width=True): st.switch_page("pages/8_📖_Manuais_PG.py")
    if btn_m2.button("📊 Tickets EPSY", use_container_width=True): st.switch_page("pages/5_📊_Dashboard_Tickets_EPSY.py")
    if btn_m3.button("📚 Wikis HelpDesk", use_container_width=True): st.switch_page("pages/6_📚_Wikis_HP.py")
    if btn_m4.button("🤝 Contribuições", use_container_width=True): st.switch_page("pages/7_🤝_Contribuicoes_Suporte.py")

with col_alertas:
    st.subheader("📌 Recado PSY")
    st.info("Sua participação faz toda a diferença para manter o WikiSuporte sempre atualizado e útil. Se tiver sugestões, correções ou novos conteúdos, fique à vontade para contribuir. Juntos, fortalecemos nosso conhecimento e tornamos o suporte cada vez melhor para toda a equipe.")