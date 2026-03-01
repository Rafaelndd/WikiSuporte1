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
# 5. CONSTRUÇÃO DAS ABAS PRINCIPAIS (UX UX/UI)
# ==========================================
aba_geral, aba_wpp, aba_telefonia = st.tabs(["👁️ Visão Unificada", "💬 WhatsApp (Multi360)", "📞 Ligações (GoTo)"])

# ------------------------------------------
# ABA 1: VISÃO UNIFICADA (GERAL)
# ------------------------------------------
with aba_geral:
    st.markdown("### 📈 Resumo da Operação")
    st.caption("Visão geral somando os esforços de todos os canais de atendimento.")
    
    vol_wpp = len(df_wpp)
    vol_tel = len(df_tel)
    total_interacoes = vol_wpp + vol_tel
    
    perc_wpp = (vol_wpp / total_interacoes * 100) if total_interacoes > 0 else 0
    perc_tel = (vol_tel / total_interacoes * 100) if total_interacoes > 0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    with st.container(border=True):
        c1.metric("Volume Total", total_interacoes, "Atendimentos")
    with st.container(border=True):
        c2.metric("Via WhatsApp", vol_wpp, f"{perc_wpp:.1f}% do total", delta_color="off")
    with st.container(border=True):
        c3.metric("Via Telefone", vol_tel, f"{perc_tel:.1f}% do total", delta_color="off")
    
    tma_wpp_min = df_wpp['TMA_HORAS'].mean() * 60 if not df_wpp.empty else 0
    tma_tel_min = df_tel['duracao_minutos'].mean() if not df_tel.empty else 0
    with st.container(border=True):
        c4.metric("Duração Média (Telefone)", f"{tma_tel_min:.1f} min", "Tempo na linha")

    st.divider()
    
    if total_interacoes > 0:
        g1, g2 = st.columns([1.5, 2.5])
        
        with g1:
            st.markdown("#### Divisão de Canais")
            df_omni = pd.DataFrame({"Canal": ["WhatsApp", "Telefone"], "Volume": [vol_wpp, vol_tel]})
            fig_omni = px.pie(df_omni, values='Volume', names='Canal', hole=0.5, color_discrete_sequence=['#25D366', '#007BFF'])
            fig_omni.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
            fig_omni.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_omni, use_container_width=True)
            st.caption("Proporção de clientes que preferem texto vs. voz.")
            
        with g2:
            st.markdown("#### Movimento Diário")
            trends = []
            if not df_wpp.empty:
                wpp_trend = df_wpp['DIA'].value_counts().reset_index()
                wpp_trend.columns = ['Data', 'Volume']
                wpp_trend['Canal'] = 'WhatsApp'
                trends.append(wpp_trend)
                
            if not df_tel.empty:
                tel_trend = df_tel['DIA'].value_counts().reset_index()
                tel_trend.columns = ['Data', 'Volume']
                tel_trend['Canal'] = 'Telefone'
                trends.append(tel_trend)
                
            if trends:
                df_trend = pd.concat(trends)
                # Trocado para gráfico de Área Suave (mais fácil de ler o volume)
                fig_trend = px.area(df_trend, x='Data', y='Volume', color='Canal', color_discrete_map={"WhatsApp": "#25D366", "Telefone": "#007BFF"})
                fig_trend.update_layout(margin=dict(t=20, b=0, l=0, r=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_trend, use_container_width=True)
                st.caption("Acompanhe os dias de maior sobrecarga na operação.")

# ------------------------------------------
# ABA 2: MULTI360 (WHATSAPP)
# ------------------------------------------
with aba_wpp:
    if df_wpp.empty:
        st.info("Nenhum dado do WhatsApp (Multi360) importado para o período.")
    else:
        # Nomes das abas traduzidos para "Gestorês"
        sub_exec, sub_indiv, sub_qual, sub_oper, sub_estrat = st.tabs(["📌 Resumo da Operação", "👤 Análise por Atendente", "⭐ Notas e Qualidade", "⚙️ Horários de Pico", "📊 Carga de Trabalho"])

        with sub_exec:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total de Conversas", len(df_wpp))
            col2.metric("Tempo Médio (TMA)", f"{round(df_wpp['TMA_HORAS'].mean(), 1)} Horas")
            col3.metric("No Prazo Ideal (SLA)", f"{round(df_wpp['DENTRO_SLA'].mean()*100, 1)}%")
            col4.metric("Nota Média dos Clientes", round(df_wpp["avaliacao"].mean(), 2))

            st.divider()
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("#### 📈 Histórico de Demora (TMA Diário)")
                tma_diario = df_wpp.groupby("DIA")["TMA_HORAS"].mean().reset_index()
                fig_tma = px.bar(tma_diario, x="DIA", y="TMA_HORAS", color_discrete_sequence=['#25D366'])
                fig_tma.update_layout(margin=dict(t=20, b=0, l=0, r=0))
                st.plotly_chart(fig_tma, use_container_width=True)
                st.caption("Mostra se a equipa está a demorar mais ou menos tempo a fechar chamados a cada dia.")
                
            with col_g2:
                st.markdown("#### 🔥 Dias e Horários mais Críticos")
                heatmap = df_wpp.pivot_table(index="DIA_SEMANA", columns="HORA", values="protocolo", aggfunc="count").fillna(0)
                dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                heatmap = heatmap.reindex([d for d in dias_ordem if d in heatmap.index])
                # Traduzindo dias
                heatmap.index = heatmap.index.map({'Monday':'Seg', 'Tuesday':'Ter', 'Wednesday':'Qua', 'Thursday':'Qui', 'Friday':'Sex', 'Saturday':'Sáb', 'Sunday':'Dom'})
                fig_heat = px.imshow(heatmap, aspect="auto", color_continuous_scale='Reds')
                fig_heat.update_layout(margin=dict(t=20, b=0, l=0, r=0))
                st.plotly_chart(fig_heat, use_container_width=True)
                st.caption("Zonas mais escuras indicam o maior volume de mensagens. Ideal para organizar pausas.")

        with sub_indiv:
            atendentes_lista = df_wpp["atendente"].dropna().unique().tolist()
            if atendentes_lista:
                st.markdown("### Selecione o Analista para visualizar o desempenho:")
                atendente = st.selectbox("Escolha o membro da equipe:", atendentes_lista, label_visibility="collapsed")
                df_at = df_wpp[df_wpp["atendente"] == atendente]

                with st.container(border=True):
                    c_at1, c_at2, c_at3, c_at4 = st.columns(4)
                    c_at1.metric("Conversas Assumidas", len(df_at))
                    c_at2.metric("Tempo Médio do Analista", f"{round(df_at['TMA_HORAS'].mean(), 1)}h")
                    c_at3.metric("Tempo sem Resposta", f"{round(df_at['TEMPO_OCIOSO_HORAS'].mean(), 1)}h", help="Tempo que o cliente ficou à espera da última resposta.")
                    c_at4.metric("Nota de Desempenho", round(score_df.loc[atendente]["Score"] * 100, 1) if atendente in score_df.index else "N/A", "%")

                c_graf1, c_graf2 = st.columns(2)
                with c_graf1:
                    prod_mensal = df_at.groupby("MES").size().reset_index(name="Volume")
                    fig_prod = px.bar(prod_mensal, x="MES", y="Volume", title="Volume de Atendimentos por Mês", color_discrete_sequence=['#25D366'])
                    st.plotly_chart(fig_prod, use_container_width=True)
                with c_graf2:
                    # Trocado o Scatter confuso por um Histograma das notas
                    fig_notas = px.histogram(df_at, x="avaliacao", nbins=5, title="Frequência de Notas Recebidas", color_discrete_sequence=['#FFC107'])
                    st.plotly_chart(fig_notas, use_container_width=True)
                    st.caption("Quantas vezes o cliente deu nota 5, 4, etc.")

        with sub_qual:
            col_q1, col_q2 = st.columns([1, 1.5])
            with col_q1:
                st.markdown("#### 🏆 Ranking de Notas")
                ranking_nota = df_wpp.groupby("atendente")["avaliacao"].mean().sort_values(ascending=False).reset_index()
                st.dataframe(ranking_nota.style.format({'avaliacao': "{:.1f}"}), use_container_width=True, hide_index=True)
            with col_q2:
                # Trocado o Scatter por um Gráfico de Barras claro
                fig_rank_notas = px.bar(ranking_nota, x="avaliacao", y="atendente", orientation='h', title="Média de Avaliação por Analista", color='avaliacao', color_continuous_scale='Greens')
                fig_rank_notas.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, b=0, l=0, r=0))
                st.plotly_chart(fig_rank_notas, use_container_width=True)

        with sub_oper:
            co1, co2 = st.columns(2)
            with co1:
                vol_hora = df_wpp.groupby("HORA").size().reset_index(name="Volume")
                fig_hora = px.bar(vol_hora, x="HORA", y="Volume", color='Volume', color_continuous_scale='Blues', title="Volume Total por Hora do Dia")
                st.plotly_chart(fig_hora, use_container_width=True)
            with co2:
                # Trocado o BoxPlot (Outliers) por um Histograma intuitivo
                fig_hist_tma = px.histogram(df_wpp, x="TMA_HORAS", nbins=20, title="Quanto tempo demoram os chamados?", color_discrete_sequence=['#EF553B'])
                fig_hist_tma.update_layout(xaxis_title="Horas para Finalizar", yaxis_title="Quantidade de Chamados")
                st.plotly_chart(fig_hist_tma, use_container_width=True)
                st.caption("Barras mais à direita representam chamados que ficaram muito tempo abertos (Gargalos).")

        with sub_estrat:
            ce1, ce2 = st.columns(2)
            with ce1:
                if "departamento" in df_wpp.columns:
                    dept = df_wpp.groupby("departamento")["TMA_HORAS"].mean().reset_index().sort_values('TMA_HORAS', ascending=True)
                    fig_dept = px.bar(dept, x="TMA_HORAS", y="departamento", orientation='h', title="Qual setor demora mais a resolver?", color='TMA_HORAS', color_continuous_scale='Reds')
                    st.plotly_chart(fig_dept, use_container_width=True)
            with ce2:
                pareto = df_wpp["atendente"].value_counts().reset_index().head(10)
                pareto.columns = ["Analista", "Volume"]
                fig_pareto = px.bar(pareto, x="Analista", y="Volume", title="Quem atende mais clientes? (Top 10 Volume)", color='Volume', color_continuous_scale='Purples')
                st.plotly_chart(fig_pareto, use_container_width=True)

# ------------------------------------------
# ABA 3: TELEFONIA (GOTO)
# ------------------------------------------
with aba_telefonia:
    if df_tel.empty:
        st.info("Nenhum dado de ligações (GoTo) importado para o período.")
    else:
        tab_tel_geral, tab_tel_agentes = st.tabs(["📌 Resumo de Ligações", "👤 Desempenho da Equipe"])
        
        with tab_tel_geral:
            st.markdown("### 📞 Métricas Globais de Voz")
            
            with st.container(border=True):
                t_col1, t_col2, t_col3 = st.columns(3)
                t_col1.metric("Total de Ligações", len(df_tel))
                t_col2.metric("Duração Média por Chamada", f"{df_tel['duracao_minutos'].mean():.1f} minutos")
                
                total_horas_linha = df_tel['duracao_minutos'].sum() / 60
                t_col3.metric("Tempo Total ao Telefone", f"{total_horas_linha:.1f} Horas", "Esforço da equipe")
            
            st.divider()
            
            df_vol_dia_tel = df_tel['DIA'].value_counts().sort_index().reset_index()
            df_vol_dia_tel.columns = ['Data', 'Volume']
            fig_linha_tel = px.area(df_vol_dia_tel, x='Data', y='Volume', title="Fluxo Diário de Ligações", color_discrete_sequence=['#007BFF'])
            fig_linha_tel.update_layout(margin=dict(t=30, b=0, l=0, r=0))
            st.plotly_chart(fig_linha_tel, use_container_width=True)

        with tab_tel_agentes:
            if coluna_agente_tel:
                st.markdown("### 👤 Produtividade ao Telefone")
                
                df_agentes_tel = df_tel.groupby(coluna_agente_tel).agg(
                    Volume=('DIA', 'count'),
                    TMA_Minutos=('duracao_minutos', 'mean'),
                    Tempo_Total_Minutos=('duracao_minutos', 'sum')
                ).reset_index().sort_values('Volume', ascending=False)
                
                c_tel1, c_tel2 = st.columns(2)
                
                with c_tel1:
                    fig_tel_vol = px.bar(df_agentes_tel.head(10), x='Volume', y=coluna_agente_tel, orientation='h', title="Top 10: Quem faz mais ligações?", color='Volume', color_continuous_scale='Blues')
                    fig_tel_vol.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, b=0, l=0, r=0))
                    st.plotly_chart(fig_tel_vol, use_container_width=True)
                    
                with c_tel2:
                    df_tma_agente = df_agentes_tel.sort_values('TMA_Minutos', ascending=False).head(10)
                    fig_tel_tma = px.bar(df_tma_agente, x='TMA_Minutos', y=coluna_agente_tel, orientation='h', title="Top 10: Quem tem as ligações mais longas?", color='TMA_Minutos', color_continuous_scale='Reds')
                    fig_tel_tma.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, b=0, l=0, r=0))
                    st.plotly_chart(fig_tel_tma, use_container_width=True)
                
                st.markdown("#### 📋 Dados Detalhados por Analista")
                # Renomeando colunas do dataframe para exibição
                df_exibicao_tel = df_agentes_tel.rename(columns={coluna_agente_tel: "Analista", "TMA_Minutos": "Duração Média (Min)", "Tempo_Total_Minutos": "Horas Totais na Linha"})
                df_exibicao_tel['Horas Totais na Linha'] = df_exibicao_tel['Horas Totais na Linha'] / 60
                st.dataframe(df_exibicao_tel.style.format({'Duração Média (Min)': "{:.1f}", 'Horas Totais na Linha': "{:.1f}h"}), use_container_width=True, hide_index=True)
            else:
                st.info("O sistema não conseguiu identificar o nome dos agentes no arquivo do GoTo. Verifique se as colunas estão corretas.")

registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD", "Acessou o dashboard de atendimentos Multi360 e Goto")