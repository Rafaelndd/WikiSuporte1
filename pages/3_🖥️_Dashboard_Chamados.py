import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from sqlalchemy import text
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from modules.database import get_connection

try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="WikiSuporte </>", page_icon="📊", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')

# ==========================================
# 2. MOTORES DE BUSCA E PROCESSAMENTO
# ==========================================
@st.cache_data(ttl=300)
def carregar_dados_tecnuv():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM chamados_tecnuv", engine)
        if not df.empty:
            df['data_abertura'] = pd.to_datetime(df.get('data_abertura'), errors='coerce')
            df['data_encerramento'] = pd.to_datetime(df.get('data_encerramento'), errors='coerce')
            df['usuario_epsy'] = df.get('usuario_epsy', pd.Series(dtype=str)).fillna("Não Informado")
            df['atendente_tecnuv'] = df.get('atendente_tecnuv', pd.Series(dtype=str)).fillna("Não Informado")
            df['versao_sistema'] = df.get('versao_sistema', pd.Series(dtype=str)).fillna("Não Informada")
            df['cliente_nome'] = df.get('cliente_nome', pd.Series(dtype=str)).fillna("Não Informado")
            df['erro_relatado'] = df.get('motivo_abertura_html', pd.Series(dtype=str)).apply(limpar_html)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar chamados: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def carregar_interacoes():
    engine = get_connection()
    try:
        try:
            df = pd.read_sql("SELECT * FROM historico_interacao", engine)
        except:
            df = pd.read_sql("SELECT * FROM historico_interacoes", engine)
            
        if not df.empty and 'data_interacao' in df.columns:
            df['data_interacao'] = pd.to_datetime(df['data_interacao'], errors='coerce')
        return df
    except:
        return pd.DataFrame()

def limpar_html(html_text):
    if not html_text or pd.isna(html_text):
        return ""
    soup = BeautifulSoup(str(html_text), "html.parser")
    texto = soup.get_text(separator=" ")
    return re.sub(r'\s+', ' ', texto).strip()

def detectar_liberacao(texto):
    return re.search(r"Este chamado foi liberado em vers", texto, re.IGNORECASE) is not None

def classificar_reincidencia_e_tempo(df_interacoes_chamado, data_abertura, status_atual):
    if df_interacoes_chamado.empty:
        return "Sem Liberação", pd.NaT

    df_ord = df_interacoes_chamado.sort_values("data_interacao").reset_index(drop=True)
    
    liberacao_idx = None
    data_primeira_liberacao = pd.NaT
    
    for idx, row in df_ord.iterrows():
        texto = limpar_html(row.get("descricao_html", ""))
        if detectar_liberacao(texto):
            liberacao_idx = idx
            if pd.isna(data_primeira_liberacao):
                data_primeira_liberacao = row['data_interacao']
    
    if liberacao_idx is None:
        return "Sem Liberação", pd.NaT

    posteriores = df_ord.iloc[liberacao_idx + 1:]
    
    if posteriores.empty:
        if "Encerrado" in str(status_atual):
            classificacao = "Resolvido Pós-Liberação"
        else:
            classificacao = "Aguardando Validação EPSY"
    else:
        resolveu = False
        for _, row in posteriores.iterrows():
            texto = limpar_html(row.get("descricao_html", ""))
            if "finaliza" in texto.lower() or "encerr" in texto.lower():
                resolveu = True
                break
                
        if resolveu or "Encerrado" in str(status_atual):
            classificacao = "Resolvido Pós-Liberação"
        else:
            classificacao = "Reincidência"
            
    return classificacao, data_primeira_liberacao

# ==========================================
# 3. INTERFACE E CARREGAMENTO
# ==========================================
st.title("🖥️ Dashboard Chamados")
st.markdown("Análise detalhada dos chamados, com foco em tempo de atendimento, reincidências e desempenho da desenvolvedora.")

df_raw = carregar_dados_tecnuv()
df_int = carregar_interacoes()

if df_raw.empty:
    st.warning("WikiSuporte ainda não se conectou ao banco de dados. Entre em contato com o desenvolvedor para resolver o problema.")
    st.stop()

# ==========================================
# 4. PAINEL DE CONTROLO E FILTROS (NA TELA PRINCIPAL)
# ==========================================
with st.expander("⚙️ Filtros: ", expanded=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    
    with col_f1:
        min_data = df_raw['data_abertura'].min().date() if not df_raw['data_abertura'].isna().all() else (datetime.now() - timedelta(days=30)).date()
        max_data = df_raw['data_abertura'].max().date() if not df_raw['data_abertura'].isna().all() else datetime.now().date()
        
        datas_selecionadas = st.date_input("📅 Período (Abertura):", value=(min_data, max_data), max_value=datetime.now().date() + timedelta(days=1))
        
    with col_f2:
        lista_analistas = ["Todos"] + sorted([a for a in df_raw['usuario_epsy'].unique() if a and str(a).strip() != "Não Informado"])
        analista_filtro = st.selectbox("👤 Analista EPSY:", options=lista_analistas, help="Lista com todos analistas")
        
    with col_f3:
        lista_status = ["Todos", "Chamados Ativos (Abertos)", "Resolvidos (Encerrados ou Cancelados)"]
        status_filtro = st.selectbox("📌 Status do Chamado:", options=lista_status)
        
    with col_f4:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", width='stretch'):
            st.cache_data.clear()
            st.rerun()

# --- APLICAÇÃO DOS FILTROS ---
df = df_raw.copy()

if len(datas_selecionadas) == 2:
    d_inicio, d_fim = datas_selecionadas
    d_fim = pd.to_datetime(d_fim) + timedelta(days=1)
    df = df[(df['data_abertura'] >= pd.to_datetime(d_inicio)) & (df['data_abertura'] < d_fim)]

if analista_filtro != "Todos":
    df = df[df['usuario_epsy'] == analista_filtro]

# Lógica robusta de fila ativa (Exclui Encerrados e Cancelados)
if status_filtro == "Chamados Ativos (Abertos)":
    df = df[~df['status_atual'].str.contains("Encerrado|Cancelado", case=False, na=False)]
elif status_filtro == "Resolvidos (Encerrados)":
    df = df[df['status_atual'].str.contains("Encerrado", case=False, na=False)]

if df.empty:
    st.info("Nenhum chamado encontrado com os filtros aplicados. Revise o período ou ajuste os critérios para refinar a busca.")
    st.stop()

# ==========================================
# 5. PROCESSAMENTO ESTRATÉGICO (MÉTRICAS)
# ==========================================
agora = pd.to_datetime(datetime.now())

# 1. Envelhecimento (Aging)
df['dias_aberto'] = (agora - df['data_abertura']).dt.days
df['is_aberto'] = ~df['status_atual'].str.contains("Encerrado|Cancelado", case=False, na=False)

# 2. Reincidência e Tempo até Liberação
resultados_reincidencia = []
tempos_liberacao = []

for _, row in df.iterrows():
    nr = row['nr_chamado']
    status = row['status_atual']
    dt_abertura = row['data_abertura']
    
    interacoes_chamado = df_int[df_int['nr_chamado'] == nr] if not df_int.empty else pd.DataFrame()
    classificacao, dt_primeira_lib = classificar_reincidencia_e_tempo(interacoes_chamado, dt_abertura, status)
    
    resultados_reincidencia.append(classificacao)
    
    if pd.notna(dt_primeira_lib) and pd.notna(dt_abertura):
        tempos_liberacao.append((dt_primeira_lib - dt_abertura).total_seconds() / 86400) # Em dias
    else:
        tempos_liberacao.append(np.nan)

df['classificacao_reincidencia'] = resultados_reincidencia
df['tempo_ate_liberacao_dias'] = tempos_liberacao

# ==========================================
# 6. CONSTRUÇÃO DO DASHBOARD (INTERFACE)
# ==========================================

aba1, aba2, aba3, aba4 = st.tabs([
    "🎯 Visão Geral",
    "⏳ Tempo de espera e gargalos nos chamados com a desenvolvedora.",
    "🐛 Detalhamento de Versões",
    "👥 Chamados por Analistas EPSY & Clientes"
])

# ------------------------------------------
# ABA 1: VISÃO EXECUTIVA
# ------------------------------------------
with aba1:
    total_chamados = len(df)
    abertos = len(df[df['is_aberto']])
    encerrados = total_chamados - abertos
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Volume de Chamados (Período)", total_chamados)
    col2.metric("Chamados Ativos (Em Fila)", abertos, delta="Na Fila", delta_color="inverse")
    col3.metric("Chamados Resolvidos", encerrados, delta="Encerrados")
    
    # Índice de Reincidência
    chamados_com_liberacao = len(df[df['classificacao_reincidencia'] != "Sem Liberação"])
    reincidentes = len(df[df['classificacao_reincidencia'] == "Reincidência"])
    taxa_reincidencia = (reincidentes / chamados_com_liberacao * 100) if chamados_com_liberacao > 0 else 0
    col4.metric("Índice de Reincidência", f"{taxa_reincidencia:.1f}%", delta="Chamados com Reincidência", delta_color="inverse")

    st.divider()
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Fila Atual por Status")
        fila = df['status_atual'].value_counts().reset_index()
        fila.columns = ['Status', 'Volume']
        st.plotly_chart(px.bar(fila, x='Volume', y='Status', orientation='h', color='Status'), width='stretch')
        
    with g2:
        st.subheader("Classificação de Reincidência Pós-Liberação")
        reinc_data = df['classificacao_reincidencia'].value_counts().reset_index()
        reinc_data.columns = ['Classificação', 'Volume']
        fig_reinc = px.pie(reinc_data, values='Volume', names='Classificação', hole=0.4, color='Classificação',
                           color_discrete_map={"Resolvido Pós-Liberação": "#25D366", "Reincidência": "#FF4B4B", "Aguardando Validação EPSY": "#FFA500", "Sem Liberação": "#808080"})
        st.plotly_chart(fig_reinc, width='stretch')

    # NOVO: Tabela detalhada de reincidências
    if reincidentes > 0:
        st.markdown("### 🚨 Detalhamento dos Chamados com Reincidência")
        st.markdown("Lista de chamados que foram liberados, mas apresentaram reincidência, indicando que o problema não foi resolvido mesmo após a liberação da desenvolvedora.")
        df_reincidentes = df[df['classificacao_reincidencia'] == "Reincidência"].copy()
        
        # Cria uma visualização limpa do motivo
        df_reincidentes['Resumo do Erro'] = df_reincidentes['erro_relatado'].str[:100] + "..."
        
        cols_reinc = ['nr_chamado', 'cliente_nome', 'usuario_epsy', 'versao_sistema', 'status_atual', 'Resumo do Erro']
        st.dataframe(df_reincidentes[cols_reinc], hide_index=True, width='stretch')

# ------------------------------------------
# ABA 2: AGING E GARGALOS (FILA COMPLETA)
# ------------------------------------------
with aba2:
    st.subheader("⏳ Análise de Tempo de Espera e Gargalos")
    st.markdown("Tempo em aberto dos chamados por status e motivo, destacando os mais antigos e as principais causas de atraso.")
    
    df_abertos = df[df['is_aberto']].copy()
    
    if df_abertos.empty:
        st.success("Nenhum chamado ativo encontrado. Todos estão resolvidos ou cancelados — ótima organização da equipe!")
    else:
        # Categorização de Aging
        acima_30 = len(df_abertos[df_abertos['dias_aberto'] >= 30])
        acima_60 = len(df_abertos[df_abertos['dias_aberto'] >= 60])
        acima_90 = len(df_abertos[df_abertos['dias_aberto'] >= 90])
        acima_365 = len(df_abertos[df_abertos['dias_aberto'] >= 365])
        
        ca1, ca2, ca3, ca4 = st.columns(4)
        ca1.metric("🟡 Chamados Ativos a Mais de 30 Dias (≥ 30 Dias)", acima_30)
        ca2.metric("🟠 Atenção, Chamados Ativos a Mais de 60 Dias (≥ 60 Dias)", acima_60)
        ca3.metric("🔴 Critico, Chamados Ativos a Mais de 90 Dias (≥ 90 Dias)", acima_90)
        ca4.metric("⛔ Grave, Chamados Ativos a Mais de um ano (≥ 1 Ano)", acima_365)
        
        st.divider()
        
        # Tabela Integral da Fila
        st.markdown("#### 📋 Tabela de Chamados Ativos")
        
        df_abertos_view = df_abertos[['nr_chamado', 'cliente_nome', 'usuario_epsy', 'atendente_tecnuv', 'status_atual', 'dias_aberto', 'erro_relatado']].copy()
        df_abertos_view.rename(columns={
            'nr_chamado': 'Chamado',
            'cliente_nome': 'Cliente',
            'usuario_epsy': 'EPSY (Abertura)',
            'atendente_tecnuv': 'Tecnuv',
            'status_atual': 'Status',
            'dias_aberto': 'Dias em Aberto',
            'erro_relatado': 'Motivo / Erro Relatado'
        }, inplace=True)
        
        # Ordena do mais velho para o mais novo
        df_abertos_view = df_abertos_view.sort_values(by='Dias em Aberto', ascending=False)
        
        st.dataframe(
            df_abertos_view.style.format({"Dias em Aberto": "{:.0f}"}).background_gradient(cmap='Reds', subset=['Dias em Aberto']), 
            hide_index=True, 
            width='stretch',
            height=600
        )

# ------------------------------------------
# ABA 3: ENGENHARIA & VERSÕES
# ------------------------------------------
with aba3:
    st.subheader("🐛 Análise de Bugs por Versão e Assunto")
    
    df_ver = df[~df['versao_sistema'].isin(["Não Informada", "Não Informado", ""])].copy()
    
    if df_ver.empty:
        st.info("O WikiSuporte não conseguiu identificar as versões dos sistemas nos chamados.")
    else:
        v1, v2 = st.columns([1, 1])
        
        with v1:
            st.markdown("#### Chamados por Versão")
            versoes = df_ver["versao_sistema"].value_counts().reset_index().head(10)
            versoes.columns = ['Versão', 'Volume']
            st.plotly_chart(px.bar(versoes, x='Volume', y='Versão', orientation='h', color='Volume', color_continuous_scale='Reds'), width='stretch')
            
        with v2:
            st.markdown("#### Tempo Médio até a 1ª Liberação da Desenvolvedora")
            tma_dev = df['tempo_ate_liberacao_dias'].mean()
            st.metric("Tempo Médio (Dias)", f"{tma_dev:.1f} Dias" if pd.notna(tma_dev) else "N/A", help="Tempo médio entre a abertura do chamado e a primeira liberação da desenvolvedora, indicando a agilidade na resposta inicial.")
            
        st.divider()
        st.markdown("#### 🔍 Detalhamento de Versões")
        st.markdown("Visualize os chamados organizados por versão do sistema, com número, cliente e resumo do erro, facilitando a identificação rápida de padrões e problemas recorrentes em cada release.")
        
        # Cria a tabela exploratória Versão + Erro
        df_ver['Erro Resumido'] = df_ver['erro_relatado'].str[:150] + "..."
        agrupamento_bugs = df_ver[['versao_sistema', 'nr_chamado', 'cliente_nome', 'Erro Resumido']].sort_values(by=['versao_sistema', 'nr_chamado'], ascending=[False, False])
        
        st.dataframe(agrupamento_bugs, hide_index=True, width='stretch')

# ------------------------------------------
# ABA 4: PERFORMANCE EPSY & OFENSORES
# ------------------------------------------
with aba4:
    st.subheader("👥 Análise de Performance")
    
    df_epsy = df[~df['usuario_epsy'].isin(["Não Informado", "Não Informada", ""])].copy()
    
    e1, e2 = st.columns([1, 1])
    
    with e1:
        st.markdown("#### 👤 Chamados Abertos por Analista EPSY")
        if df_epsy.empty:
            st.info("O WikiSuporte não conseguiu identificar os analistas EPSY responsáveis pelos chamados.")
        else:
            analistas = df_epsy["usuario_epsy"].value_counts().reset_index()
            analistas.columns = ['Analista EPSY', 'Volume de Chamados Abertos']
            st.plotly_chart(px.bar(analistas, x='Volume de Chamados Abertos', y='Analista EPSY', orientation='h', color='Volume de Chamados Abertos', color_continuous_scale='Blues'), width='stretch')
            
    with e2:
        st.markdown("#### 🏢 Chamados Abertos por Cliente")
        df_cli = df[~df['cliente_nome'].isin(["Não Informado", "Não Informada", ""])]
        if df_cli.empty:
            st.info("O WikiSuporte não conseguiu identificar os clientes nos chamados.")
        else:
            # Mostra o Cliente, o total e quantos estão em aberto
            clientes_agg = df_cli.groupby('cliente_nome').agg(
                Total_Chamados=('nr_chamado', 'count'),
                Fila_Ativa=('is_aberto', 'sum')
            ).reset_index().sort_values('Total_Chamados', ascending=False).head(15)
            
            clientes_agg.rename(columns={'cliente_nome': 'Cliente', 'Total_Chamados': 'Total Abertos (Período)', 'Fila_Ativa': 'Ainda Pendentes'}, inplace=True)
            
            st.dataframe(clientes_agg, hide_index=True, width='stretch')

registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD_CHAMADOS", "Acessou Dashboard Analítico - Chamados Tecnuv (EPSY)")