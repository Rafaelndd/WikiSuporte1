import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
import os
import logging
import unicodedata
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
# TTL curto: o bot grava no Postgres em tempo real; cache longo faz parecer que "não salvou"
@st.cache_data(ttl=45)
def carregar_dados_tecnuv():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM chamados_tecnuv", engine)
        if not df.empty:
            df['data_abertura'] = pd.to_datetime(df.get('data_abertura'), errors='coerce')
            df['data_encerramento'] = pd.to_datetime(df.get('data_encerramento'), errors='coerce')
            # usuario_epsy: fallback para nome_analista_epsy se a coluna não existir
            col_epsy = df.get("usuario_epsy") if "usuario_epsy" in df.columns else df.get("nome_analista_epsy", pd.Series(dtype=object))
            df["usuario_epsy"] = col_epsy.fillna("Não Informado").astype(str)
            df['atendente_tecnuv'] = df.get('atendente_tecnuv', pd.Series(dtype=str)).fillna("Não Informado")
            df['versao_sistema'] = df.get('versao_sistema', pd.Series(dtype=str)).fillna("Não Informada")
            # cliente_nome: enriquecer com clientes_vinculados_chamado quando vazio
            try:
                df_vinculos = pd.read_sql(
                    "SELECT nr_chamado, nome_cliente FROM clientes_vinculados_chamado",
                    engine,
                )
                if not df_vinculos.empty:
                    mapa_cliente = df_vinculos.set_index('nr_chamado')['nome_cliente'].to_dict()
                    def preencher_cliente(row):
                        val = row.get('cliente_nome')
                        if pd.isna(val) or not str(val).strip() or str(val).strip() in ("Não Informado", "Não Informada"):
                            return mapa_cliente.get(row['nr_chamado'], val)
                        return val
                    df['cliente_nome'] = df.apply(preencher_cliente, axis=1)
            except Exception:
                pass
            df["cliente_nome"] = df.get("cliente_nome", pd.Series(dtype=str)).fillna("Não Informado").astype(str)
            # Motivo/assunto: sempre texto limpo + Title Case na amostragem (colunas originais no DF para UI)
            for col in ("motivo_abertura_html", "assunto_html"):
                if col in df.columns:
                    df[col] = df[col].apply(limpar_html)
            df["erro_relatado"] = df.get("motivo_abertura_html", pd.Series(dtype=str)).apply(
                lambda x: x if isinstance(x, str) else limpar_html(x)
            )
            # categoria_ia (classificação semântica) se existir
            if 'categoria_ia' not in df.columns:
                df['categoria_ia'] = None
            st_col = df.get("status_atual", pd.Series("", index=df.index)).astype(str)
            df["status_norm"] = st_col.map(_normalize_status_key)
            df["status_canonico"] = st_col.map(status_para_canonico)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar chamados: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=45)
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


@st.cache_data(ttl=45)
def carregar_releases_chamados():
    """
    Quantas vezes o chamado apareceu em releases (release_itens ou ciclos_homologacao).
    """
    engine = get_connection()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM release_itens LIMIT 1"))
        df_rel = pd.read_sql(
            """
            SELECT nr_chamado, COUNT(DISTINCT id_release) AS qtd_releases
            FROM release_itens
            GROUP BY nr_chamado
            """,
            engine,
        )
        return df_rel
    except Exception:
        try:
            return pd.read_sql(
                """
                SELECT id_chamado::integer AS nr_chamado, COUNT(DISTINCT id_release) AS qtd_releases
                FROM ciclos_homologacao
                GROUP BY id_chamado
                """,
                engine,
            )
        except Exception:
            return pd.DataFrame(columns=["nr_chamado", "qtd_releases"])

# --- Status Tecnuv (amostragem alinhada ao Helpdesk; match case-insensitive / sem acento) ---
STATUS_DASHBOARD_LABELS = [
    "Em aberto",
    "Encerrado",
    "Cancelado",
    "Em analise",
    "Pendente representante",
    "Pendente tecnuv",
    "Em Desenvolvimento",
    "Em Fila de Desenvolvimento",
    "Em Andamento",
    "Aguardando Liberacao de Versao",
    "Aguardando Avaliacao",
    "Enviado Para Qualidade",
    "Retorno Qualidade",
    "Outros",
]
STATUS_COLOR_MAP = {
    "Em aberto": "#3498db",
    "Encerrado": "#27ae60",
    "Cancelado": "#7f8c8d",
    "Em analise": "#f39c12",
    "Pendente representante": "#e74c3c",
    "Pendente tecnuv": "#e67e22",
    "Em Desenvolvimento": "#8e44ad",
    "Em Fila de Desenvolvimento": "#6c3483",
    "Em Andamento": "#1abc9c",
    "Aguardando Liberacao de Versao": "#2980b9",
    "Aguardando Avaliacao": "#d35400",
    "Enviado Para Qualidade": "#16a085",
    "Retorno Qualidade": "#c0392b",
    "Outros": "#95a5a6",
}
# Ordem de match: frases mais específicas primeiro (substring no texto normalizado)
_STATUS_MATCH_RULES = [
    ("pendente representante", "Pendente representante"),
    ("pendente tecnuv", "Pendente tecnuv"),
    ("pendente tecnv", "Pendente tecnuv"),
    ("fila de desenvolvimento", "Em Fila de Desenvolvimento"),
    ("em desenvolvimento", "Em Desenvolvimento"),
    ("aguardando liberacao", "Aguardando Liberacao de Versao"),
    ("aguardando liberação", "Aguardando Liberacao de Versao"),
    ("aguardando avaliacao", "Aguardando Avaliacao"),
    ("aguardando avaliação", "Aguardando Avaliacao"),
    ("enviado para qualidade", "Enviado Para Qualidade"),
    ("retorno qualidade", "Retorno Qualidade"),
    ("em analise", "Em analise"),
    ("em análise", "Em analise"),
    ("em andamento", "Em Andamento"),
    ("encerrado", "Encerrado"),
    ("cancelado", "Cancelado"),
    ("em aberto", "Em aberto"),
    ("aberto", "Em aberto"),
]


def _normalize_status_key(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = unicodedata.normalize("NFD", str(s).strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def status_para_canonico(status_atual) -> str:
    """Uma etiqueta estável para gráficos/filtro, a partir de qualquer grafia do banco."""
    n = _normalize_status_key(status_atual)
    if not n:
        return "Outros"
    for needle, label in _STATUS_MATCH_RULES:
        if needle in n:
            return label
    return "Outros"


def limpar_html(html_text):
    """Compatível com código antigo; preferir modules.html_texto.html_para_exibicao."""
    try:
        from modules.html_texto import html_para_exibicao

        return html_para_exibicao(html_text, title_case=True)
    except Exception:
        if not html_text or pd.isna(html_text):
            return ""
        soup = BeautifulSoup(str(html_text), "html.parser")
        texto = soup.get_text(separator=" ")
        return re.sub(r"\s+", " ", texto).strip()


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
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "**Período padrão:** 12 meses. **Status padrão:** Pendente representante (multiselect). "
        "Status são unificados por texto (maiúsc/minúsc/acento). Cada **aba** traz fila, aging, versões, etc.\n\n"
        "**Após o bot sincronizar:** os dados vêm do Postgres, mas esta página usa **cache ~45s**. "
        "Se não vir mudança na hora, clique **🔄 Atualizar** nos filtros (limpa cache)."
    )

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
        # Período padrão: últimos 12 meses
        if not df_raw["data_abertura"].isna().all():
            data_max = df_raw["data_abertura"].max().date()
            data_min = df_raw["data_abertura"].min().date()
        else:
            data_max = datetime.now().date()
            data_min = (datetime.now() - timedelta(days=365)).date()

        default_inicio = max(data_min, data_max - timedelta(days=365))

        datas_selecionadas = st.date_input(
            "📅 Período (Abertura):",
            value=(default_inicio, data_max),
            max_value=datetime.now().date() + timedelta(days=1),
            help="Padrão: 12 meses até a data mais recente no banco.",
        )

    with col_f2:
        lista_analistas = ["Todos"] + sorted(
            [a for a in df_raw["usuario_epsy"].unique() if a and str(a).strip() != "Não Informado"]
        )
        analista_filtro = st.selectbox("👤 Analista EPSY:", options=lista_analistas, help="Lista com todos analistas")

    with col_f3:
        opcoes_status = [s for s in STATUS_DASHBOARD_LABELS if s != "Outros"]
        status_multiselect = st.multiselect(
            "📌 Status (canônico)",
            options=opcoes_status,
            default=["Pendente representante"],
            help="Só estes status entram na amostragem. Vazio = todos. Padrão: Pendente representante.",
        )
        
    with col_f4:
        st.write("")
        st.write("")
        if st.button("🔄 Atualizar", width='stretch', help="Limpa cache e relê o banco (use após o bot sincronizar)"):
            st.cache_data.clear()
            st.rerun()

# --- APLICAÇÃO DOS FILTROS ---
df = df_raw.copy()

if len(datas_selecionadas) == 2:
    d_inicio, d_fim = datas_selecionadas
    d_fim = pd.to_datetime(d_fim) + timedelta(days=1)
    df = df[(df['data_abertura'] >= pd.to_datetime(d_inicio)) & (df['data_abertura'] < d_fim)]

if analista_filtro != "Todos":
    df = df[df["usuario_epsy"] == analista_filtro]

if "status_canonico" in df.columns and status_multiselect:
    df = df[df["status_canonico"].isin(status_multiselect)]

if df.empty:
    st.info("Nenhum chamado encontrado com os filtros aplicados. Revise o período ou ajuste os critérios para refinar a busca.")
    st.stop()

# ==========================================
# 5. PROCESSAMENTO ESTRATÉGICO (MÉTRICAS)
# ==========================================
agora = pd.to_datetime(datetime.now())

# 1. Envelhecimento (Aging)
df['dias_aberto'] = (agora - df['data_abertura']).dt.days
if "status_canonico" in df.columns:
    df["is_aberto"] = ~df["status_canonico"].isin(["Encerrado", "Cancelado"])
else:
    df["is_aberto"] = ~df["status_atual"].str.contains("Encerrado|Cancelado", case=False, na=False)
# Pendente representante (situação no Helpdesk) — contagem de dias para cobrança/notificações
_sit = df.get("situacao", pd.Series("", index=df.index)).astype(str).str.lower()
df["pendente_representante"] = _sit.str.contains("pendente", na=False) & _sit.str.contains("representante", na=False)
df["dias_pendente_repr"] = np.where(
    df["pendente_representante"] & df["is_aberto"], df["dias_aberto"], np.nan
)

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

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs([
    "🎯 Visão Geral",
    "⏳ Tempo de espera e gargalos nos chamados com a desenvolvedora.",
    "🐛 Detalhamento de Versões",
    "👥 Chamados por Analistas EPSY & Clientes",
    "📋 Qualidade de Homologação",
    "📂 Fila aberta & releases",
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

    n_repr = int(df["pendente_representante"].sum())
    if n_repr > 0:
        st.warning(
            f"**{n_repr}** chamado(s) com situação **pendente representante** (média {df.loc[df['pendente_representante'], 'dias_aberto'].mean():.0f} dias abertos). "
            "Responsável e coordenador recebem aviso na **Home** ao citar em release e a cada **7 dias**."
        )
        with st.expander("Lista — pendente representante (dias)"):
            show = df[df["pendente_representante"]][
                ["nr_chamado", "usuario_epsy", "dias_aberto", "situacao", "status_atual"]
            ].sort_values("dias_aberto", ascending=False)
            st.dataframe(show, use_container_width=True, hide_index=True)

    st.divider()
    
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("Fila por status (canônico)")
        col_fila = "status_canonico" if "status_canonico" in df.columns else "status_atual"
        fila = df[col_fila].value_counts().reset_index()
        fila.columns = ["Status", "Volume"]
        cores = {k: STATUS_COLOR_MAP.get(k, "#95a5a6") for k in fila["Status"].unique()}
        fig_fila = px.bar(
            fila,
            x="Volume",
            y="Status",
            orientation="h",
            color="Status",
            color_discrete_map=cores,
        )
        fig_fila.update_layout(showlegend=False, height=min(420, 80 + len(fila) * 28))
        st.plotly_chart(fig_fila, width="stretch")
        
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
        st.plotly_chart(fig_reinc, use_container_width='stretch')

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
# ABA 3: VERSÕES — ABERTOS POR VERSÃO, CATEGORIAS, CONSULTA DE SEGURANÇA (sem gráfico pizza)
# ------------------------------------------
def _semver_tuple(v: str) -> tuple:
    if not v or not str(v).strip():
        return (0, 0, 0)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(v))
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (0, 0, 0)


# --- Versões “sistema” para listagem / consulta (exclui PDV Móvel e fora do padrão) ---
_RE_VERSAO_SISTEMA_PADRAO = re.compile(
    r"^\s*(?:V\s*)?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?\s*$",
    re.IGNORECASE,
)
# Referência: 24/11/2017 — V 1.06.27
_MIN_VERSAO_SISTEMA_TUPLE = (1, 6, 27, 0)
# Fallback até o bot gravar helpdesk_release_head (1º release da Home). .env opcional.
_DEFAULT_TETO_VERSAO_ATUAL = (2, 9, 257, 0)


def _tuple_versao_sistema_quatro(s: str) -> Optional[tuple]:
    """Extrai (major, minor, patch, build) se a string for só versão no padrão X.Y.Z ou X.Y.Z.N / V …"""
    if not s or not str(s).strip():
        return None
    m = _RE_VERSAO_SISTEMA_PADRAO.match(str(s).strip())
    if not m:
        return None
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4) or 0),
    )


def _versao_sistema_listagem_ok(
    texto_ou_versao: str,
    teto: Optional[tuple] = None,
) -> bool:
    """
    Válido para listagem / aba Versões:
    - Só padrão estrito: string inteira X.Y.Z ou X.Y.Z.N (V opcional), sem vírgulas, sem começar por "."
    - >= V 1.06.27; se teto informado, versão <= teto (nada acima da atual)
    - Rejeita PDV Móvel no texto
    """
    if not texto_ou_versao or not str(texto_ou_versao).strip():
        return False
    s = str(texto_ou_versao).strip()
    if "," in s or ";" in s:
        return False
    if s.startswith("."):
        return False
    low = s.lower()
    if "pdv móvel" in low or "pdv movel" in low:
        return False
    t = _tuple_versao_sistema_quatro(s)
    if t is None:
        return False
    if t < _MIN_VERSAO_SISTEMA_TUPLE:
        return False
    if teto is not None and t > teto:
        return False
    return True


def _teto_versao_atual_sistema() -> tuple:
    """
    Teto = versão atual do produto (último 1º release sincronizado pelo bot → helpdesk_release_head).
    1) Coluna versao_norm em helpdesk_release_head (após raspagem)
    2) .env VERSAO_ATUAL_SISTEMA (só comparação / até primeira sync)
    3) _DEFAULT_TETO_VERSAO_ATUAL
    """
    try:
        from modules.database import get_connection
        from sqlalchemy import text as sql_text

        with get_connection().connect() as c:
            row = c.execute(
                sql_text("SELECT versao_norm FROM helpdesk_release_head WHERE id = 1")
            ).fetchone()
        if row and (row[0] or "").strip():
            t = _tuple_versao_sistema_quatro(str(row[0]).strip())
            if t is not None and t >= _MIN_VERSAO_SISTEMA_TUPLE:
                return t
    except Exception:
        pass
    raw = (os.getenv("VERSAO_ATUAL_SISTEMA") or "").strip()
    if raw:
        t = _tuple_versao_sistema_quatro(raw)
        if t is not None and t >= _MIN_VERSAO_SISTEMA_TUPLE:
            return t
    return _DEFAULT_TETO_VERSAO_ATUAL


def _titulo_release_eh_pdv_movel(titulo: Optional[str]) -> bool:
    if not titulo:
        return False
    low = str(titulo).lower()
    return "pdv móvel" in low or "pdv movel" in low


def _status_aberto(st) -> bool:
    if pd.isna(st):
        return True
    s = str(st).lower()
    return "encerrado" not in s and "cancelado" not in s


def _eh_erro(cat) -> bool:
    c = str(cat or "").lower()
    return "erro" in c or "bug" in c or "falha" in c


def _eh_melhoria(cat) -> bool:
    return "melhoria" in str(cat or "").lower()


def _eh_fiscal(cat) -> bool:
    c = str(cat or "").lower()
    return "fiscal" in c or "adequa" in c or "sped" in c or "nfe" in c


with aba3:
    st.subheader("🐛 Versões do sistema — abertos, categorias e consulta de segurança")
    _teto_v = _teto_versao_atual_sistema()
    _ok_ver = lambda v: _versao_sistema_listagem_ok(v, teto=_teto_v)
    _teto_str = ".".join(str(x) for x in _teto_v[:3]) + (f".{_teto_v[3]}" if _teto_v[3] else "")
    st.caption(
        f"Somente versões no **padrão** (2.9.x), **sem vírgulas** nem **.** no início; "
        f"**teto = {_teto_str}** (último **1º release** sincronizado do Helpdesk; senão .env). "
        "**Erro ativo** / **Corrigido** / **release_itens** como antes."
    )

    dfv = df_raw.copy()
    bad_ver = {"não informada", "não informado", "", "nan", "none"}
    dfv["versao_sistema"] = dfv.get("versao_sistema", pd.Series(dtype=str)).astype(str).str.strip()
    dfv = dfv[~dfv["versao_sistema"].str.lower().isin(bad_ver)]
    # Normalização: só padrão estrito + até versão atual (teto)
    dfv = dfv[dfv["versao_sistema"].map(_ok_ver)]
    dfv["aberto"] = dfv["status_atual"].apply(_status_aberto)
    dfv["categoria_ia"] = dfv.get("categoria_ia", pd.Series(index=dfv.index, dtype=object)).fillna("Não classificada").astype(str)
    dfv["eh_erro"] = dfv["categoria_ia"].apply(_eh_erro)
    dfv["Resumo"] = dfv.get("erro_relatado", pd.Series(dtype=str)).fillna("").astype(str).str[:200]
    cn = dfv.get("cliente_nome", dfv.get("nome_cliente", pd.Series("", index=dfv.index)))
    dfv["Cliente"] = cn.astype(str).replace("", "Necessário cadastro")

    if dfv.empty:
        st.info(
            "Nenhum chamado com **versão_sistema** válida neste recorte (padrão X.Y.Z, sem vírgula, até a versão atual), "
            "ou nenhuma versão preenchida."
        )
    else:
        # --- 1) Todas as versões: total de ABERTOS por versão (ordenado semver) ---
        agg_abertos = (
            dfv[dfv["aberto"]]
            .groupby("versao_sistema", as_index=False)
            .agg(Chamados_abertos=("nr_chamado", "count"))
        )
        agg_total = dfv.groupby("versao_sistema", as_index=False).agg(Total_chamados=("nr_chamado", "count"))
        por_versao = agg_total.merge(agg_abertos, on="versao_sistema", how="left").fillna(0)
        por_versao["Chamados_abertos"] = por_versao["Chamados_abertos"].astype(int)
        por_versao["_ord"] = por_versao["versao_sistema"].apply(_semver_tuple)
        por_versao = por_versao.sort_values("_ord", ascending=True)

        st.markdown("#### 📌 Por versão — chamados **ainda abertos** (contexto da versão no cadastro)")
        st.caption("Apenas volume **atual** por versão. O histórico total de chamados por versão está na seção abaixo, separado.")
        st.dataframe(
            por_versao[["versao_sistema", "Chamados_abertos"]].rename(
                columns={"versao_sistema": "Versão", "Chamados_abertos": "Abertos agora"}
            ),
            hide_index=True,
            use_container_width=True,
            height=min(380, max(220, 40 + min(len(por_versao), 12) * 28)),
        )
        if len(por_versao) > 12:
            st.caption(f"Tabela com rolagem — **{len(por_versao)}** versões. Gráfico: amostra das que têm mais abertos.")

        st.markdown("#### 📜 Total histórico de chamados por versão")
        st.caption(
            "Quantidade **acumulada** de chamados já vinculados a cada versão no recorte (abertos + encerrados). "
            "Independente da tabela de **abertos agora** acima."
        )
        st.dataframe(
            por_versao.sort_values("_ord", ascending=True)[["versao_sistema", "Total_chamados"]].rename(
                columns={"versao_sistema": "Versão", "Total_chamados": "Total histórico (recorte)"}
            ),
            hide_index=True,
            use_container_width=True,
            height=min(380, max(220, 40 + min(len(por_versao), 12) * 28)),
        )

        nmax = len(por_versao)
        n_graf = st.slider(
            "Quantas versões exibir no gráfico (as com mais chamados abertos)",
            min_value=1,
            max_value=nmax,
            value=min(18, nmax),
            key="aba3_n_versao_grafico",
            help="Só as N versões com mais abertos; sem barra agregada.",
        )
        por_ord_abertos = por_versao.sort_values("Chamados_abertos", ascending=False)
        por_chart = por_ord_abertos.head(n_graf).sort_values("Chamados_abertos", ascending=True)

        altura_barras = min(520, 120 + len(por_chart) * 26)
        fig_v = px.bar(
            por_chart,
            x="Chamados_abertos",
            y="versao_sistema",
            orientation="h",
            labels={"Chamados_abertos": "Chamados abertos", "versao_sistema": "Versão"},
            color="Chamados_abertos",
            color_continuous_scale="Reds",
        )
        fig_v.update_layout(showlegend=False, height=altura_barras, margin=dict(l=8, r=8, t=8, b=8))
        st.plotly_chart(fig_v, use_container_width=True)

        # --- 2) Categorias (abertos) — mais aberturas com a desenvolvedora ---
        st.markdown("#### 📊 Categorias (IA) — volume entre chamados **ainda abertos**")
        ab = dfv[dfv["aberto"]]
        if ab.empty:
            st.info("Nenhum chamado aberto no recorte.")
        else:
            cat_cnt = ab["categoria_ia"].value_counts().reset_index()
            cat_cnt.columns = ["Categoria", "Volume"]
            fig_c = px.bar(
                cat_cnt.sort_values("Volume", ascending=True),
                x="Volume",
                y="Categoria",
                orientation="h",
                color="Volume",
                color_continuous_scale="Blues",
            )
            fig_c.update_layout(showlegend=False, height=max(280, len(cat_cnt) * 24))
            st.plotly_chart(fig_c, use_container_width=True)

        # --- 3) Mapa nr_chamado -> versões em release (para “corrigido na versão X”) ---
        map_nr_releases: dict = {}
        try:
            engine = get_connection()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM release_itens LIMIT 1"))
                try:
                    ri = pd.read_sql(
                        text(
                            """
                            SELECT nr_chamado, versao, titulo_release FROM release_itens
                            WHERE versao IS NOT NULL AND TRIM(versao) <> ''
                            """
                        ),
                        conn,
                    )
                except Exception:
                    ri = pd.read_sql(
                        text(
                            """
                            SELECT nr_chamado, versao FROM release_itens
                            WHERE versao IS NOT NULL AND TRIM(versao) <> ''
                            """
                        ),
                        conn,
                    )
                    ri["titulo_release"] = ""
            if not ri.empty:
                for _, r in ri.iterrows():
                    if _titulo_release_eh_pdv_movel(r.get("titulo_release")):
                        continue
                    v = str(r["versao"]).strip()
                    if not _versao_sistema_listagem_ok(v, teto=_teto_v):
                        continue
                    nr = int(r["nr_chamado"])
                    map_nr_releases.setdefault(nr, set()).add(v)
        except Exception:
            pass

        def releases_txt(nr: int) -> str:
            s = map_nr_releases.get(int(nr), set())
            if not s:
                return "—"
            return ", ".join(sorted(s, key=lambda x: _tuple_versao_sistema_quatro(x) or (0, 0, 0, 0)))

        # --- 4) Consulta: versão segura? + lista filtrável ---
        st.divider()
        st.markdown("#### 🛡️ Consulta por versão (ex.: atualizar rede para 2.9.252?)")
        st.caption(
            "Padrão **X.Y.Z** / **X.Y.Z.N** (opcional **V**), sem **,** nem **.** no início; "
            "≥ **V 1.06.27**; ≤ **versão atual**. **PDV Móvel** excluído."
        )
        lista_ver = [
            v
            for v in por_versao.sort_values("_ord", ascending=True)["versao_sistema"].tolist()
            if _ok_ver(v)
        ]
        lista_ver_ui = lista_ver[::-1]  # mais recentes primeiro no select
        if not lista_ver_ui:
            st.warning(
                "Nenhuma versão no recorte passou na validação (formato + mínimo V 1.06.27; textos com PDV Móvel excluídos). "
                "Ajuste o cadastro **versão_sistema** nos chamados ou o filtro de dados."
            )
            v_consulta = None
        else:
            v_consulta = st.selectbox("Versão a analisar", options=lista_ver_ui, index=0)
        sub = dfv[dfv["versao_sistema"] == v_consulta] if v_consulta is not None else dfv.iloc[0:0]
        erros_sub = sub[sub["eh_erro"]]
        abertos_erro = erros_sub[erros_sub["aberto"]]
        fechados_erro = erros_sub[~erros_sub["aberto"]]
        n_aberto_erro = len(abertos_erro)
        n_fech_erro = len(fechados_erro)

        if v_consulta is not None:
            if n_aberto_erro > 0:
                st.error(
                    f"**Atenção:** na versão **{v_consulta}** existem **{n_aberto_erro}** chamado(s) classificados como **erro** ainda **ativos** — risco para rollout até normalizar ou subir versão com correções."
                )
            else:
                st.success(
                    f"Nenhum chamado de **erro** ainda **aberto** vinculado à versão **{v_consulta}** no histórico analisado. "
                    "Ainda assim confira melhorias/fiscais abaixo."
                )
            st.metric("Erros já encerrados (histórico nesta versão)", n_fech_erro)
            if n_fech_erro and map_nr_releases:
                com_release = sum(1 for _, r in fechados_erro.iterrows() if int(r["nr_chamado"]) in map_nr_releases)
                st.caption(f"Desses, **{com_release}** aparecem em pelo menos um **release** (citados em nota de versão).")

        st.markdown("##### Filtros da lista detalhada")
        c1, c2, c3 = st.columns(3)
        with c1:
            f_cat = st.multiselect(
                "Categoria (IA)",
                options=sorted(dfv["categoria_ia"].unique()),
                default=[],
            )
        with c2:
            f_tipo = st.selectbox("Tipo", ["Todos", "Só erros", "Só melhorias", "Só fiscal/adequação", "Só abertos"])
        with c3:
            q = st.text_input("Pesquisa (resumo / nr chamado)", "")

        det = sub.copy()
        if f_cat:
            det = det[det["categoria_ia"].isin(f_cat)]
        if f_tipo == "Só erros":
            det = det[det["eh_erro"]]
        elif f_tipo == "Só melhorias":
            det = det[det["categoria_ia"].apply(_eh_melhoria)]
        elif f_tipo == "Só fiscal/adequação":
            det = det[det["categoria_ia"].apply(_eh_fiscal)]
        elif f_tipo == "Só abertos":
            det = det[det["aberto"]]
        if q.strip():
            m = det["Resumo"].str.contains(q, case=False, na=False) | det["nr_chamado"].astype(str).str.contains(
                re.escape(q.strip()), na=False
            )
            det = det[m]

        det["Status"] = det["aberto"].map({True: "Aberto", False: "Encerrado/Cancelado"})
        det["Correções (releases)"] = det["nr_chamado"].apply(releases_txt)
        det["Situação erro"] = det.apply(
            lambda r: "Ainda aguardando correção (aberto)"
            if r["eh_erro"] and r["aberto"]
            else ("Encerrado — ver releases citados" if r["eh_erro"] and not r["aberto"] else "—"),
            axis=1,
        )
        show_cols = [
            "nr_chamado",
            "Cliente",
            "versao_sistema",
            "categoria_ia",
            "Status",
            "Situação erro",
            "Correções (releases)",
            "Resumo",
            "data_abertura",
            "usuario_epsy",
        ]
        show_cols = [c for c in show_cols if c in det.columns]
        det_sorted = det.sort_values(["aberto", "nr_chamado"], ascending=[False, False])
        st.dataframe(
            det_sorted[show_cols],
            hide_index=True,
            use_container_width=True,
            height=420,
        )
        st.caption(
            "**Correções (releases):** versões em que o número do chamado constou na nota de release. "
            "Chamado **aberto** = problema ainda não encerrado no Helpdesk. Migração **release_itens** + raspagem/manual de releases enriquece esta coluna."
        )

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
        df_cli = df.copy()
        df_cli["cliente_exibicao"] = df_cli["cliente_nome"].replace(
            ["", None], "Sem cliente vinculado"
        ).fillna("Sem cliente vinculado")
        mask_na = df_cli["cliente_exibicao"].isin(["Não Informado", "Não Informada", ""])
        df_cli.loc[mask_na, "cliente_exibicao"] = "Sem cliente vinculado"
        clientes_agg = df_cli.groupby("cliente_exibicao", as_index=False).agg(
            Total_Chamados=("nr_chamado", "count"),
            Fila_Ativa=("is_aberto", "sum"),
        ).sort_values("Total_Chamados", ascending=False).head(15)
        clientes_agg.rename(
            columns={
                "cliente_exibicao": "Cliente",
                "Total_Chamados": "Total Abertos (Período)",
                "Fila_Ativa": "Ainda Pendentes",
            },
            inplace=True,
        )
        if clientes_agg.empty:
            st.info("Nenhum chamado no período. Ajuste os filtros.")
        else:
            st.dataframe(clientes_agg, hide_index=True, use_container_width='stretch')
            if (clientes_agg["Cliente"] == "Sem cliente vinculado").any():
                st.caption("💡 Vincule clientes em **Configurações** para identificar por razão social.")

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
                st.dataframe(df_rank, hide_index=True, use_container_width='')

        with r2:
            st.markdown("#### 📊 Vulnerabilidade por Módulo")
            df_mod = m["vulnerabilidade_modulo"]
            if df_mod.empty:
                st.info("Nenhuma reprovação registrada por módulo.")
            else:
                df_mod.columns = ["Módulo", "Reprovações"]
                st.dataframe(df_mod, hide_index=True, use_container_width='stretch')

    except Exception as e:
        st.warning(
            "As tabelas de homologação (`chamados`, `releases`, `ciclos_homologacao`) "
            "podem não existir ainda. Execute o script `database/migracao_ciclos_homologacao.sql`."
        )
        st.error(str(e))

# ------------------------------------------
# ABA 6: FILA ABERTA + RELEASES / REINCIDÊNCIA
# ------------------------------------------
with aba6:
    st.subheader("📂 Chamados x releases (tempo real no banco)")
    st.markdown(
        "**Reincidência** = chamado citado em **mais de um** release (`release_itens`). "
        "**Sem release** = ainda não apareceu em nenhum release processado. "
        "Priorize migrar releases na **Page 11** (grava linha por chamado)."
    )
    filtro_fila = st.selectbox(
        "Exibir",
        ["Somente ativos (não encerrados/cancelados)", "Encerrados ou cancelados", "Todos"],
        key="aba6_filtro",
    )
    engine = get_connection()
    try:
        cols = set(
            pd.read_sql(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'chamados_tecnuv'
                    """
                ),
                engine,
            )["column_name"].str.lower()
        )
        # Cliente: instalações antigas = cliente_nome; modelo atual / ORM = nome_cliente
        if "nome_cliente" in cols:
            expr_cliente = "COALESCE(c.nome_cliente, '—')"
        elif "cliente_nome" in cols:
            expr_cliente = "COALESCE(c.cliente_nome, '—')"
        else:
            expr_cliente = """COALESCE((
                SELECT v.nome_cliente FROM clientes_vinculados_chamado v
                WHERE v.nr_chamado = c.nr_chamado LIMIT 1
            ), '—')"""
        if "usuario_epsy" in cols and "nome_analista_epsy" in cols:
            expr_quem = "COALESCE(c.usuario_epsy, c.nome_analista_epsy, '—')"
        elif "usuario_epsy" in cols:
            expr_quem = "COALESCE(c.usuario_epsy, '—')"
        elif "nome_analista_epsy" in cols:
            expr_quem = "COALESCE(c.nome_analista_epsy, '—')"
        else:
            expr_quem = "'—'"

        tem_release_itens = False
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM release_itens LIMIT 1"))
            tem_release_itens = True
        except Exception:
            pass

        if tem_release_itens:
            sub_ri = """
            SELECT nr_chamado, COUNT(DISTINCT id_release) AS qtd_releases
            FROM release_itens GROUP BY nr_chamado
            """
        else:
            sub_ri = """
            SELECT id_chamado::integer AS nr_chamado, COUNT(DISTINCT id_release) AS qtd_releases
            FROM ciclos_homologacao GROUP BY id_chamado
            """

        cat_select = "COALESCE(c.categoria_ia, '—') AS categoria_ia" if "categoria_ia" in cols else "'—' AS categoria_ia"

        sql = f"""
        SELECT
            c.nr_chamado,
            {expr_cliente} AS cliente,
            c.data_abertura,
            {expr_quem} AS quem_abriu,
            c.status_atual,
            COALESCE(ri.qtd_releases, 0) AS vezes_em_releases,
            CASE
                WHEN COALESCE(ri.qtd_releases, 0) > 1 THEN 'Reincidência (liberado em +1 release)'
                WHEN COALESCE(ri.qtd_releases, 0) = 1 THEN '1 liberação em release'
                ELSE 'Não consta em release'
            END AS situacao_release,
            {cat_select},
            LEFT(COALESCE(c.motivo_abertura_html, c.assunto_encerramento, ''), 120) AS resumo
        FROM chamados_tecnuv c
        LEFT JOIN ( {sub_ri} ) ri ON ri.nr_chamado = c.nr_chamado
        WHERE 1=1
        """
        if filtro_fila.startswith("Somente ativos"):
            sql += """ AND TRIM(LOWER(COALESCE(c.status_atual, ''))) NOT IN ('encerrado', 'cancelado')
                AND LOWER(COALESCE(c.status_atual, '')) NOT LIKE '%encerrado%'
                AND LOWER(COALESCE(c.status_atual, '')) NOT LIKE '%cancelado%' """
        elif filtro_fila.startswith("Encerrados"):
            sql += """ AND (
                TRIM(LOWER(COALESCE(c.status_atual, ''))) IN ('encerrado', 'cancelado')
                OR LOWER(COALESCE(c.status_atual, '')) LIKE '%encerrado%'
                OR LOWER(COALESCE(c.status_atual, '')) LIKE '%cancelado%'
            ) """
        sql += " ORDER BY c.data_abertura DESC NULLS LAST LIMIT 2000"
        df_fila = pd.read_sql(text(sql), engine)
        if not df_fila.empty and "resumo" in df_fila.columns:
            df_fila["resumo"] = df_fila["resumo"].apply(limpar_html)
        if not tem_release_itens:
            st.info(
                "Tabela **`release_itens`** ainda não existe — contagem de releases veio de **`ciclos_homologacao`**. "
                "Para uma linha por bullet no release, execute `database/migracao_release_itens.sql` e reprocesse na Page 11."
            )
        if df_fila.empty:
            st.info("Nenhum registro com os filtros atuais.")
        else:
            st.metric("Registros", len(df_fila))
            st.dataframe(df_fila, use_container_width=True, hide_index=True)
    except Exception as e:
        st.warning("Erro na consulta da aba Fila/releases. Verifique tabelas `chamados_tecnuv` e `ciclos_homologacao`.")
        st.code(str(e))

registrar_log_auditoria(usuario_id, "VIEW_DASHBOARD_CHAMADOS", "Acessou Dashboard Analítico - Chamados Tecnuv (EPSY)")