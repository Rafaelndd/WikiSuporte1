import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

from sqlalchemy import text
from datetime import datetime, timedelta, time
from modules.database import get_connection

# Logs de auditoria (com tratamento de exceção para evitar falhas caso o módulo não esteja presente)
try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="Dashboard de Atendimentos", page_icon="📊", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')

# ==========================================
# 2. MOTORES DE BUSCA DE DADOS (COM CACHE)
# ==========================================
@st.cache_data(ttl=300)
def carregar_dados_goto():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM atendimentos_goto", engine)
        if not df.empty and 'data_chamada' in df.columns:
            df['data_chamada'] = pd.to_datetime(df['data_chamada'], errors='coerce')
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_dados_multi360():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM atendimentos_multi360", engine)
        if not df.empty:
            df['data_inicio'] = pd.to_datetime(df.get('data_inicio'), errors='coerce')
            df['data_finalizacao'] = pd.to_datetime(df.get('data_finalizacao'), errors='coerce')
            
            if 'data_ultima_mensagem' in df.columns:
                df['data_ultima_mensagem'] = pd.to_datetime(df['data_ultima_mensagem'], errors='coerce')
            else:
                df['data_ultima_mensagem'] = pd.NaT
                
            df['avaliacao'] = pd.to_numeric(df.get('avaliacao'), errors='coerce')
        return df
    except: return pd.DataFrame()


# ==========================================
# 3. INTERFACE E FILTROS GLOBAIS
# ==========================================
st.title("📊 Dashboard de Atendimentos")
st.markdown("Visão clara do fluxo de atendimentos e do desempenho da equipe em todos os canais.")

df_goto_raw = carregar_dados_goto()
df_multi360_raw = carregar_dados_multi360()

if df_goto_raw.empty and df_multi360_raw.empty:
    st.warning("Nenhum arquivo dos atendimentos foi encontrado. Por favor, importe os dados para visualizar o dashboard.")
    st.stop()

# --- NOVO PAINEL DE FILTROS NA PÁGINA PRINCIPAL ---
with st.expander("⚙️ Filtros: ", expanded=True):
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    
    with col_f1:
        # Descobre as datas dinamicamente
        datas_minimas = []
        datas_maximas = []
        if not df_goto_raw.empty:
            datas_minimas.append(df_goto_raw['data_chamada'].dropna().min())
            datas_maximas.append(df_goto_raw['data_chamada'].dropna().max())
        if not df_multi360_raw.empty:
            datas_minimas.append(df_multi360_raw['data_inicio'].dropna().min())
            datas_maximas.append(df_multi360_raw['data_inicio'].dropna().max())
            
        datas_minimas = [d for d in datas_minimas if pd.notna(d)]
        datas_maximas = [d for d in datas_maximas if pd.notna(d)]
        
        if datas_minimas and datas_maximas:
            data_inicial_padrao = min(datas_minimas).date()
            data_final_padrao = max(datas_maximas).date()
        else:
            data_final_padrao = datetime.now().date()
            data_inicial_padrao = (datetime.now() - timedelta(days=30)).date()

        datas_selecionadas = st.date_input("📅 Período (Abertura):", value=(data_inicial_padrao, data_final_padrao), max_value=datetime.now().date() + timedelta(days=1))
        
    with col_f2:
        sla_finalizacao_horas = st.number_input("⏱️ Meta SLA WhatsApp (Horas):", value=24)
        
    with col_f3:
        st.write("") 
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# --- APLICAÇÃO DE FILTROS BÁSICOS (DATAS) ---
df_tel = df_goto_raw.copy()
df_wpp = df_multi360_raw.copy()

if len(datas_selecionadas) == 2:
    data_inicio, data_fim = datas_selecionadas
    data_fim = pd.to_datetime(data_fim) + timedelta(days=1)
    data_inicio = pd.to_datetime(data_inicio)

    if not df_tel.empty:
        df_tel = df_tel[(df_tel['data_chamada'] >= data_inicio) & (df_tel['data_chamada'] < data_fim)]
    if not df_wpp.empty:
        df_wpp = df_wpp[(df_wpp['data_inicio'] >= data_inicio) & (df_wpp['data_inicio'] < data_fim)]

# ==========================================
# 4. TRATAMENTO DE DADOS (WPP & GOTO)
# ==========================================

# --- TRATAMENTO WHATSAPP ---
if not df_wpp.empty:
    df_wpp["TMA_HORAS"] = (df_wpp["data_finalizacao"] - df_wpp["data_inicio"]).dt.total_seconds() / 3600
    if df_wpp['data_ultima_mensagem'].notna().any():
        df_wpp["TEMPO_OCIOSO_HORAS"] = (df_wpp["data_finalizacao"] - df_wpp["data_ultima_mensagem"]).dt.total_seconds() / 3600
    else:
        df_wpp["TEMPO_OCIOSO_HORAS"] = 0.0

    df_wpp["DIA"] = df_wpp["data_inicio"].dt.date
    df_wpp["MES"] = df_wpp["data_inicio"].dt.to_period("M").astype(str)
    df_wpp["HORA"] = df_wpp["data_inicio"].dt.hour
    df_wpp["DIA_SEMANA"] = df_wpp["data_inicio"].dt.day_name()
    
    df_wpp["status"] = df_wpp.get("status", "").fillna("").astype(str)
    df_wpp["FINALIZADO"] = df_wpp["status"].str.lower().str.contains("finalizado", na=False)
    df_wpp["DENTRO_SLA"] = df_wpp["TMA_HORAS"] <= sla_finalizacao_horas

    # SCORE COMPOSTO WPP
    def normalizar(serie):
        return (serie - serie.min()) / (serie.max() - serie.min() + 0.0001)

    df_validos = df_wpp.dropna(subset=['atendente'])
    if not df_validos.empty:
        score_df = pd.DataFrame({
            "Volume": df_validos.groupby("atendente").size(),
            "TMA": df_validos.groupby("atendente")["TMA_HORAS"].mean(),
            "Avaliacao": df_validos.groupby("atendente")["avaliacao"].mean(),
            "Finalizacao": df_validos.groupby("atendente")["FINALIZADO"].mean()
        }).fillna(0)
        score_df["Score"] = (normalizar(score_df["Volume"]) * 0.30 + (1 - normalizar(score_df["TMA"])) * 0.30 + normalizar(score_df["Avaliacao"]) * 0.20 + normalizar(score_df["Finalizacao"]) * 0.20)
    else:
        score_df = pd.DataFrame()

# --- TRATAMENTO TELEFONIA (GOTO) ---
def extrair_minutos_duracao(valor):
    """Converte strings de duração (ex: 00:05:30) ou segundos para Minutos."""
    try:
        if pd.isna(valor): return 0.0
        if isinstance(valor, (int, float)): return float(valor) / 60.0
        partes = str(valor).split(':')
        if len(partes) == 3: return (int(partes[0]) * 60) + int(partes[1]) + (int(partes[2]) / 60.0)
        if len(partes) == 2: return int(partes[0]) + (int(partes[1]) / 60.0)
        return 0.0
    except: return 0.0

if not df_tel.empty:
    df_tel['DIA'] = df_tel['data_chamada'].dt.date
    if 'duracao' in df_tel.columns:
        df_tel['duracao_minutos'] = df_tel['duracao'].apply(extrair_minutos_duracao)
    else:
        df_tel['duracao_minutos'] = 0.0
    
    # Padroniza a coluna do agente de telefonia
    coluna_agente_tel = 'usuario' if 'usuario' in df_tel.columns else 'nome' if 'nome' in df_tel.columns else None

# ==========================================
# 5. CONSTRUÇÃO DAS ABAS PRINCIPAIS
# ==========================================
aba_geral, aba_wpp, aba_telefonia = st.tabs(["👁️ Visão Omnichannel", "💬 Mensageria (Multi360)", "📞 Telefonia (GoTo)"])

# ------------------------------------------
# ABA 1: VISÃO OMNICHANNEL (UNIFICADA)
# ------------------------------------------
with aba_geral:
    st.subheader("📈 Visão Geral de Atendimentos")
    
    vol_wpp = len(df_wpp)
    vol_tel = len(df_tel)
    total_interacoes = vol_wpp + vol_tel
    
    perc_wpp = (vol_wpp / total_interacoes * 100) if total_interacoes > 0 else 0
    perc_tel = (vol_tel / total_interacoes * 100) if total_interacoes > 0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Atendimentos", total_interacoes)
    c2.metric("Atendimentos Multi360", vol_wpp, f"{perc_wpp:.1f}% da operação", delta_color="off")
    c3.metric("Atendimentos Goto", vol_tel, f"{perc_tel:.1f}% da operação", delta_color="off")
    
    tma_wpp_min = df_wpp['TMA_HORAS'].mean() * 60 if not df_wpp.empty else 0
    tma_tel_min = df_tel['duracao_minutos'].mean() if not df_tel.empty else 0
    c4.metric("TMA Médio (Voz)", f"{tma_tel_min:.1f} min", "Tempo de Linha")

    st.divider()
    
    if total_interacoes > 0:
        g1, g2 = st.columns([1, 2])
        
        with g1:
            st.markdown("#### Distribuição de Canais")
            df_omni = pd.DataFrame({"Canal": ["WhatsApp", "Telefonia"], "Volume": [vol_wpp, vol_tel]})
            fig_omni = px.pie(df_omni, values='Volume', names='Canal', hole=0.5, color_discrete_sequence=['#25D366', '#007BFF'])
            fig_omni.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
            fig_omni.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_omni, use_container_width=True)
            
        with g2:
            st.markdown("#### Tendência Diária de Atendimentos")
            
            # Prepara os dados diários de ambos os canais para o mesmo gráfico
            trends = []
            if not df_wpp.empty:
                wpp_trend = df_wpp['DIA'].value_counts().reset_index()
                wpp_trend.columns = ['Data', 'Volume']
                wpp_trend['Canal'] = 'WhatsApp'
                trends.append(wpp_trend)
                
            if not df_tel.empty:
                tel_trend = df_tel['DIA'].value_counts().reset_index()
                tel_trend.columns = ['Data', 'Volume']
                tel_trend['Canal'] = 'Telefonia'
                trends.append(tel_trend)
                
            if trends:
                df_trend = pd.concat(trends)
                fig_trend = px.line(df_trend, x='Data', y='Volume', color='Canal', markers=True, color_discrete_map={"WhatsApp": "#25D366", "Telefonia": "#007BFF"})
                fig_trend.update_layout(margin=dict(t=0, b=0, l=0, r=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_trend, use_container_width=True)

# ------------------------------------------
# ABA 2: MULTI360 (WHATSAPP)
# ------------------------------------------
with aba_wpp:
    if df_wpp.empty:
        st.info("Nenhum dado do Multi360 importado para o período selecionado.")
    else:
        sub_exec, sub_indiv, sub_qual, sub_oper, sub_estrat = st.tabs(["📌 Visão Geral", "👤 Performance Individual", "⭐ Qualidade", "⚙️ Operacional", "📊 Estratégico"])

        with sub_exec:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total de Atendimentos", len(df_wpp))
            col2.metric("Tempo Médio de Atendimento (h)", round(df_wpp["TMA_HORAS"].mean(), 2))
            col3.metric("% Dentro SLA", f"{round(df_wpp['DENTRO_SLA'].mean()*100, 1)}%")
            col4.metric("Avaliação Média", round(df_wpp["avaliacao"].mean(), 2))

            st.subheader("🏆 Ranking de avaliações Multi360")
            if not score_df.empty:
                st.dataframe(score_df.sort_values("Score", ascending=False).style.format("{:.2f}"), use_container_width=True)

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.subheader("📈 Tendência TMA Diário")
                tma_diario = df_wpp.groupby("DIA")["TMA_HORAS"].mean().reset_index()
                fig_tma = px.line(tma_diario, x="DIA", y="TMA_HORAS", markers=True)
                st.plotly_chart(fig_tma, use_container_width=True)
            with col_g2:
                st.subheader("🔥 Mapa visual do TMA Diário (Volume Dia x Hora)")
                heatmap = df_wpp.pivot_table(index="DIA_SEMANA", columns="HORA", values="protocolo", aggfunc="count").fillna(0)
                dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                heatmap = heatmap.reindex([d for d in dias_ordem if d in heatmap.index])
                fig_heat = px.imshow(heatmap, aspect="auto", color_continuous_scale='YlOrRd')
                st.plotly_chart(fig_heat, use_container_width=True)

        with sub_indiv:
            atendentes_lista = df_wpp["atendente"].dropna().unique().tolist()
            if atendentes_lista:
                atendente = st.selectbox("Selecione o atendente:", atendentes_lista)
                df_at = df_wpp[df_wpp["atendente"] == atendente]

                c_at1, c_at2, c_at3, c_at4 = st.columns(4)
                c_at1.metric("Volume de Atendimentos", len(df_at))
                c_at2.metric("TMA Médio (h)", round(df_at["TMA_HORAS"].mean(), 2))
                c_at3.metric("Ociosidade Média (h)", round(df_at["TEMPO_OCIOSO_HORAS"].mean(), 2))
                c_at4.metric("Score Geral", round(score_df.loc[atendente]["Score"], 2) if atendente in score_df.index else "N/A")

                c_graf1, c_graf2 = st.columns(2)
                with c_graf1:
                    prod_mensal = df_at.groupby("MES").size().reset_index(name="Volume")
                    st.plotly_chart(px.line(prod_mensal, x="MES", y="Volume", markers=True, title="Produção Mensal"), use_container_width=True)
                with c_graf2:
                    st.plotly_chart(px.scatter(df_at, x="TMA_HORAS", y="avaliacao", color="avaliacao", color_continuous_scale='RdYlGn', title="TMA x Avaliação"), use_container_width=True)

        with sub_qual:
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                st.subheader("⭐ Ranking de Avaliações por Atendente")
                ranking_nota = df_wpp.groupby("atendente")["avaliacao"].mean().sort_values(ascending=False).reset_index()
                st.dataframe(ranking_nota.style.format({'avaliacao': "{:.2f}"}), use_container_width=True)
            with col_q2:
                st.plotly_chart(px.scatter(df_wpp, x="TMA_HORAS", y="avaliacao", color="atendente", title="Correlação Geral TMA x Nota"), use_container_width=True)

        with sub_oper:
            co1, co2 = st.columns(2)
            with co1:
                vol_hora = df_wpp.groupby("HORA").size().reset_index(name="Volume")
                st.plotly_chart(px.bar(vol_hora, x="HORA", y="Volume", color='Volume', color_continuous_scale='Blues', title="Volume por Hora"), use_container_width=True)
            with co2:
                st.plotly_chart(px.box(df_wpp, y="TMA_HORAS", points="outliers", title="Outliers de Tempo (TMA)"), use_container_width=True)

        with sub_estrat:
            ce1, ce2 = st.columns(2)
            with ce1:
                if "departamento" in df_wpp.columns:
                    dept = df_wpp.groupby("departamento")["TMA_HORAS"].mean().reset_index().sort_values('TMA_HORAS', ascending=False)
                    st.plotly_chart(px.bar(dept, x="departamento", y="TMA_HORAS", title="TMA Médio por Setor"), use_container_width=True)
            with ce2:
                pareto = df_wpp["atendente"].value_counts().reset_index()
                pareto.columns = ["Atendente", "Volume"]
                st.plotly_chart(px.bar(pareto, x="Atendente", y="Volume", title="Distribuição de Carga de Trabalho (Pareto)"), use_container_width=True)

# ------------------------------------------
# ABA 3: TELEFONIA (GOTO)
# ------------------------------------------
with aba_telefonia:
    if df_tel.empty:
        st.info("Nenhum arquivo do Goto importado para o período selecionado.")
    else:
        tab_tel_geral, tab_tel_agentes = st.tabs(["📌 Visão Geral", "👤 Performance dos atendimentos por Atendente"])
        
        with tab_tel_geral:
            st.subheader("Métricas Gerais Goto")
            
            t_col1, t_col2, t_col3 = st.columns(3)
            t_col1.metric("Total de Ligações", len(df_tel))
            t_col2.metric("TMA (Tempo Médio/Minutos)", f"{df_tel['duracao_minutos'].mean():.1f} min")
            
            total_horas_linha = df_tel['duracao_minutos'].sum() / 60
            t_col3.metric("Tempo Total em Linha", f"{total_horas_linha:.1f} Horas")
            
            st.divider()
            
            df_vol_dia_tel = df_tel['DIA'].value_counts().sort_index().reset_index()
            df_vol_dia_tel.columns = ['Data', 'Volume']
            fig_linha_tel = px.line(df_vol_dia_tel, x='Data', y='Volume', title="Fluxo Diário de Ligações", markers=True)
            fig_linha_tel.update_traces(line_color='#007BFF')
            st.plotly_chart(fig_linha_tel, use_container_width=True)

        with tab_tel_agentes:
            if coluna_agente_tel:
                st.subheader("Análise de Produtividade por atendente (Goto)")
                
                # Prepara o DataFrame agrupado por Agente
                df_agentes_tel = df_tel.groupby(coluna_agente_tel).agg(
                    Volume=('DIA', 'count'),
                    TMA_Minutos=('duracao_minutos', 'mean'),
                    Tempo_Total_Minutos=('duracao_minutos', 'sum')
                ).reset_index().sort_values('Volume', ascending=False)
                
                c_tel1, c_tel2 = st.columns(2)
                
                with c_tel1:
                    fig_tel_vol = px.bar(df_agentes_tel.head(10), x='Volume', y=coluna_agente_tel, orientation='h', title="Top 10 Agentes (Por Volume)", color='Volume', color_continuous_scale='Blues')
                    fig_tel_vol.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_tel_vol, use_container_width=True)
                    
                with c_tel2:
                    df_tma_agente = df_agentes_tel.sort_values('TMA_Minutos', ascending=False).head(10)
                    fig_tel_tma = px.bar(df_tma_agente, x='TMA_Minutos', y=coluna_agente_tel, orientation='h', title="Maiores Tempos Médios (TMA em min)", color='TMA_Minutos', color_continuous_scale='Reds')
                    fig_tel_tma.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig_tel_tma, use_container_width=True)
                
                st.markdown("#### Dados Detalhados por Atendente (Goto)")
                st.dataframe(df_agentes_tel.style.format({'TMA_Minutos': "{:.1f}", 'Tempo_Total_Minutos': "{:.1f}"}), use_container_width=True, hide_index=True)
            else:
                st.info("Não foi possível indentificar qual atendente realizoou cada ligação. Verifique se o arquivo do Goto possui uma coluna de identificação de agente (ex: 'usuario' ou 'nome').")

registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD", "Acessou o dashboard de atendimentos Multi360 e Goto")