import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
import os
import logging
from dotenv import load_dotenv
from sqlalchemy import text
from typing import Tuple, Optional
from modules.database import get_connection
from services.db_homologacao import get_metricas_homologacao
from retry_requests import retry
from datetime import datetime, timedelta
from bs4 import BeautifulSoup




# ==========================================
# 1. SEGURANÇA E SESSÃO
# ==========================================

# Inicializa variáveis de estado da sessão para controle de login e histórico de notificações
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "notificacoes_lidas" not in st.session_state:
    st.session_state["notificacoes_lidas"] = []


st.set_page_config(
    page_title="Wiki-Suporte",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Cadeado: impede acesso direto sem login
if not st.session_state.get("autenticado", False):
    st.switch_page("app.py")

# ID do usuário logado (usado nos logs de auditoria)
usuario_id = st.session_state.get("usuario_id")

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
        except Exception:
            df = pd.read_sql("SELECT * FROM historico_interacoes", engine)
            
        if not df.empty and 'data_interacao' in df.columns:
            df['data_interacao'] = pd.to_datetime(df['data_interacao'], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def carregar_releases_chamados():
    """
    Carrega o número de releases em que cada chamado aparece.
    Usa a tabela de ligação oficial (chamados_corrigidos_releases) e
    faz fallback para release_chamados_correcao se necessário.
    """
    engine = get_connection()
    try:
        try:
            df_rel = pd.read_sql(
                """
                SELECT nr_chamado, COUNT(*) AS qtd_releases
                FROM chamados_corrigidos_releases
                GROUP BY nr_chamado
                """,
                engine,
            )
        except Exception:
            df_rel = pd.read_sql(
                """
                SELECT nr_chamado, COUNT(*) AS qtd_releases
                FROM release_chamados_correcao
                GROUP BY nr_chamado
                """,
                engine,
            )
        return df_rel
    except Exception:
        return pd.DataFrame(columns=["nr_chamado", "qtd_releases"])

def limpar_html(html_text):
    if not html_text or pd.isna(html_text):
        return ""
    soup = BeautifulSoup(str(html_text), "html.parser")
    texto = soup.get_text(separator=" ")
    return re.sub(r'\s+', ' ', texto).strip()


def extrair_versao_liberacao(texto: str) -> Optional[str]:
    """
    Tenta extrair o número da versão informada em uma mensagem de liberação.
    Ex.: 'Este chamado foi liberado em vers 3.1.4' -> '3.1.4'
    """
    if not texto:
        return None
    m = re.search(r"vers(?:ão)?\s*([\d\.]+)", texto, flags=re.IGNORECASE)
    return m.group(1) if m else None


def classificar_reincidencia_e_tempo(df_interacoes_chamado, data_abertura, status_atual):
    """
    Ajuste: só considera liberação quando a interação é da TecNuv (origem/usuario)
    e usa detectar_liberacao apenas dentro do loop de interações.
    """
    if df_interacoes_chamado.empty:
        return "Sem Liberação", pd.NaT

    df_ord = df_interacoes_chamado.sort_values("data_interacao").reset_index(drop=True)

    liberacao_idx = None
    data_primeira_liberacao = pd.NaT

    for idx, row in df_ord.iterrows():
        texto = limpar_html(row.get("descricao_html", ""))
        origem = (row.get("origem_interacao") or row.get("origem") or row.get("usuario") or "").lower()
        if "tecnuv" in origem and detectar_liberacao(texto):
            liberacao_idx = idx
            if pd.isna(data_primeira_liberacao):
                data_primeira_liberacao = row["data_interacao"]

    if liberacao_idx is None:
        return "Sem Liberação", pd.NaT

    posteriores = df_ord.iloc[liberacao_idx + 1 :]

    if posteriores.empty:
        classificacao = "Resolvido Pós-Liberação" if "encerrado" in str(status_atual).lower() else "Aguardando Validação EPSY"
    else:
        resolveu = posteriores["descricao_html"].fillna("").str.lower().str.contains("finaliza|encerr").any()
        classificacao = "Resolvido Pós-Liberação" if resolveu or "encerrado" in str(status_atual).lower() else "Reincidência"

    return classificacao, data_primeira_liberacao


def sincronizar_chamados(
    ids_helpdesk_abertos: list,
    ids_banco_abertos: list,
    buscar_interacoes_helpdesk,          # função externa que retorna lista/dict de interações
    buscar_status_finalizacao_helpdesk,  # função externa que retorna (status, data, usuario, mensagem)
):
    """
    Fluxo de sincronização resumido:
    - Compara sets de IDs abertos no helpdesk x banco.
    - Para cada diferença, busca interações e status final.
    - Marca liberações apenas se vierem da TecNuv e baterem com detectar_liberacao.
    """
    chamados_abertos_helpdesk = set(ids_helpdesk_abertos)
    chamados_abertos_banco = set(ids_banco_abertos)

    novos_abertos = chamados_abertos_helpdesk - chamados_abertos_banco
    fechados_no_helpdesk = chamados_abertos_banco - chamados_abertos_helpdesk

    resultados = {
        "novos_abertos": [],
        "fechados": [],
        "liberacoes": [],  # cada item: {id, data, versao, interacao_raw}
    }

    # Novos chamados detectados no helpdesk
    for cid in novos_abertos:
        interacoes = buscar_interacoes_helpdesk(cid)
        resultados["novos_abertos"].append({"id": cid, "interacoes": interacoes})

    # Chamados que fecharam no helpdesk
    for cid in fechados_no_helpdesk:
        status, dt_final, usuario_final, msg = buscar_status_finalizacao_helpdesk(cid)
        interacoes = buscar_interacoes_helpdesk(cid)
        resultados["fechados"].append(
            {
                "id": cid,
                "status": status,
                "data_finalizacao": dt_final,
                "usuario_finalizador": usuario_final,
                "mensagem_final": msg,
                "interacoes": interacoes,
            }
        )

    # Processa liberações em todos os chamados divergentes
    for cid in novos_abertos | fechados_no_helpdesk:
        interacoes = buscar_interacoes_helpdesk(cid)
        for interacao in interacoes:
            origem = (interacao.get("origem") or interacao.get("usuario") or "").lower()
            if "tecnuv" not in origem:
                continue
            texto = interacao.get("descricao_html", "")
            if detectar_liberacao(texto):
                resultados["liberacoes"].append(
                    {
                        "id": cid,
                        "data": interacao.get("data_interacao"),
                        "versao": extrair_versao_liberacao(texto),
                        "interacao_raw": interacao,
                    }
                )

    return resultados
# def detectar_liberacao(texto):
#     return re.search(r"Este chamado foi liberado em vers", texto, re.IGNORECASE) is not None

# def classificar_reincidencia_e_tempo(df_interacoes_chamado, data_abertura, status_atual):
#     if df_interacoes_chamado.empty:
#         return "Sem Liberação", pd.NaT

#     df_ord = df_interacoes_chamado.sort_values("data_interacao").reset_index(drop=True)
    
#     liberacao_idx = None
#     data_primeira_liberacao = pd.NaT
    
#     for idx, row in df_ord.iterrows():
#         texto = limpar_html(row.get("descricao_html", ""))
#         if detectar_liberacao(texto):
#             liberacao_idx = idx
#             if pd.isna(data_primeira_liberacao):
#                 data_primeira_liberacao = row['data_interacao']
    
#     if liberacao_idx is None:
#         return "Sem Liberação", pd.NaT

#     posteriores = df_ord.iloc[liberacao_idx + 1:]
    
#     if posteriores.empty:
#         if "Encerrado" in str(status_atual):
#             classificacao = "Resolvido Pós-Liberação"
#         else:
#             classificacao = "Aguardando Validação EPSY"
#     else:
#         resolveu = False
#         for _, row in posteriores.iterrows():
#             texto = limpar_html(row.get("descricao_html", ""))
#             if "finaliza" in texto.lower() or "encerr" in texto.lower():
#                 resolveu = True
#                 break
                
#         if resolveu or "Encerrado" in str(status_atual):
#             classificacao = "Resolvido Pós-Liberação"
#         else:
#             classificacao = "Reincidência"
            
#     return classificacao, data_primeira_liberacao

# ==========================================
# 3. INTERFACE E CARREGAMENTO
# ==========================================
st.title("🖥️ Dashboard Chamados")
st.markdown("Análise detalhada dos chamados, com foco em tempo de atendimento, reincidências e desempenho da desenvolvedora.")

df_raw = carregar_dados_tecnuv()
df_int = carregar_interacoes()
df_releases = carregar_releases_chamados()

if df_raw.empty:
    st.warning("WikiSuporte ainda não se conectou ao banco de dados. Entre em contato com o desenvolvedor para resolver o problema.")
    st.stop()

# ==========================================
# 4. PAINEL DE CONTROLO E FILTROS (NA TELA PRINCIPAL)
# ==========================================
with st.expander("⚙️ Filtros: ", expanded=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 1])
    
    with col_f1:
        # Período padrão: últimos 90 dias (para evitar carregar todo o histórico de uma vez)
        if not df_raw['data_abertura'].isna().all():
            data_max = df_raw['data_abertura'].max().date()
            data_min = df_raw['data_abertura'].min().date()
        else:
            data_max = datetime.now().date()
            data_min = (datetime.now() - timedelta(days=90)).date()

        default_inicio = max(data_min, data_max - timedelta(days=90))

        datas_selecionadas = st.date_input(
            "📅 Período (Abertura):",
            value=(default_inicio, data_max),
            max_value=datetime.now().date() + timedelta(days=1),
        )
        
    with col_f2:
        lista_analistas = ["Todos"] + sorted([a for a in df_raw['usuario_epsy'].unique() if a and str(a).strip() != "Não Informado"])
        analista_filtro = st.selectbox("👤 Analista EPSY:", options=lista_analistas, help="Lista com todos analistas")
        
    with col_f3:
        # Removido "Todos" para garantir que encerrados/cancelados só apareçam quando filtrados explicitamente
        lista_status = [
            "Chamados Ativos (Abertos)",
            "Encerrados",
            "Cancelados",
            "Encerrados ou Cancelados",
        ]
        status_filtro = st.selectbox("📌 Status do Chamado:", options=lista_status, index=0)
        
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

# Lógica de status: por padrão, apenas chamados ativos (abertos)
if status_filtro == "Chamados Ativos (Abertos)":
    df = df[~df['status_atual'].str.contains("Encerrado|Cancelado", case=False, na=False)]
elif status_filtro == "Encerrados":
    df = df[df['status_atual'].str.contains("Encerrado", case=False, na=False)]
elif status_filtro == "Cancelados":
    df = df[df['status_atual'].str.contains("Cancelado", case=False, na=False)]
elif status_filtro == "Encerrados ou Cancelados":
    df = df[df['status_atual'].str.contains("Encerrado|Cancelado", case=False, na=False)]

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

# 2. Reincidência e Tempo até Liberação (baseado em releases)
resultados_reincidencia = []
tempos_liberacao = []

# Mapa: nr_chamado -> quantidade de releases em que apareceu
map_releases = {}
if not df_releases.empty:
    map_releases = df_releases.set_index("nr_chamado")["qtd_releases"].to_dict()

for _, row in df.iterrows():
    nr = row['nr_chamado']
    status = row['status_atual']
    dt_abertura = row['data_abertura']
    
    interacoes_chamado = df_int[df_int['nr_chamado'] == nr] if not df_int.empty else pd.DataFrame()
    # Usa as interações apenas para medir tempo até a primeira liberação
    _, dt_primeira_lib = classificar_reincidencia_e_tempo(interacoes_chamado, dt_abertura, status)

    qtd_rel = int(map_releases.get(nr, 0) or 0)
    status_lower = str(status).lower()
    encerrado_ou_cancelado = "encerrado" in status_lower or "cancelado" in status_lower

    if qtd_rel == 0:
        classificacao = "Sem Liberação"
    else:
        if not encerrado_ou_cancelado:
            classificacao = "Aguardando Validação EPSY"
        else:
            if qtd_rel == 1:
                classificacao = "Resolvido Pós-Liberação"
            else:
                classificacao = "Reincidência"

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

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "🎯 Visão Geral",
    "⏳ Tempo de espera e gargalos nos chamados com a desenvolvedora.",
    "🐛 Detalhamento de Versões",
    "👥 Chamados por Analistas EPSY & Clientes",
    "📋 Qualidade de Homologação"
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
        # Calcular percentual para exibir nos textos das barras
        reinc_data["Percentual"] = (reinc_data["Volume"] / reinc_data["Volume"].sum() * 100).round(1)

        fig_reinc = px.bar(
            reinc_data,
            y="Classificação",
            x="Volume",
            orientation="h",
            color="Classificação",
            color_discrete_map={
                "Resolvido Pós-Liberação": "#25D366",
                "Reincidência": "#FF4B4B",
                "Aguardando Validação EPSY": "#FFA500",
                "Sem Liberação": "#808080"
            },
            text="Percentual"
        )
        fig_reinc.update_traces(
            texttemplate="%{text:.1f}%",
            textposition="outside",
            marker=dict(line=dict(color="rgba(0,0,0,0.08)", width=1), opacity=0.92),
            cliponaxis=False,
        )
        fig_reinc.update_layout(
            margin=dict(t=30, b=15, l=0, r=10),
            height=320,
            xaxis_title="Volume",
            yaxis_title=None,
            showlegend=False,
        )
        st.plotly_chart(fig_reinc, use_container_width=True)

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

# ------------------------------------------
# ABA 5: QUALIDADE DE HOMOLOGAÇÃO (ciclos_homologacao)
# ------------------------------------------
with aba5:
    st.subheader("📋 Métricas de Qualidade de Homologação")
    st.markdown("Indicadores baseados na tabela `ciclos_homologacao` (registo manual na Page 11 - Releases).")

    try:
        m = get_metricas_homologacao()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Taxa de Retrabalho Global",
            f"{m['taxa_retrabalho_global']:.1f}%",
            help="Percentual de ciclos marcados como Reprovado em relação ao total testado.",
        )
        col2.metric(
            "Gargalo de Homologação",
            m["gargalo_homologacao"],
            help="Quantidade de ciclos aguardando teste pelo suporte.",
        )
        col3.metric("Top Ofensores (chamados)", len(m["ranking_reincidencia"]))
        col4.metric("Módulos com Reprovações", len(m["vulnerabilidade_modulo"]))

        st.divider()

        r1, r2 = st.columns(2)
        with r1:
            st.markdown("#### 🔴 Ranking de Reincidência (Top Ofensores)")
            df_rank = m["ranking_reincidencia"]
            if df_rank.empty:
                st.info("Nenhum chamado com múltiplos ciclos ainda.")
            else:
                df_rank.columns = ["Chamado", "Qtd. Ciclos", "Reprovações"]
                st.dataframe(df_rank, hide_index=True, use_container_width=True)

        with r2:
            st.markdown("#### 📊 Vulnerabilidade por Módulo")
            df_mod = m["vulnerabilidade_modulo"]
            if df_mod.empty:
                st.info("Nenhuma reprovação registrada por módulo.")
            else:
                df_mod.columns = ["Módulo", "Reprovações"]
                st.dataframe(df_mod, hide_index=True, use_container_width=True)

    except Exception as e:
        st.warning(
            "As tabelas de homologação (`chamados`, `releases`, `ciclos_homologacao`) "
            "podem não existir ainda. Execute o script `database/migracao_ciclos_homologacao.sql`."
        )
        st.error(str(e))

registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD_CHAMADOS", "Acessou Dashboard Analítico - Chamados Tecnuv (EPSY)")