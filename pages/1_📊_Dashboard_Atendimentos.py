import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text
from datetime import datetime, timedelta, time
from modules.database import get_connection
from services.ui_realtime import render_global_notifications_listener
from config_ramais import (
    RAMAIS_EXCLUIR,
    RAMAL_NOME_ESPECIAL,
    obter_setor_por_nome_analista,
    SETOR_TEF,
    SETOR_SUPORTE_GERAL,
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

logging.info("--- Sistema WikiSuporte - iniciado e logs configurados  ---")

#======================================================================================================================#
# Tenta importar a função de auditoria (Ajuste o caminho se necessário)
try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    # Fallback caso o ficheiro não exista ainda
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass

# Configura a página: título, ícone, layout expandido e barra lateral recolhida por padrão
st.set_page_config(
    page_title="WikiSuporte", 
    page_icon="💡", 
    layout="wide", 
    initial_sidebar_state="collapsed"
)

# Inicializa variáveis de estado da sessão para controle de login e histórico de notificações
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "notificacoes_lidas" not in st.session_state:
    st.session_state["notificacoes_lidas"] = []

# Cadeado de segurança: exige login e perfil adequado
if not st.session_state.get("autenticado", False):
    st.switch_page("app.py")
render_global_notifications_listener()

perfil_logado_raw = str(st.session_state.get("perfil", "analista")).strip().lower()
# Aceita tanto nomenclatura nova quanto antiga, se existir
if perfil_logado_raw in ("desenvolvedor", "dev"):
    perfil_logado = "dev"
elif perfil_logado_raw in ("coordenação", "coordenador"):
    perfil_logado = "coordenador"
else:
    perfil_logado = perfil_logado_raw

if perfil_logado not in ["dev", "coordenador"]:
    st.error("⛔ Acesso Negado.")
    st.stop()


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
def carregar_goto_agent_calls():
    """Chamadas atendidas do relatório GoTo Agent Calls (Contact Resolution = COMPLETED)."""
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT contact_id, contact_creation_time, agent_name, talk_time_millis FROM goto_agent_calls", engine)
        if not df.empty and "contact_creation_time" in df.columns:
            df["contact_creation_time"] = pd.to_datetime(df["contact_creation_time"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()

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
st.markdown("Análise detalhada dos atendimentos via GoTo e Multi360.")
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Ajuste **Filtros** (período, analista, cliente). As **abas** separam GoTo, Multi360 e visões combinadas. "
        "Indicadores e gráficos mostram volume, tempo médio, satisfação e mais. Use os insights para gestão e melhorias. "
    )

df_goto_raw = carregar_dados_goto()
df_multi360_raw = carregar_dados_multi360()
df_goto_agent_calls_raw = carregar_goto_agent_calls()

if df_goto_raw.empty and df_multi360_raw.empty:
    st.warning("⚠️ WikiSuporte - Nenhum atendimento encontrado no sistema ou falha de conexão.")
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

        datas_selecionadas = st.date_input("📅 Período (Abertura):", value=(data_inicial_padrao, data_final_padrao), max_value=datetime.now().date() + timedelta(days=1),format="DD/MM/YYYY")
        
    with col_f2:
        sla_finalizacao_horas = st.number_input("⏱️ Meta SLA WhatsApp (Horas):", value=24)
        
    with col_f3:
        st.write("") 
        st.write("")
        if st.button("🔄 Atualizar", width='stretch'):
            st.cache_data.clear()
            st.rerun()


# --- APLICAÇÃO DE FILTROS BÁSICOS (DATAS) ---
df_tel = df_goto_raw.copy()
df_wpp = df_multi360_raw.copy()
df_agent_calls_periodo = pd.DataFrame()
if len(datas_selecionadas) == 2:
    data_inicio, data_fim = datas_selecionadas
    data_fim_excl = pd.to_datetime(data_fim) + timedelta(days=1)
    data_inicio = pd.to_datetime(data_inicio)

    if not df_tel.empty:
        df_tel = df_tel[(df_tel['data_chamada'] >= data_inicio) & (df_tel['data_chamada'] < data_fim_excl)]
    if not df_wpp.empty:
        df_wpp = df_wpp[(df_wpp['data_inicio'] >= data_inicio) & (df_wpp['data_inicio'] < data_fim_excl)]
    if not df_goto_agent_calls_raw.empty and "contact_creation_time" in df_goto_agent_calls_raw.columns:
        df_agent_calls_periodo = df_goto_agent_calls_raw[
            (df_goto_agent_calls_raw["contact_creation_time"] >= data_inicio)
            & (df_goto_agent_calls_raw["contact_creation_time"] < data_fim_excl)
        ].copy()

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
    
    # Prevenção caso a variável sla_finalizacao_horas não venha do filtro
    sla_meta = locals().get('sla_finalizacao_horas', 24)
    df_wpp["DENTRO_SLA"] = df_wpp["TMA_HORAS"] <= sla_meta

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
coluna_agente_tel = None

def _obter_mapa_ramal_nome_goto():
    """Retorna dict ramal -> nome (exclui ramais ignorados e inclui rótulos especiais: Caixa Parado, Chamador, Jairo/TEF)."""
    mapa = {}
    try:
        engine = get_connection()
        df_u = pd.read_sql(
            text("SELECT nome, ramal FROM usuarios WHERE ramal IS NOT NULL AND TRIM(ramal) <> '' AND ativo = TRUE"),
            engine,
        )
        if not df_u.empty:
            for _, row in df_u.iterrows():
                r = str(row["ramal"]).strip()
                if r not in RAMAIS_EXCLUIR:
                    mapa[r] = str(row["nome"]).strip()
    except Exception:
        pass
    for ramal, nome in RAMAL_NOME_ESPECIAL.items():
        if ramal not in RAMAIS_EXCLUIR:
            mapa[str(ramal).strip()] = nome
    return mapa

if not df_tel.empty:
    colunas_lower = {str(c).lower(): c for c in df_tel.columns}
    col_part = next((c for c in colunas_lower.values() if 'participante' in c.lower()), None)

    # Ramal 5355: não considerar nem as ligações para ele (excluir das métricas)
    if col_part:
        mascara_5355 = df_tel[col_part].astype(str).str.contains("5355", regex=False, na=False)
        df_tel = df_tel[~mascara_5355].copy()

    if col_part:
        def is_ligacao_interna(valor):
            """
            Verifica se a string tem EXATAMENTE e APENAS o ramal repetido (ex: "5332: 5332").
            Ignora se houver qualquer outro número, cliente ou transferência depois.
            """
            if pd.isna(valor): return False
            
            # Limpa espaços e um possível ponto e vírgula esquecido no final
            texto_limpo = str(valor).strip().strip(';')
            
            # 1ª Regra de Segurança: Se tiver o separador de transferências (;), NÃO É caixa postal.
            if ';' in texto_limpo:
                return False
                
            # Divide o texto pelo sinal de dois pontos
            partes = [p.strip() for p in texto_limpo.split(':')]
            
            # 2ª Regra de Segurança: Tem que ter exatamente 2 partes, elas têm que ser IDÊNTICAS, 
            # ser compostas só de números, e ter 4 dígitos (formato de ramal).
            if len(partes) == 2 and partes[0] == partes[1] and partes[0].isdigit() and len(partes[0]) == 4:
                return True
                
            return False

        # Aplica a função linha por linha de forma 100% segura
        mascara_caixa_postal = df_tel[col_part].apply(is_ligacao_interna)
        
        # O símbolo (~) inverte a máscara: Mantém na tabela apenas o que NÃO é ligação interna
        df_tel = df_tel[~mascara_caixa_postal].copy()

    # Só continua o cálculo de UX e KPIs se a tabela não ficar vazia após o filtro
    if not df_tel.empty:
        df_tel['DIA'] = df_tel['data_chamada'].dt.date
        
        # 1. Ajuste do Tempo: Milissegundos para Minutos
        if 'duracao_ms' in colunas_lower:
            col_real_tempo = colunas_lower['duracao_ms']
            df_tel['duracao_ms_val'] = pd.to_numeric(df_tel[col_real_tempo], errors='coerce').fillna(0)
            df_tel['duracao_minutos'] = df_tel['duracao_ms_val'] / 60000.0
        elif 'duracao' in colunas_lower:
            col_real_tempo = colunas_lower['duracao']
            df_tel['duracao_ms_val'] = pd.to_numeric(df_tel[col_real_tempo], errors='coerce').fillna(0)
            df_tel['duracao_minutos'] = df_tel['duracao_ms_val'] / 60000.0
        else:
            df_tel['duracao_ms_val'] = 0.0
            df_tel['duracao_minutos'] = 0.0
            
        # 2. TRADUTOR DE STATUS (UX) - Classificação correta por resultado da chamada (GoTo)
        # Atendida = "Encerrada com sucesso" ou "Chamada do plano de discagem encerrada"
        # Perdida = "Chamada perdida" (não atendida no ramal)
        # Abandonada na URA = desistiu no menu (sem encerrada); demais = Falha/Outros
        if 'resultado' in colunas_lower:
            col_res = colunas_lower['resultado']
            df_tel['resultado_upper'] = df_tel[col_res].fillna("").astype(str).str.upper().str.strip()

            LIMITE_MS = 5 * 60 * 1000  # 5 minutos em ms (fallback quando resultado não é reconhecido)

            def categorizar_chamada(row):
                status = row['resultado_upper']
                dur_ms = row.get('duracao_ms_val', 0)

                if "CHAMADA PERDIDA" in status:
                    return "Perdida (Tocou no Ramal)"
                if "COMPLETED" in status or "ENCERRADA COM SUCESSO" in status:
                    return "Atendida"
                # "Chamada do plano de discagem encerrada" = ligação atendida e encerrada (não é abandono)
                if "PLANO DE DISCAGEM" in status and "ENCERRADA" in status:
                    return "Atendida"
                if "PLANO DE DISCAGEM" in status:
                    return "Abandonada na URA"
                if "INDETERMINADO" in status or "CANCELADA" in status:
                    return "Falha Técnica / Cancelada"

                # Fallback: por duração (quando resultado não é um dos textos conhecidos)
                if dur_ms <= LIMITE_MS:
                    return "Perdida (Tocou no Ramal)"
                return "Atendida"

            df_tel['Categoria_UX'] = df_tel.apply(categorizar_chamada, axis=1)
        else:
            df_tel['Categoria_UX'] = "Não Informado"
            
        df_tel['Is_Atendida'] = (df_tel['Categoria_UX'] == "Atendida").astype(int)
        df_tel['Is_Perdida_Ramal'] = (df_tel['Categoria_UX'] == "Perdida (Tocou no Ramal)").astype(int)

        # 3. Agente principal: usar coluna do banco ou inferir a partir de participantes (ramal)
        col_part = next((c for c in colunas_lower.values() if 'participante' in c.lower()), None)
        if 'nome_analista_epsy' in colunas_lower:
            coluna_agente_tel = colunas_lower['nome_analista_epsy']
        elif 'usuario' in colunas_lower:
            coluna_agente_tel = colunas_lower['usuario']
        else:
            coluna_agente_tel = None
        # Se a coluna existe mas está vazia, ou não existe: preencher a partir de participantes
        if col_part and (coluna_agente_tel is None or df_tel[coluna_agente_tel].fillna("").astype(str).str.strip().eq("").all()):
            mapa_ramal = _obter_mapa_ramal_nome_goto()
            if mapa_ramal:
                def _analista_de_participantes(row):
                    texto = str(row.get(col_part, "")) + " " + str(row.get("telefone_origem", "")) if "telefone_origem" in df_tel.columns else str(row.get(col_part, ""))
                    for ramal, nome in mapa_ramal.items():
                        if ramal and ramal in texto:
                            return nome
                    return "Não Identificado"
                if coluna_agente_tel is None:
                    df_tel["nome_analista_epsy"] = df_tel.apply(_analista_de_participantes, axis=1)
                    coluna_agente_tel = "nome_analista_epsy"
                    colunas_lower["nome_analista_epsy"] = "nome_analista_epsy"
                else:
                    vazios = df_tel[coluna_agente_tel].fillna("").astype(str).str.strip().eq("")
                    df_tel.loc[vazios, coluna_agente_tel] = df_tel.loc[vazios].apply(_analista_de_participantes, axis=1)
        if coluna_agente_tel:
            df_tel[coluna_agente_tel] = df_tel[coluna_agente_tel].fillna("Não Identificado")
        # Setor (TEF x Suporte Geral) para cada linha
        mapa_ramal = _obter_mapa_ramal_nome_goto()
        if coluna_agente_tel and mapa_ramal:
            df_tel["setor_epsy"] = df_tel[coluna_agente_tel].apply(
                lambda nome: obter_setor_por_nome_analista(nome, mapa_ramal)
            )
        else:
            df_tel["setor_epsy"] = SETOR_SUPORTE_GERAL

# ==========================================
# 5. CONSTRUÇÃO DAS ABAS PRINCIPAIS (UX/UI)
# ==========================================
aba_geral, aba_wpp, aba_telefonia = st.tabs(["Visão Unificada", "WhatsApp (Multi360)", "Ligações (GoTo)"])

# ------------------------------------------
# ABA 1: VISÃO UNIFICADA (GERAL)
# ------------------------------------------
with aba_geral:
    st.markdown("### 📈 Resumo de Atendimentos - GoTo e WhatsApp")
    st.caption("Volume total de atendimentos, proporção entre GoTo e Multi360.")
    
    vol_wpp = len(df_wpp) if 'df_wpp' in locals() else 0
    vol_tel = len(df_tel) if 'df_tel' in locals() else 0
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
    
    tma_wpp_min = df_wpp['TMA_HORAS'].mean() * 60 if ('df_wpp' in locals() and not df_wpp.empty and 'TMA_HORAS' in df_wpp.columns) else 0
    tma_tel_min = df_tel['duracao_minutos'].mean() if ('df_tel' in locals() and not df_tel.empty and 'duracao_minutos' in df_tel.columns) else 0
    
    with st.container(border=True):
        c4.metric("Duração Média (Telefone)", f"{tma_tel_min:.1f} min", "Tempo na linha")

    st.divider()
    
    if total_interacoes > 0:
        g1, g2 = st.columns([1.5, 2.5])
        
    with g1:
        st.markdown("#### 📊 Proporção de Atendimentos por Canal")
        df_omni = pd.DataFrame(
            {"Canal": ["WhatsApp", "Telefone"], "Volume": [vol_wpp, vol_tel]}
        )

        # Gráfico em barras horizontais para melhor leitura em telas largas/estreitas
        fig_omni = px.bar(
            df_omni,
            x="Volume",
            y="Canal",
            orientation="h",
            text="Volume",
            color="Canal",
            color_discrete_map={"WhatsApp": "#25D366", "Telefone": "#007BFF"},
        )

        fig_omni.update_traces(
            texttemplate="%{text:,}",
            textposition="outside",
            cliponaxis=False,
            marker=dict(line=dict(color="rgba(0,0,0,0.08)", width=1), opacity=0.92),
        )
        fig_omni.update_layout(
            xaxis_title="Volume de atendimentos",
            yaxis_title="",
            bargap=0.25,
            margin=dict(t=20, b=20, l=10, r=20),
            showlegend=False,
            height=280,
        )
        st.plotly_chart(fig_omni, use_container_width='stretch')
        st.caption(
            "A visualização mostra a distribuição dos atendimentos entre os canais."
        )
            
        with g2:
            st.markdown("#### 📈 Tendência Diária de Atendimentos")
            trends = []
            
            if 'df_wpp' in locals() and not df_wpp.empty and 'DIA' in df_wpp.columns:
                wpp_trend = df_wpp['DIA'].value_counts().reset_index()
                wpp_trend.columns = ['Data', 'Volume']
                wpp_trend['Canal'] = 'WhatsApp'
                trends.append(wpp_trend)
                
            if 'df_tel' in locals() and not df_tel.empty and 'DIA' in df_tel.columns:
                tel_trend = df_tel['DIA'].value_counts().reset_index()
                tel_trend.columns = ['Data', 'Volume']
                tel_trend['Canal'] = 'Telefone'
                trends.append(tel_trend)
                
            if trends:
                df_trend = pd.concat(trends)
                fig_trend = px.area(df_trend, x='Data', y='Volume', color='Canal', color_discrete_map={"WhatsApp": "#25D366", "Telefone": "#007BFF"})
                fig_trend.update_layout(margin=dict(t=20, b=0, l=0, r=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_trend, width='stretch')
                st.caption("Acompanhe a evolução diária dos atendimentos em cada canal para identificar picos e sazonalidades.")

# ------------------------------------------
# ABA 2: MULTI360 (WHATSAPP)
# ------------------------------------------
with aba_wpp:
    if 'df_wpp' not in locals() or df_wpp.empty or 'TMA_HORAS' not in df_wpp.columns:
        st.info("Nenhum dado válido do WhatsApp (Multi360) importado para o período selecionado.")
    else:
        sub_exec, sub_indiv, sub_qual, sub_oper, sub_estrat = st.tabs(["📌 Resumo da Operação", "👤 Análise por Atendente", "⭐ Notas e Qualidade", "⚙️ Horários de Pico", "📊 Carga de Trabalho"])

        with sub_exec:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total de Conversas", len(df_wpp))
            col2.metric("Tempo Médio (TMA)", f"{round(df_wpp['TMA_HORAS'].mean(), 1)} Horas")
            col3.metric("No Prazo Ideal (SLA)", f"{round(df_wpp['DENTRO_SLA'].mean()*100, 1)}%" if 'DENTRO_SLA' in df_wpp.columns else "N/A")
            col4.metric("Nota Média dos Clientes", round(df_wpp["avaliacao"].mean(), 2) if 'avaliacao' in df_wpp.columns else "N/A")

            st.divider()
            col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("#### 📈 Performance e Volume Diário")
            
            # 1. Preparação dos dados: Média e Contagem no mesmo agrupamento
            resumo_diario = df_wpp.groupby("DIA").agg(
                TMA_medio=("TMA_HORAS", "mean"),
                Quantidade=("TMA_HORAS", "count")
            ).reset_index()
            
            # 2. Criar gráfico com dois eixos
            from plotly.subplots import make_subplots
            import plotly.graph_objects as go

            fig_misto = make_subplots(specs=[[{"secondary_y": True}]])

            # Adiciona Volume (Barras) - Eixo Principal (Esquerda)
            fig_misto.add_trace(
                go.Bar(
                    x=resumo_diario["DIA"], 
                    y=resumo_diario["Quantidade"],
                    name="Qtd. Atendimentos",
                    marker_color='#D1FAE5', # Verde bem claro para não ofuscar a linha
                    hovertemplate="Volume: %{y}<extra></extra>"
                ),
                secondary_y=False,
            )

            # Adiciona TMA (Linha) - Eixo Secundário (Direita)
            fig_misto.add_trace(
                go.Scatter(
                    x=resumo_diario["DIA"], 
                    y=resumo_diario["TMA_medio"],
                    name="Tempo Médio (h)",
                    mode="lines+markers+text",
                    text=resumo_diario["TMA_medio"].round(1),
                    textposition="top center",
                    line=dict(color='#25D366', width=3), # Verde WhatsApp forte
                    hovertemplate="Média: %{y:.2f}h<extra></extra>"
                ),
                secondary_y=True,
            )

            # 3. Ajustes de Layout e Nomes Claros
            fig_misto.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )

            fig_misto.update_yaxes(title_text="Volume de Chats", secondary_y=False)
            fig_misto.update_yaxes(title_text="Tempo Médio (h)", secondary_y=True)

            st.plotly_chart(fig_misto, use_container_width='stretch')
            st.caption("As barras mostram o **volume** total e a linha indica a **agilidade**. Analise picos de volume que causam aumento no tempo de resposta.")


        with col_g2:
                if 'DIA_SEMANA' in df_wpp.columns and 'HORA' in df_wpp.columns:
                    st.markdown("#### 📅 Mapa de Calor: Concentração de Atendimentos")
                    
                    # 1. Preparação dos dados
                    heatmap = df_wpp.pivot_table(index="DIA_SEMANA", columns="HORA", values="TMA_HORAS", aggfunc="count").fillna(0)
                    dias_ordem = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    heatmap = heatmap.reindex([d for d in dias_ordem if d in heatmap.index])
                    
                    # Tradução dos índices para o Gestor
                    dias_pt = {'Monday':'Segunda', 'Tuesday':'Terça', 'Wednesday':'Quarta', 'Thursday':'Quinta', 'Friday':'Sexta', 'Saturday':'Sábado', 'Sunday':'Domingo'}
                    heatmap.index = heatmap.index.map(dias_pt)

                    # 2. Criação do Gráfico com Plotly
                    fig_heat = px.imshow(
                        heatmap, 
                        aspect="auto", 
                        color_continuous_scale='YlOrRd', # Amarelo -> Laranja -> Vermelho (mais intuitivo)
                        labels=dict(x="Hora do Dia", y="Dia da Semana", color="Qtd. Atendimentos"),
                        text_auto=True # Mostra o número dentro do quadrado se houver espaço
                    )

                    # 3. Refinamento de Layout (UX)
                    fig_heat.update_layout(
                        xaxis_nticks=24, # Garante que mostre as 24h se houver dados
                        margin=dict(t=10, b=10, l=10, r=10),
                        coloraxis_showscale=False # Remove a barra lateral para limpar o visual se preferir
                    )
                    
                    st.plotly_chart(fig_heat, use_container_width='stretch')
                    st.info("💡 **Dica de Gestão:** Áreas em vermelho indicam picos de atendimento.")

with sub_indiv:
    if 'atendente' in df_wpp.columns:
        # 1. Preparação da lista e filtro
        atendentes_lista = sorted(df_wpp["atendente"].dropna().unique().tolist())
        
        if atendentes_lista:
            st.markdown("### 👤 Painel de Performance Individual")
            atendente = st.selectbox("Selecione o Analista para análise detalhada:", atendentes_lista)
            
            # Filtra os dados do atendente selecionado
            df_at = df_wpp[df_wpp["atendente"] == atendente]

            # 2. Bloco de Indicadores Principais (KPIs)
            with st.container(border=True):
                c_at1, c_at2, c_at3, c_at4 = st.columns(4)
                
                # Cálculos comparativos para Contexto (UX)
                media_geral_tma = df_wpp['TMA_HORAS'].mean()
                tma_individuo = df_at['TMA_HORAS'].mean()
                diff_percentual = ((tma_individuo / media_geral_tma) - 1) * 100  # Diferença vs equipe

                c_at1.metric(
                    label="Chats Finalizados", 
                    value=len(df_at),
                    help="Total de atendimentos atribuídos a este analista no período."
                )

                c_at2.metric(
                    label="Tempo Médio (TMA)", 
                    value=f"{tma_individuo:.1f}h", 
                    delta=f"{diff_percentual:.1f}% vs Equipe", 
                    delta_color="inverse",
                    help="Tempo médio que o analista leva para encerrar um chat. Menos tempo indica mais agilidade."
                )
                
                tempo_ocioso = df_at['TEMPO_OCIOSO_HORAS'].mean() if 'TEMPO_OCIOSO_HORAS' in df_at.columns else 0
                c_at3.metric(
                    label="Espera do Cliente", 
                    value=f"{tempo_ocioso:.1f}h",
                    help="Média de tempo que o cliente aguardou sem resposta após a última interação."
                )
                
                if 'score_df' in locals() and atendente in score_df.index:
                    pontuacao = score_df.loc[atendente]["Score"] * 100
                    c_at4.metric(
                        label="Índice de Qualidade", 
                        value=f"{pontuacao:.0f} pts",
                        help="Nota composta baseada em volume, agilidade e avaliações (0 a 100)."
                    )

            # 3. Bloco de Gráficos (Análise de Tendência e Satisfação)
            col_esq, col_dir = st.columns(2)
            
            with col_esq:
                st.markdown("#### 📈 Evolução de Produtividade")
                if 'MES' in df_at.columns:
                    prod_mensal = (
                        df_at.groupby("MES")
                        .size()
                        .reset_index(name="Volume")
                        .sort_values("MES")
                    )
                    fig_prod = px.line(
                        prod_mensal,
                        x="MES",
                        y="Volume",
                        markers=True,
                        color_discrete_sequence=['#25D366'],
                        labels={"MES": "Mês", "Volume": "Qtd. Chats"}
                    )
                    fig_prod.update_traces(marker=dict(size=8, line=dict(width=1, color="#0F5132")))
                    fig_prod.update_layout(
                        margin=dict(t=10, b=10, l=10, r=10),
                        height=320,
                        xaxis_title=None,
                        yaxis_title=None,
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_prod, use_container_width='stretch')
                    st.caption("Histórico mensal de atendimentos realizados.")

            with col_dir:
                st.markdown("#### ⭐ Satisfação do Cliente (CSAT)")
                if 'avaliacao' in df_at.columns:
                    # Conta a frequência de cada nota (1 a 5) com nomes de colunas únicos
                    notas_counts = (
                        df_at['avaliacao']
                        .value_counts()
                        .sort_index()
                        .reset_index(name="Frequência")
                        .rename(columns={"index": "avaliacao"})
                    )

                    fig_notas = px.bar(
                        notas_counts,
                        y="avaliacao",
                        x="Frequência",
                        orientation="h",  # barras horizontais para melhor leitura
                        color_discrete_sequence=['#FFC107'],
                        labels={"avaliacao": "Nota Recebida", "Frequência": "Frequência"}
                    )
                    fig_notas.update_traces(
                        texttemplate="%{x}",
                        textposition="outside",
                        marker=dict(line=dict(color="rgba(0,0,0,0.08)", width=1), opacity=0.9)
                    )
                    fig_notas.update_layout(
                        margin=dict(t=10, b=10, l=10, r=20),
                        height=320,
                        xaxis_title="Frequência",
                        yaxis_title=None
                    )
                    st.plotly_chart(fig_notas, use_container_width='stretch')
                    st.caption("Distribuição das notas dadas pelos clientes ao fim do chat.")

            # 4. Tabela de Casos Críticos (Ação Imediata)
            
                    st.markdown("#### 🚨 Top 5 Atendimentos com Maior Demora (Gargalos)")

                    casos_criticos = df_at.nlargest(5, 'TMA_HORAS')[['atendente', 'data_inicio', 'status', 'TMA_HORAS']]
                    casos_criticos.columns = ['Analista Responsável', 'Início do Chamado', 'Status Atual', 'Tempo Total (Horas)']

                    st.dataframe(
                        casos_criticos.style.format({'Tempo Total (Horas)': '{:.1f}h'}),
                        use_container_width='strech',
                        hide_index=True
                    )

                    st.caption("Esta lista destaca os atendimentos que mais impactaram negativamente a média de agilidade deste analista.")


with sub_qual:
    if 'avaliacao' in df_wpp.columns and 'atendente' in df_wpp.columns:
        st.markdown("### ⭐ Qualidade e Satisfação (Score de Satisfação do Cliente - Escala 0-10)")
        
        # 1. Agrupamento com média e volume de amostragem
        ranking_nota = df_wpp.groupby("atendente").agg(
            Media_Nota=("avaliacao", "mean"),
            Total_Votos=("avaliacao", "count")
        ).sort_values("Media_Nota", ascending=False).reset_index()

        col_q1, col_q2 = st.columns([1, 1.5])
        
        with col_q1:
            st.markdown("#### 🏆 Ranking de Notas")
            # UX: Background gradient calibrado para escala 10 (Vermelho a Verde)
            st.dataframe(
                ranking_nota.style.format({'Media_Nota': "{:.1f}"})
                .background_gradient(subset=['Media_Nota'], cmap='RdYlGn', vmin=0, vmax=10),
                use_container_width='stretch', 
                hide_index=True,
                column_config={
                    "atendente": "Analista",
                    "Media_Nota": "Nota Média (0-10)",
                    "Total_Votos": "Avaliações"
                }
            )
            st.caption("💡 O gradiente de cor destaca quem está mais próximo da nota máxima (10.0).")

        with col_q2:
            # 2. Gráfico Horizontal com limite fixo em 10
            fig_rank_notas = px.bar(
                ranking_nota, 
                x="Media_Nota", 
                y="atendente", 
                orientation='h',
                text_auto='.1f',
                color='Media_Nota',
                # Escala de cores divergente para destacar notas baixas vs altas
                color_continuous_scale='RdYlGn', 
                range_x=[0, 11], # Margem extra para o texto da nota não cortar
                labels={"Media_Nota": "Nota Média", "atendente": "Analista"}
            )
            
            fig_rank_notas.update_layout(
                title="Performance de Atendimento por Analista",
                yaxis={'categoryorder':'total ascending'}, 
                margin=dict(t=40, b=0, l=0, r=0),
                coloraxis_showscale=False,
                xaxis=dict(tickmode='linear', tick0=0, dtick=2) # Eixo X marcando de 2 em 2 até 10
            )
            
            st.plotly_chart(fig_rank_notas, use_container_width='stretch')

        # 3. Widget de Insight de Gestão
        media_equipe = df_wpp['avaliacao'].mean()
        # UX: Feedback visual baseado na média (Se média < 7, alerta amarelo)
        tipo_alerta = "info" if media_equipe >= 7 else "warning"
        
        st.write("---")
        if tipo_alerta == "info":
            st.info(f"✅ **Média Geral da Equipe:** {media_equipe:.1f} / 10.0. Avaliação geral está boa, continue monitorando para manter a qualidade.")
        else:
            st.warning(f"⚠️ **Atenção:** Média da equipe está em {media_equipe:.1f} / 10.0. Considere investigar os fatores que estão impactando a satisfação do cliente e implementar ações de melhoria.")


    with sub_oper:
        st.markdown("### ⚙️ Eficiência e Gargalos Operacionais")
        
        co1, co2 = st.columns(2)
        
        with co1:
            if 'HORA' in df_wpp.columns:
                st.markdown("#### 🕒 Pico de Demanda (Por Hora)")
                # Agrupamento e preparação
                vol_hora = df_wpp.groupby("HORA").size().reset_index(name="Volume")
                
                # UX: Gráfico de área/linha costuma ser melhor para séries temporais contínuas (horas)
                fig_hora = px.area(
                    vol_hora, x="HORA", y="Volume", 
                    color_discrete_sequence=['#007BFF'],
                    markers=True,
                    labels={"HORA": "Hora do Dia", "Volume": "Qtd. Atendimentos"}
                )
                
                fig_hora.update_layout(
                    margin=dict(t=10, b=10, l=10, r=10),
                    xaxis=dict(tickmode='linear', tick0=0, dtick=2), # Mostra 0h, 2h, 4h...
                    hovermode="x unified"
                )
                
                st.plotly_chart(fig_hora, use_container_width='stretch')
                st.caption("🔍 **Insight:** Identifique os horários com maior demanda.")

        with co2:
            st.markdown("#### ⏳ Análise de Tempo de Atendimento (Tempo Médio por Atendimento - TMA)")
            # UX: Ajuste de bins para não poluir e foco no 'Grosso' da operação
            fig_hist_tma = px.histogram(
                df_wpp, x="TMA_HORAS", 
                nbins=30, 
                color_discrete_sequence=['#EF553B'],
                labels={"TMA_HORAS": "Duração (Horas)", "count": "Frequência"}
            )
            
            # Adiciona uma linha vertical com a mediana (UX: A mediana é mais "real" que a média em histogramas)
            mediana_tma = df_wpp["TMA_HORAS"].median()
            fig_hist_tma.add_vline(x=mediana_tma, line_dash="dash", line_color="black", 
                                    annotation_text=f"Mediana: {mediana_tma:.1f}h")

            fig_hist_tma.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                xaxis_title="Horas para Finalizar", 
                yaxis_title="Volume de Chamados",
                bargap=0.1
            )
            
            st.plotly_chart(fig_hist_tma, use_container_width= 'stretch')
            st.caption("💡 **Análise:** Se a curva se estende à direita, indica casos complexos que demoram mais para serem resolvidos e atrasam a fila.")

        # --- MÉTRICA DE CONCLUSÃO RÁPIDA (UX: O "Pulo do Gato" para o Gestor) ---
        atendimentos_rapidos = (df_wpp["TMA_HORAS"] <= 1).mean() * 100
        st.info(f"🚀 **Agilidade de Primeiro Nível:** {atendimentos_rapidos:.1f}% dos atendimentos do suporte são resolvidos em **menos de 1 hora**.")


    with sub_estrat:
        st.markdown("### 📊 Visão Estratégica: Departamentos e Produtividade")
        
        ce1, ce2 = st.columns(2)
    
    with ce1:
        if "departamento" in df_wpp.columns:
            st.markdown("#### 🏢 Agilidade por Departamento")
            # Agrupamento e ordenação (Menor tempo = Melhor performance no topo)
            dept = df_wpp.groupby("departamento")["TMA_HORAS"].mean().reset_index().sort_values('TMA_HORAS', ascending=True)
            
            fig_dept = px.bar(
                dept, 
                x="TMA_HORAS", 
                y="departamento", 
                orientation='h', 
                text_auto='.1f',
                color='TMA_HORAS', 
                color_continuous_scale='Reds', # Vermelho indica "alerta" para tempos altos
                labels={"TMA_HORAS": "Tempo Médio (h)", "departamento": "Departamento"}
            )
            
            fig_dept.update_layout(
                margin=dict(t=30, b=10, l=10, r=10),
                coloraxis_showscale=False,
                xaxis_title="Duração Média (Horas)",
                yaxis_title=None
            )
            
            st.plotly_chart(fig_dept, use_container_width='stretch')
            st.caption("🚨 **Foco de Gestão:** Departamentos no final da lista possuem processos mais lentos ou maior complexidade.")

    with ce2:
        if 'atendente' in df_wpp.columns:
            st.markdown("#### 🏆 Top 10 Analistas (Volume)")
            # Curva de Pareto simplificada: quem carrega o maior volume?
            pareto = df_wpp["atendente"].value_counts().reset_index().head(10)
            pareto.columns = ["Analista", "Volume"]
            
            fig_pareto = px.bar(
                pareto, 
                x="Volume", # Inverti para horizontal (H) para facilitar leitura de nomes longos
                y="Analista", 
                orientation='h',
                text_auto=True,
                color='Volume', 
                color_continuous_scale='Purples', # Roxo transmite autoridade/importância
                labels={"Volume": "Qtd. Atendimentos", "Analista": "Analista"}
            )
            
            fig_pareto.update_layout(
                margin=dict(t=30, b=10, l=10, r=10),
                coloraxis_showscale=False,
                yaxis={'categoryorder':'total ascending'}, # O maior volume fica no topo
                xaxis_title="Total de Chats Concluídos",
                yaxis_title=None
            )
            
            st.plotly_chart(fig_pareto, use_container_width='stretch')
            st.caption("⭐ **Reconhecimento:** Estes são os analistas que processam a maior demanda da operação.")

    # --- INSIGHT ESTRATÉGICO FINAL ---
    if not df_wpp.empty:
        top_analista = pareto.iloc[0]["Analista"]
        vol_max = pareto.iloc[0]["Volume"]
        st.success(f"💡 **Destaque Operacional:** O analista **{top_analista}** é o mais produtivo do período, com **{vol_max}** atendimentos finalizados.")


# ------------------------------------------
# ABA 3: TELEFONIA (GOTO)
# ------------------------------------------
with aba_telefonia:
    if 'df_tel' not in locals() or df_tel.empty or 'duracao_minutos' not in df_tel.columns:
        st.info("Nenhum dado válido de ligações (GoTo) importado para o período selecionado.")
    else:
        tab_tel_geral, tab_tel_agentes = st.tabs(["📌 Resumo das Ligações", "👤 Desempenho dos Analistas"])
        
        with tab_tel_geral:
            st.markdown("### 📞 Dashboard de Ligações - GoTo")
            st.caption("Análise detalhada do fluxo de chamadas, status e comportamento dos clientes ao longo do tempo.")
            
            # Cálculos: quando há relatório Agent Calls no período, usá-lo para Atendidas (fonte fiel)
            vol_total = len(df_tel)
            if not df_agent_calls_periodo.empty:
                vol_atendidas = len(df_agent_calls_periodo)
                fonte_atendidas = " (relatório Agent Calls)"
            else:
                vol_atendidas = int(df_tel['Is_Atendida'].sum()) if 'Is_Atendida' in df_tel.columns else 0
                fonte_atendidas = ""
            vol_perdidas_ramal = int(df_tel['Is_Perdida_Ramal'].sum()) if 'Is_Perdida_Ramal' in df_tel.columns else 0
            vol_ura = len(df_tel[df_tel['Categoria_UX'] == "Abandonada na URA"]) if 'Categoria_UX' in df_tel.columns else 0
            vol_total_exib = vol_atendidas + vol_perdidas_ramal if not df_agent_calls_periodo.empty else vol_total

            with st.container(border=True):
                t_col1, t_col2, t_col3, t_col4 = st.columns(4)
                t_col1.metric("Total de Entradas", vol_total_exib, "Atendidas + Perdidas" if not df_agent_calls_periodo.empty else "No PABX")
                t_col2.metric("✅ Atendidas" + fonte_atendidas, vol_atendidas, f"{(vol_atendidas/vol_total_exib*100):.1f}%" if vol_total_exib > 0 else "0%", delta_color="normal")
                t_col3.metric("⚠️ Perdidas no Ramal", vol_perdidas_ramal, "Chamadas não atendidas", delta_color="inverse")
                t_col4.metric("🚪 Abandonadas na URA", vol_ura, "Desistiu no Menu", delta_color="inverse")
            
            st.divider()
            
            cg_tel1, cg_tel2 = st.columns([2, 1.5])
            
            with cg_tel1:
                if 'DIA' in df_tel.columns:
                    df_vol_dia_tel = df_tel['DIA'].value_counts().sort_index().reset_index()
                    df_vol_dia_tel.columns = ['Data', 'Volume']
                    fig_linha_tel = px.area(df_vol_dia_tel, x='Data', y='Volume', title="Fluxo Diário de Entradas", color_discrete_sequence=['#007BFF'])
                    fig_linha_tel.update_layout(margin=dict(t=30, b=0, l=0, r=0))
                    st.plotly_chart(fig_linha_tel, width='stretch')
            
            with cg_tel2:
                if 'Categoria_UX' in df_tel.columns:
                    df_status = df_tel['Categoria_UX'].value_counts().reset_index()
                    df_status.columns = ['Status', 'Quantidade']
                    df_status['Percentual'] = (
                        df_status['Quantidade'] / df_status['Quantidade'].sum() * 100
                    ).round(1)

                    # Paleta de cores semântica (Verde=Sucesso, Vermelho=Perdida, Laranja=URA, Cinza=Erro)
                    cores_status = {
                        "Atendida": "#25D366",
                        "Perdida (Tocou no Ramal)": "#EF553B",
                        "Abandonada na URA": "#FFA15A",
                        "Falha Técnica / Cancelada": "#B6E880",
                        "Outros": "#AB63FA",
                    }

                    fig_status = px.bar(
                        df_status,
                        y="Status",
                        x="Quantidade",
                        orientation="h",
                        color="Status",
                        color_discrete_map=cores_status,
                        text="Percentual",
                        title="Desfecho das Chamadas",
                        labels={"Quantidade": "Qtd. Chamadas", "Status": "Status"},
                    )
                    fig_status.update_traces(
                        texttemplate="%{text:.1f}%",
                        textposition="outside",
                        marker=dict(line=dict(color="rgba(0,0,0,0.08)", width=1), opacity=0.92),
                        cliponaxis=False,
                    )
                    fig_status.update_layout(
                        margin=dict(t=30, b=10, l=0, r=10),
                        height=320,
                        showlegend=False,
                    )
                    st.plotly_chart(fig_status, use_container_width='stretch')

        with tab_tel_agentes:
            if coluna_agente_tel:
                # Agrupamento: por analista e, se existir, por setor (TEF / Suporte Geral)
                cols_agrup = [coluna_agente_tel]
                if 'setor_epsy' in df_tel.columns:
                    cols_agrup = [coluna_agente_tel, 'setor_epsy']
                df_agentes_tel = df_tel.groupby(cols_agrup).agg(
                    Total_Direcionado=('DIA', 'count'),
                    Atendidas=('Is_Atendida', 'sum'),
                    Perdidas_Ramal=('Is_Perdida_Ramal', 'sum'),
                    TMA_Minutos=('duracao_minutos', 'mean'),
                    Tempo_Total_Minutos=('duracao_minutos', 'sum')
                ).reset_index().sort_values('Atendidas', ascending=False)
                
                # --- SEPARAÇÃO: rotas/sistema vs equipe real ---
                termos_sistema = ['Transferência', 'Ramal \\d', 'Sistema', 'Abandono', 'Retenção']
                mascara_sistema = df_agentes_tel[coluna_agente_tel].astype(str).str.contains('|'.join(termos_sistema), case=False, na=False, regex=True)
                
                df_equipe_real = df_agentes_tel[~mascara_sistema].copy()
                df_sistema_rotas = df_agentes_tel[mascara_sistema].copy()
                
                st.markdown("### 👤 Desempenho dos Analistas")
                st.caption("Visão isolada dos analistas por setor (TEF e Suporte Geral). Ligações para o ramal 5355 não são contabilizadas.")
                
                # Resumo por setor (TEF x Suporte Geral)
                if 'setor_epsy' in df_equipe_real.columns:
                    resumo_setor = df_equipe_real.groupby('setor_epsy').agg(
                        Chamadas=('Total_Direcionado', 'sum'),
                        Atendidas=('Atendidas', 'sum'),
                        Analistas=(coluna_agente_tel, 'nunique')
                    ).reset_index()
                    resumo_setor.columns = ['Setor', 'Chamadas direcionadas', 'Atendidas', 'Qtd. analistas']
                    st.markdown("#### 📂 Por setor")
                    st.dataframe(resumo_setor, hide_index=True, use_container_width=True)
                    st.divider()
                
                c_tel1, c_tel2 = st.columns(2)
                with c_tel1:
                    fig_tel_vol = px.bar(df_equipe_real.head(10), x='Atendidas', y=coluna_agente_tel, orientation='h', title="Top 10: Atendimentos Efetivos", color='Atendidas', color_continuous_scale='Blues')
                    fig_tel_vol.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, b=0, l=0, r=0))
                    st.plotly_chart(fig_tel_vol, width='stretch')
                with c_tel2:
                    df_perdidas = df_equipe_real.sort_values('Perdidas_Ramal', ascending=False).head(10)
                    fig_tel_perd = px.bar(df_perdidas, x='Perdidas_Ramal', y=coluna_agente_tel, orientation='h', title="🚨 Alerta: Chamadas Não Atendidas", color='Perdidas_Ramal', color_continuous_scale='Reds')
                    fig_tel_perd.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(t=30, b=0, l=0, r=0))
                    st.plotly_chart(fig_tel_perd, width='stretch')
                
                st.markdown("#### 📋 Produtividade por Analista")
                df_exibicao_equipe = df_equipe_real.rename(columns={
                    coluna_agente_tel: "Analista", 
                    "Total_Direcionado": "Chamadas Direcionadas",
                    "Atendidas": "Atendimentos Efetivos",
                    "Perdidas_Ramal": "Não Atendeu (Perdidas)",
                    "TMA_Minutos": "Duração Média (Min)", 
                    "Tempo_Total_Minutos": "Horas Totais na Linha"
                })
                if 'setor_epsy' in df_exibicao_equipe.columns:
                    df_exibicao_equipe = df_exibicao_equipe.rename(columns={'setor_epsy': 'Setor'})
                df_exibicao_equipe['Horas Totais na Linha'] = df_exibicao_equipe['Horas Totais na Linha'] / 60
                
                st.dataframe(df_exibicao_equipe.style.format({
                    'Duração Média (Min)': "{:.1f}", 
                    'Horas Totais na Linha': "{:.1f}h"
                }).background_gradient(subset=['Não Atendeu (Perdidas)'], cmap='Reds'), width='stretch', hide_index=True)

                # ----------------------------------------------------
                # BLOCO 2: APENAS SISTEMA E TRANSFERÊNCIAS
                # ----------------------------------------------------
                if not df_sistema_rotas.empty:
                    st.divider()
                    st.markdown("### 🔄 Monitoramento de Transferências e Sistema")
                    st.caption("Volume de chamadas que ficaram no limbo de transferências, caíram na URA ou tocaram em ramais em análise.")
                    
                    df_exibicao_rotas = df_sistema_rotas.rename(columns={
                        coluna_agente_tel: "Origem / Status do Sistema", 
                        "Total_Direcionado": "Total de Registros"
                    })
                    
                    # Removi as colunas de TMA e Atendidas porque não fazem sentido para transferências
                    df_exibicao_rotas = df_exibicao_rotas[["Origem / Status do Sistema", "Total de Registros"]]
                    
                    st.dataframe(df_exibicao_rotas, width='stretch', hide_index=True)

            else:
                st.info("O sistema não conseguiu identificar o nome dos agentes no arquivo do GoTo.")

try:
    usuario_id = st.session_state.get("usuario_id", None)
    registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD", "Acessou o dashboard de atendimentos Multi360 e Goto")
except:
    pass