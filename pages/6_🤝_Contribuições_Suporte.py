"""
Essa page foi renomeada para 6_🤝_Contribuicoes_Suporte.py para refletir melhor o conteúdo e evitar confusão com a page de dashboard de tickets. O código da antiga page 5_📊_Dashboard_Tickets_EPSY.py foi mantido aqui para referência, mas a nova page 6 terá foco total em contribuições, avaliações e fila de revisão, enquanto a antiga page 5 continuará sendo o dashboard analítico dos tickets EPSY.

"""
import html
import zipfile
import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection
import os
import time
from datetime import datetime, timezone

from app.services.base_conhecimento_service import (
    AprovacaoContribuicaoError,
    aprovar_contribuicao_conhecimento,
    computar_xp_aprovacao,
    registrar_bonus_semanal_contribuicao,
)
import tempfile
import unicodedata
import re
import tempfile  # Faltava esta importação
from difflib import SequenceMatcher
import json
import tempfile
from dotenv import load_dotenv
import unicodedata
import re
from menus import *
from modules.utils import inicializar_usuario, calcular_patente
from services.perfil_usuario import normalizar_perfil_para_sessao
from services.ui_realtime import render_global_notifications_listener, show_gamification_upgrade_card
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.wiki_authenticator import process_forced_logout_from_url
from services.ui_avatar import html_avatar_perfil_circular
from services.contrib_rules_ui import render_contrib_rules_table
from services.vector_db import (
    EMBEDDING_DIM,
    buscar_similares,
    criar_extensao_e_tabela,
    indexar_base_conhecimento,
)

load_dotenv()


try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass
#==================================================================================================================


# Configuração da página (deve ser a primeira chamada Streamlit)
st.set_page_config(page_title="WikiSuporte", page_icon="🏆", layout="wide")

if process_forced_logout_from_url():
    st.rerun()

# Verificação de autenticação com default explícito para False e mensagem de redirecionamento para melhor UX
if not st.session_state.get('autenticado', False):
    st.info("Redirecionando para a página de login...")  # Sugestão: Adicionar feedback ao usuário
    st.switch_page("app.py")
render_global_notifications_listener()
wiki_theme_apply_authenticated()

# Recuperação de variáveis de sessão com verificações para evitar erros
usuario_logado_id = st.session_state.get('usuario_id')
if usuario_logado_id is None:  # Sugestão: Verificação para ID ausente
    st.error("ID de usuário não encontrado. Por favor, faça login novamente.")
    st.switch_page("app.py")  # Redireciona se ID não existir

# Definição de perfis válidos como constante para validação (sugestão para consistência e manutenção)
PERFIS_VALIDOS = ("analista", "admin")
perfil_logado = normalizar_perfil_para_sessao(st.session_state.get("perfil", "analista"))
if perfil_logado not in PERFIS_VALIDOS:
    st.warning(f"Perfil não reconhecido. Usando default 'analista'.")
    perfil_logado = "analista"

# Configuração do diretório de upload (sem mudanças significativas, mas com comentário para segurança)
UPLOAD_DIR = "uploads_wiki"
MAX_ANEXOS_CONTRIBUICAO = 10
MAX_BYTES_ANEXO_CONTRIBUICAO = 25_000_000
os.makedirs(UPLOAD_DIR, exist_ok=True)  # Em produção, considere usar armazenamento em nuvem para maior segurança

engine = get_connection()

_busca_sem_ok = False
registrar_busca_com_topico = None  # type: ignore
listar_buscas_mesmo_assunto = None  # type: ignore
ranking_topicos_agregado = None  # type: ignore
historico_por_topico_recente = None  # type: ignore
try:
    from services.busca_semantica_historico import (
        historico_por_topico_recente as _hpt,
        listar_buscas_mesmo_assunto as _lbm,
        ranking_topicos_agregado as _rta,
        registrar_busca_com_topico as _rbc,
    )

    with engine.connect() as _probe:
        _probe.execute(text("SELECT 1 FROM busca_topicos LIMIT 1"))
    registrar_busca_com_topico = _rbc
    listar_buscas_mesmo_assunto = _lbm
    ranking_topicos_agregado = _rta
    historico_por_topico_recente = _hpt
    _busca_sem_ok = True
except Exception:
    pass


def _notificar_email_obsoleto(email_autor: str, nome_autor: str, titulo: str, quem: str, motivo: str) -> None:
    """Aviso por e-mail ao autor quando a contribuição for marcada obsoleta (secrets opcional)."""
    if not email_autor or not str(email_autor).strip():
        return
    try:
        import smtplib
        from email.message import EmailMessage
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = int(st.secrets["email"]["smtp_port"])
        smtp_user = st.secrets["email"]["smtp_user"]
        smtp_pass = st.secrets["email"]["smtp_password"]
        remetente = st.secrets["email"].get("from_addr", smtp_user)
        msg = EmailMessage()
        msg["Subject"] = "[WikiSuporte] Sua contribuição foi marcada como obsoleta"
        msg["From"] = remetente
        msg["To"] = email_autor
        msg.set_content(
            f"Olá, {nome_autor or 'analista'}.\n\n"
            f"A contribuição \"{titulo}\" foi marcada como OBSOLETA por {quem}.\n"
            f"Motivo / orientação: {motivo or '(não informado)'}\n\n"
            "Acesse WikiSuporte → Base de Conhecimento → Minhas Contribuições, "
            "atualize o texto e reenvie para a fila de avaliação.\n"
        )
        with smtplib.SMTP(smtp_server, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception:
        pass  # e-mail opcional


# ===============================================================================================================================================================
# 2. FUNÇÕES DE CACHE (Trazidas das Pages 6 e 8)
# ===============================================================================================================================================================
@st.cache_data(ttl=3600)
def carregar_wikis():
    try:
        engine = get_connection()
        # Só as colunas usadas na tela + campos normalizados para busca
        query = """
            SELECT
                id,
                titulo,
                categoria,
                conteudo,
                caminho_anexo,
                criado_em
            FROM base_conhecimento
            WHERE origem = 'WIKI_HELPDESK'
            ORDER BY criado_em DESC
        """
        df = pd.read_sql(query, engine)

        if df.empty:
            return df, None

        # Normalização de texto feita UMA vez, reaproveitada nas buscas
        import unicodedata, re

        def _norm_text(t):
            txt = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8')
            return re.sub(r'[^a-z0-9\s]', '', txt.lower()).strip()

        df["titulo_norm"] = df["titulo"].fillna("").map(_norm_text)
        df["categoria_norm"] = df["categoria"].fillna("").map(_norm_text)
        df["conteudo_norm"] = df["conteudo"].fillna("").map(_norm_text)

        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=3600)
def carregar_manuais():
    try:
        engine = get_connection()
        query = """
            SELECT
                id,
                titulo,
                categoria,
                conteudo,
                caminho_anexo,
                criado_em
            FROM base_conhecimento
            WHERE origem = 'MANUAL_HELPDESK'
            ORDER BY criado_em DESC
        """
        df = pd.read_sql(query, engine)

        if df.empty:
            return df, None

        import unicodedata, re

        def _norm_text(t):
            txt = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8')
            return re.sub(r'[^a-z0-9\s]', '', txt.lower()).strip()

        df["titulo_norm"] = df["titulo"].fillna("").map(_norm_text)
        df["categoria_norm"] = df["categoria"].fillna("").map(_norm_text)
        df["conteudo_norm"] = df["conteudo"].fillna("").map(_norm_text)

        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)

# ==========================================
# 3. TÍTULO E DESCRIÇÃO
# ==========================================
st.title("🧠 Base de Conhecimento")
st.markdown("Respostas rápidas, manuais do PostoGestor, wikis do HelpDesk e a Base de Conhecimento colaborativa em um só lugar!")
with st.expander("📋 Regras de contribuições e penalidades", expanded=True):
    st.caption("Guia rápido para pontuação, bônus e descontos semanais.")
    render_contrib_rules_table(compact=True)


# ==========================================
# 4. DEFINIÇÃO DAS ABAS (Nova Ordem de UX)
# ==========================================
if perfil_logado == "admin":
    abas = st.tabs([
        "🏅 Inicio & Ranking", 
        "🔎 WikiSuporte - Busque na Base", 
        "📘 Acervo Digital", 
        "📖 Histórico de Buscas", 
        "📝 Adicionar Contribuição", 
        "⚖️ Fila de Avaliação", 
        "📚 Minhas Contribuições", 
        "🔍 Explorar Base de Conhecimento"
    ])
    aba_ranking, aba_gemini, aba_acervo, aba_arquivo, aba_nova, aba_fila, aba_minhas, aba_explorar = abas
else:
    abas = st.tabs([
        "🏅 Home & Ranking", 
        "🔎 WikiSuporte - Busque na Base", 
        "📘 Acervo Digital", 
        "📖 Histórico de Buscas", 
        "📝 Adicionar Contribuição", 
        "📚 Minhas Contribuições", 
        "🔍 Explorar Base de Conhecimento"
    ])
    aba_ranking, aba_gemini, aba_acervo, aba_arquivo, aba_nova, aba_minhas, aba_explorar = abas

# ==========================================
# ABA 1: GAMIFICAÇÃO E RANKING (Sincronizado com Trigger)
# ==========================================
with aba_ranking:
    st.subheader("📊 Ranking de Especialistas")

    # Importamos a lista de níveis para o sumário visual (expander)
    from modules.utils import NIVEIS_CONHECIMENTO

    def _nome_ranking_com_status(row: pd.Series) -> str:
        nome = str(row.get("Analista") or "").strip()
        if bool(row.get("em_ferias")):
            nome += " 🏖️"
        if bool(row.get("em_atendimento_externo")):
            nome += " 🚗"
        return nome

    with engine.connect() as conn:
        query_ranking = text("""
            SELECT u.nome AS "Analista",
                   COUNT(b.id) AS "Dicas Aprovadas",
                   u.xp_total AS "XP Acumulado",
                   u.medalha_atual AS "Patente",
                   NULLIF(TRIM(COALESCE(u.caminho_foto_perfil, '')), '') AS caminho_foto_perfil,
                   COALESCE(u.em_ferias, FALSE) AS em_ferias,
                   COALESCE(u.em_atendimento_externo, FALSE) AS em_atendimento_externo
            FROM usuarios u
            LEFT JOIN base_conhecimento b ON b.id_analista_autor = u.id
                 AND b.origem = 'CONHECIMENTO_SUPORTE'
                 AND b.status = 'APROVADO'
            WHERE u.xp_total > 0
            GROUP BY u.id, u.nome, u.xp_total, u.medalha_atual,
                     NULLIF(TRIM(COALESCE(u.caminho_foto_perfil, '')), ''),
                     COALESCE(u.em_ferias, FALSE),
                     COALESCE(u.em_atendimento_externo, FALSE)
            ORDER BY u.xp_total DESC
        """)
        df_ranking = pd.read_sql(query_ranking, conn)

        if not df_ranking.empty:
            df_ranking.insert(0, "Ícone", df_ranking["XP Acumulado"].apply(lambda x: calcular_patente(x)["icon"]))
            df_ranking["Analista"] = df_ranking.apply(_nome_ranking_com_status, axis=1)

            trofeus = ("🥇", "🥈", "🥉")
            st.markdown("##### Pódio")
            cols_podio = st.columns(3)
            top_n = min(3, len(df_ranking))
            for i in range(3):
                with cols_podio[i]:
                    if i < top_n:
                        r = df_ranking.iloc[i]
                        caminho = r.get("caminho_foto_perfil")
                        if caminho is None or (isinstance(caminho, float) and pd.isna(caminho)):
                            caminho = None
                        else:
                            caminho = str(caminho).strip() or None
                        st.markdown(
                            html_avatar_perfil_circular(caminho, tamanho_px=100),
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"<div style='text-align:center;font-size:2.1rem;line-height:1.2;'>{trofeus[i]}</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f"<div style='text-align:center;font-weight:600'>"
                            f"{html.escape(str(r['Analista']))}</div>",
                            unsafe_allow_html=True,
                        )
                        st.caption(str(r.get("Patente") or ""))
                        st.caption(
                            f"{int(r['XP Acumulado'])} XP · {int(r['Dicas Aprovadas'])} contribuições"
                        )

            st.divider()

            df_tabela = df_ranking[
                ["Ícone", "Analista", "Dicas Aprovadas", "XP Acumulado", "Patente"]
            ].copy()

            st.dataframe(
                df_tabela,
                width="stretch",
                hide_index=True,
                column_config={
                    "Ícone": st.column_config.TextColumn("Ícone", width="small"),
                    "XP Acumulado": st.column_config.NumberColumn("XP Total", format="%d ⚡"),
                    "Dicas Aprovadas": st.column_config.NumberColumn("Contribuições", width="medium"),
                },
            )

            with st.expander("🔍 Guia de Patentes (De 1k a 1M XP)"):
                cols = st.columns(5)
                # Mostra a jornada do conhecimento
                for i, n in enumerate(reversed(NIVEIS_CONHECIMENTO)):
                    with cols[i % 5]:
                        st.markdown(f"""
                            <div style="text-align:center; padding:8px; border-bottom:2px solid {n['cor']}; margin-bottom:5px;">
                                <div style="font-size:22px;">{n['icon']}</div>
                                <div style="font-size:11px; font-weight:bold; color:white;">{n['nome']}</div>
                                <div style="font-size:10px; color:#666;">{n['xp']/1000:g}k</div>
                            </div>
                        """, unsafe_allow_html=True)
        else:
            st.warning("Nenhum analista pontuou ainda. Hora de minerar conhecimento! ⛏️")

# ==========================================
# ABA 2: BUSCA SEMÂNTICA RAG (IA TEMPORARIAMENTE DESATIVADA)
# ==========================================
with aba_gemini:
    st.markdown(
        """
        <style>
        .ws-busca-hero {
            text-align: center;
            margin: 0 auto 1rem auto;
            max-width: 56rem;
        }
        .ws-busca-hero h1 {
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
            font-weight: 800;
            font-size: clamp(1.9rem, 4.8vw, 2.8rem);
            margin: 0;
            letter-spacing: -0.03em;
        }
        .ws-busca-hero .wiki { color: #f85001; }
        .ws-busca-hero .suporte { color: #15789a; }
        html[data-theme="dark"] .ws-busca-hero .wiki { color: #ff9a6b; }
        html[data-theme="dark"] .ws-busca-hero .suporte { color: #5eb8d9; }
        .ws-busca-hero p {
            color: #4b5563;
            font-size: 1rem;
            margin: 0.45rem 0 0 0;
        }
        html[data-theme="dark"] .ws-busca-hero p { color: #d1d5db; }
        </style>
        <div class="ws-busca-hero">
            <h1><span class="wiki">Wiki</span><span class="suporte">Suporte</span></h1>
            <p><strong>Está com dúvidas, precisa de alguma informação?</strong><br/>Busque na nossa Base de Conhecimento.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        criar_extensao_e_tabela(EMBEDDING_DIM)
    except Exception:
        pass

    dim_atual = None
    try:
        with engine.connect() as conn:
            row_dim = conn.execute(
                text(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod) AS tipo
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'base_conhecimento_embeddings'
                      AND a.attname = 'embedding'
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    LIMIT 1
                    """
                )
            ).fetchone()
        if row_dim and row_dim[0]:
            m = re.search(r"vector\((\d+)\)", str(row_dim[0]).lower())
            if m:
                dim_atual = int(m.group(1))
    except Exception:
        dim_atual = None

    if dim_atual and dim_atual != EMBEDDING_DIM:
        st.warning(
            f"⚠️ Dimensão vetorial atual: {dim_atual}. Recomendada para Gemini neste projeto: {EMBEDDING_DIM}. "
            "Considere alinhar para manter a precisão da busca semântica."
        )

    origem_opts = ["CONHECIMENTO_SUPORTE", "WIKI_HELPDESK", "MANUAL_HELPDESK"]
    try:
        with engine.connect() as conn:
            rows_origem = conn.execute(
                text(
                    """
                    SELECT DISTINCT origem
                    FROM base_conhecimento
                    WHERE status = 'APROVADO'
                    ORDER BY origem
                    """
                )
            ).fetchall()
        origem_db = [str(r[0]) for r in rows_origem if r and r[0]]
        if origem_db:
            origem_opts = origem_db
    except Exception:
        pass

    colf1, colf2 = st.columns([2, 1])
    with colf1:
        origem_sel = st.multiselect(
            "Fontes da busca",
            options=origem_opts,
            default=[o for o in ["CONHECIMENTO_SUPORTE", "WIKI_HELPDESK", "MANUAL_HELPDESK"] if o in origem_opts] or origem_opts,
            help="Escolha onde pesquisar para deixar os resultados mais precisos.",
        )
    with colf2:
        top_k = st.slider("Precisão (top resultados)", min_value=3, max_value=15, value=8, step=1)

    with st.form("form_busca_rag_semantica", clear_on_submit=False):
        pergunta = st.text_input(
            "Digite sua dúvida",
            placeholder="Ex.: Como configuro o e-mail no PostoGestor para envio automático?",
            key="input_psy_rag",
        )
        buscar = st.form_submit_button("🔍 Buscar na Base de Conhecimento", type="primary", use_container_width=True)

    if perfil_logado == "admin":
        with st.expander("⚙️ Administração da busca vetorial", expanded=False):
            st.caption(
                f"Dimensão recomendada para Gemini no cenário atual: **{EMBEDDING_DIM}**. "
                "Esta dimensão é um bom equilíbrio entre precisão e velocidade para o volume atual."
            )
            if st.button("♻️ Reindexar Base de Conhecimento (RAG)", key="btn_reindex_rag"):
                with st.spinner("Reindexando embeddings da Base de Conhecimento..."):
                    total_chunks = indexar_base_conhecimento(origens=origem_sel or None, limite=1500)
                st.success(f"Reindexação concluída. Chunks indexados/atualizados: {total_chunks}")

    # IA desativada por decisão operacional (manter código de referência)
    # from services.llm_router import gerar_resposta
    # resposta_ia = gerar_resposta(pergunta=pergunta, contexto=texto_contexto)
    # st.markdown(resposta_ia.texto)

    if buscar:
        if not (pergunta or "").strip():
            st.warning("⚠️ Insira uma dúvida para pesquisar.")
        else:
            with st.spinner("Executando busca semântica RAG na Base de Conhecimento..."):
                resultados = buscar_similares(
                    pergunta.strip(),
                    top_k=int(top_k),
                    origens=origem_sel or None,
                    usar_embedding_query=True,
                )
                resultados = [r for r in resultados if float(r.get("similaridade", 0.0)) >= 0.45]

                if not resultados:
                    with engine.connect() as conn:
                        rows = conn.execute(
                            text(
                                """
                                SELECT id, titulo, origem, conteudo
                                FROM base_conhecimento
                                WHERE status = 'APROVADO'
                                  AND origem = ANY(:origens)
                                  AND (titulo ILIKE :q OR conteudo ILIKE :q)
                                ORDER BY atualizado_em DESC NULLS LAST, criado_em DESC
                                LIMIT :lim
                                """
                            ),
                            {
                                "origens": origem_sel or origem_opts,
                                "q": f"%{pergunta.strip()}%",
                                "lim": int(top_k),
                            },
                        ).fetchall()
                    resultados = [
                        {
                            "id_conhecimento": int(r[0]),
                            "titulo": str(r[1] or "Sem título"),
                            "origem": str(r[2] or "BASE"),
                            "texto_chunk": str(r[3] or "")[:1600],
                            "similaridade": 0.30,
                        }
                        for r in rows
                    ]

            if not resultados:
                st.error("Nenhum resultado relevante foi encontrado para a sua dúvida.")
            else:
                st.success(f"Foram encontrados {len(resultados)} resultado(s) relevantes.")
                st.info("🤖 IA de resposta está temporariamente desativada. Exibindo resultados semânticos da Base.")

                resumo_linhas = []
                for i, item in enumerate(resultados[:3], start=1):
                    trecho = " ".join(str(item["texto_chunk"]).split())
                    trecho = trecho[:220].rstrip() + ("..." if len(trecho) > 220 else "")
                    resumo_linhas.append(
                        f"{i}. **{item['titulo']}** ({item['origem']}) — {trecho}"
                    )
                st.markdown("### 🧠 Resumo semântico")
                st.markdown("\n".join(resumo_linhas))

                st.markdown("### 📚 Fontes encontradas")
                for item in resultados:
                    sim_pct = int(float(item.get("similaridade", 0.0)) * 100)
                    with st.expander(
                        f"📄 {item['titulo']} · {item['origem']} · Similaridade {sim_pct}%"
                    ):
                        st.write(item["texto_chunk"])

                if _busca_sem_ok and registrar_busca_com_topico:
                    try:
                        registrar_busca_com_topico(
                            engine,
                            usuario_logado_id,
                            pergunta.strip(),
                            "Busca semântica RAG (IA desativada)",
                            "ASSISTENTE",
                            0,
                            0,
                            0,
                        )
                    except Exception:
                        pass

# ==========================================
# ABA UNIFICADA: ACERVO DIGITAL (WIKIS E MANUAIS)
# ==========================================
with aba_acervo:
    st.title("📚 Acervo Digital e Base de Conhecimento")
    st.markdown("Consulte rapidamente procedimentos do Helpdesk e manuais oficiais do PostoGestor num único local organizado.")
    
    # UX: Sub-abas mantêm os ambientes separados visualmente e impedem que variáveis colidam
    sub_wiki, sub_manual = st.tabs(["📘 Wikis Helpdesk", "📙 Manuais PostoGestor"])

    # ---------------------------------------------------------
    # SUB-AMBIENTE 1: WIKIS HELPDESK
    # ---------------------------------------------------------
    with sub_wiki:
        df_wikis, erro_bd = carregar_wikis()

        # UX: Ranking escondido em expander para libertar espaço vertical (Clean Design)
        with st.expander("🏆 Ver os assuntos mais pesquisados nas Wikis (agrupado por tema)"):
            if _busca_sem_ok and ranking_topicos_agregado:
                try:
                    rw = ranking_topicos_agregado(engine, "WIKI", 8)
                    df_rank_wiki = pd.DataFrame(rw, columns=["Assunto (tema)", "Buscas"]) if rw else pd.DataFrame()
                except Exception:
                    df_rank_wiki = pd.DataFrame()
            else:
                df_rank_wiki = pd.DataFrame()
            if df_rank_wiki.empty:
                with engine.connect() as conn:
                    query_rank_wiki = text("""
                        SELECT REPLACE(INITCAP(lower(pergunta)), '[wiki] ', '') as "Assunto", COUNT(id) as "Volume"
                        FROM historico_buscas_psy
                        WHERE lower(pergunta) LIKE '[wiki] %'
                        GROUP BY lower(pergunta)
                        ORDER BY "Volume" DESC LIMIT 5
                    """)
                    df_rank_wiki = pd.read_sql(query_rank_wiki, conn)
            if not df_rank_wiki.empty:
                st.dataframe(df_rank_wiki, width="stretch", hide_index=True)
            else:
                st.caption("Ainda não há dados suficientes para o ranking de Wikis.")

        st.markdown("<br>", unsafe_allow_html=True)

        # UX: Barra de pesquisa destacada num contentor com borda
        with st.container(border=True):
            st.markdown("#### 🔍 Motor de Busca Inteligente (Wikis)")
            col_busca_w, col_btn_w = st.columns([4, 1])
            with col_busca_w:
                termo_busca_wiki = st.text_input("O que está a procurar nas Wikis?", placeholder="Ex: Erro nota fiscal...", key="busca_wiki_input", label_visibility="collapsed")
            with col_btn_w:
                btn_buscar_wiki = st.button("Pesquisar", width='stretch', type="primary", key="btn_w")

        if erro_bd: 
            st.error(f"❌ Ocorreu um erro técnico: `{erro_bd}`")
        elif df_wikis.empty: 
            st.info("O acervo de Wikis do Helpdesk está vazio.")
        else:
            df_w = df_wikis.copy()

            if btn_buscar_wiki and termo_busca_wiki.strip():
                try:
                    if _busca_sem_ok and registrar_busca_com_topico:
                        registrar_busca_com_topico(
                            engine,
                            usuario_logado_id,
                            f"[WIKI] {termo_busca_wiki.strip()}",
                            "Busca Inteligente Wiki",
                            "WIKI",
                        )
                    else:
                        with engine.begin() as conn_log:
                            conn_log.execute(
                                text("""
                                INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                                VALUES (:u, :p, 'Busca Inteligente Wiki', 0, 0, 0)
                            """),
                                {"u": usuario_logado_id, "p": f"[WIKI] {termo_busca_wiki.strip()}"},
                            )
                except Exception as e:
                    st.error(f"Erro ao registrar métrica de busca: {e}")

                import unicodedata, re

                def norm_text_query(t: str) -> str:
                    txt = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8')
                    return re.sub(r'[^a-z0-9\s]', '', txt.lower()).strip()

                stopwords = {
                    'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das',
                    'no', 'na', 'em', 'para', 'com', 'como'
                }
                termo_norm = norm_text_query(termo_busca_wiki)
                fatias = [p for p in termo_norm.split() if p not in stopwords and len(p) > 2]

                if fatias:
                    def calcular_score(row):
                        score = 0
                        tit = row.get('titulo_norm', '')
                        cat = row.get('categoria_norm', '')
                        cont = row.get('conteudo_norm', '')
                        for f in fatias:
                            if f in tit:
                                score += 3
                            if f in cat:
                                score += 2
                            if f in cont:
                                score += 1
                        return score

                    df_w['score'] = df_w.apply(calcular_score, axis=1)
                    df_w = df_w[df_w['score'] > 0].sort_values(by='score', ascending=False)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Exibição
            if btn_buscar_wiki and termo_busca_wiki.strip() and df_w.empty:
                st.warning(f"Nenhum documento encontrado para as palavras-chave: **'{termo_busca_wiki}'**.")
            else:
                if btn_buscar_wiki and termo_busca_wiki.strip():
                    st.markdown(f"**📖 Resultados Encontrados ({len(df_w)}) - Ordenados por relevância**")
                
                for _, row in df_w.head(20).iterrows():
                    titulo = row.get('titulo', 'Sem Título')
                    categoria = row.get('categoria', 'Geral')
                    subcategoria = row.get('subcategoria', 'Não especificada')
                    conteudo = row.get('conteudo', 'Nenhum conteúdo descrito.')
                    
                    tag_score = f"⭐ Score: {row['score']}" if 'score' in df_w.columns else ""
                    
                    with st.expander(f"📑 {titulo} {tag_score}"):
                        st.markdown(f"**📂 Categoria:** `{categoria}` ➔ `{subcategoria}`")
                        st.divider()
                        st.markdown("#### 📖 Conteúdo")
                        st.markdown(conteudo)
                        if pd.notna(row.get('caminho_anexo')) and str(row.get('caminho_anexo')).strip():
                            st.info(f"📎 **Anexo disponível em:** {row['caminho_anexo']}")


    # ---------------------------------------------------------
    # SUB-AMBIENTE 2: MANUAIS POSTOGESTOR
    # ---------------------------------------------------------
    with sub_manual:
        df_manuais, erro_bd = carregar_manuais()

        # UX: Ranking em Expander
        with st.expander("🏆 Assuntos mais buscados nos Manuais (tema único)"):
            if _busca_sem_ok and ranking_topicos_agregado:
                try:
                    rm = ranking_topicos_agregado(engine, "MANUAL", 8)
                    df_rank_man = pd.DataFrame(rm, columns=["Assunto (tema)", "Buscas"]) if rm else pd.DataFrame()
                except Exception:
                    df_rank_man = pd.DataFrame()
            else:
                df_rank_man = pd.DataFrame()
            if df_rank_man.empty:
                with engine.connect() as conn:
                    query_rank_man = text("""
                        SELECT REPLACE(INITCAP(lower(pergunta)), '[manual] ', '') as "Assunto", COUNT(id) as "Volume"
                        FROM historico_buscas_psy
                        WHERE lower(pergunta) LIKE '[manual] %'
                        GROUP BY lower(pergunta)
                        ORDER BY "Volume" DESC LIMIT 5
                    """)
                    df_rank_man = pd.read_sql(query_rank_man, conn)
            if not df_rank_man.empty:
                st.dataframe(df_rank_man, width="stretch", hide_index=True)
            else:
                st.caption("Ainda não há dados suficientes para o ranking de Manuais.")

        st.markdown("<br>", unsafe_allow_html=True)

        # UX: Barra de pesquisa destacada
        with st.container(border=True):
            st.markdown("#### 🔍 Motor de Busca Inteligente (Manuais)")
            col_busca_m, col_btn_m = st.columns([4, 1])
            with col_busca_m:
                termo_busca_manual = st.text_input("O que está a procurar nos Manuais?", placeholder="Ex: Configurar impressora...", key="busca_manual_input", label_visibility="collapsed")
            with col_btn_m:
                btn_buscar_manual = st.button("Pesquisar", width='stretch', type="primary", key="btn_m")

        if erro_bd:
            st.error(f"❌ Ocorreu um erro técnico: `{erro_bd}`")
        elif df_manuais.empty:
            st.warning("Nenhum manual com a origem 'MANUAL_HELPDESK' foi encontrado.")
        else:
            df_m = df_manuais.copy()

            # --- CORREÇÃO 1: Usando as variáveis de estado do MANUAL ---
            if btn_buscar_manual and termo_busca_manual.strip():
                try:
                    # CORREÇÃO 2: Registro de métricas gravando como [MANUAL] no banco de dados
                    if _busca_sem_ok and registrar_busca_com_topico:
                        registrar_busca_com_topico(
                            engine,
                            usuario_logado_id,
                            f"[MANUAL] {termo_busca_manual.strip()}",
                            "Busca Inteligente Manual",
                            "MANUAL",
                        )
                    else:
                        with engine.begin() as conn_log:
                            conn_log.execute(
                                text("""
                                INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                                VALUES (:u, :p, 'Busca Inteligente Manual', 0, 0, 0)
                            """),
                                {"u": usuario_logado_id, "p": f"[MANUAL] {termo_busca_manual.strip()}"},
                            )
                except Exception as e:
                    st.error(f"Erro ao registrar métrica de busca: {e}")

                import unicodedata, re

                def norm_text_query(t: str) -> str:
                    txt = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8')
                    return re.sub(r'[^a-z0-9\s]', '', txt.lower()).strip()

                stopwords = {
                    'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das',
                    'no', 'na', 'em', 'para', 'com', 'como'
                }
                
                # CORREÇÃO 3: Lendo a variável de busca do Manual
                termo_norm = norm_text_query(termo_busca_manual)
                fatias = [p for p in termo_norm.split() if p not in stopwords and len(p) > 2]

                # Criamos a coluna de score zerada por padrão (Programação Defensiva)
                df_m['score'] = 0

                if fatias:
                    def calcular_score(row):
                        score = 0
                        # Cast para string (str) garantindo que nulos do banco não quebrem o in
                        tit = str(row.get('titulo_norm', ''))
                        cat = str(row.get('categoria_norm', ''))
                        cont = str(row.get('conteudo_norm', ''))
                        
                        for f in fatias:
                            if f in tit:
                                score += 3
                            if f in cat:
                                score += 2
                            if f in cont:
                                score += 1
                        return score

                    # CORREÇÃO 4: Aplicando a matemática no DataFrame correto (df_m)
                    df_m['score'] = df_m.apply(calcular_score, axis=1)
                    df_m = df_m[df_m['score'] > 0].sort_values(by='score', ascending=False)

            st.markdown("<br>", unsafe_allow_html=True)
            
            # --- EXIBIÇÃO DO RANKING/PESQUISA ---
            if btn_buscar_manual and termo_busca_manual.strip() and df_m.empty:
                st.warning(f"Nenhum manual encontrado para as palavras-chave: **'{termo_busca_manual}'**.")
            elif btn_buscar_manual and termo_busca_manual.strip():
                st.markdown(f"**📖 Resultados Encontrados ({len(df_m)}) - Ordenados por relevância**")
                for _, row in df_m.head(20).iterrows():
                    titulo = row.get('titulo', 'Sem Título')
                    conteudo = row.get('conteudo', 'Nenhum conteúdo disponível.')
                    anexo = row.get('caminho_anexo', '')
                    
                    # CORREÇÃO 5: Programação Defensiva, se o score não existir, usa 0.
                    valor_score = row.get('score', 0)
                    tag_score = f"⭐ Score: {valor_score}"
                    
                    with st.expander(f"📖 {titulo} {tag_score}"):
                        st.markdown(conteudo)
                        if pd.notna(anexo) and str(anexo).strip() and os.path.exists(str(anexo)):
                            with open(anexo, "rb") as f:
                                st.download_button("📎 Baixar Anexo", f, file_name=os.path.basename(str(anexo)), key=f"dl_man_busca_{row.get('id', titulo)}")
            else:
                # UX REFINADA: Ao invés de listar 500 itens de uma vez (Lag), usamos um Selectbox
                st.markdown("#### 📁 Navegação por Categorias")
                categorias = df_m['categoria'].fillna('Geral').unique()
                
                cat_selecionada = st.selectbox(
                    "Filtre por uma categoria para explorar os manuais:", 
                    ["Selecione uma categoria..."] + list(sorted(categorias)),
                    key="filtro_cat_manual_ux"
                )
                
                if cat_selecionada != "Selecione uma categoria...":
                    df_cat = df_m[df_m['categoria'] == cat_selecionada]
                    st.caption(f"A mostrar {len(df_cat)} manuais da categoria: **{cat_selecionada}**")
                    
                    for _, row in df_cat.iterrows():
                        titulo = row.get('titulo', 'Sem Título')
                        with st.expander(f"📖 {titulo}"):
                            st.markdown(row.get('conteudo', ''))
                            anexo = row.get('caminho_anexo', '')
                            if pd.notna(anexo) and str(anexo).strip() and os.path.exists(str(anexo)):
                                with open(anexo, "rb") as f:
                                    st.download_button("📎 Baixar Anexo", f, file_name=os.path.basename(str(anexo)), key=f"dl_man_def_{row.get('id', titulo)}")

                
               
# ==========================================
# ABA 5: HISTÓRICO E RANKING DA EQUIPE
# ==========================================
with aba_arquivo:
    hist_limit_key = "historico_buscas_limite"
    if hist_limit_key not in st.session_state:
        st.session_state[hist_limit_key] = 10

    st.subheader("📖 Histórico e Ranking da Equipe")
    st.caption(
        "Histórico agrupa por **tema** (mesma dúvida em palavras diferentes = um bloco). "
        "Ranking mostra **o que mais gera dúvida** na equipe, sem repetir variações do mesmo assunto."
    )
    col_hist, col_rank = st.columns([2, 1])

    with col_hist:
        st.markdown("#### 🔍 Últimas buscas por tema (quem / quando)")
        df_recentes = pd.DataFrame()
        if _busca_sem_ok and historico_por_topico_recente:
            try:
                recentes = historico_por_topico_recente(engine, int(st.session_state[hist_limit_key]))
                df_recentes = pd.DataFrame(recentes) if recentes else pd.DataFrame()
            except Exception:
                df_recentes = pd.DataFrame()
        if df_recentes.empty:
            with engine.connect() as conn:
                query_recentes = text(
                    """
                    SELECT pergunta, resposta_ia, nome, data_busca FROM (
                        SELECT DISTINCT ON (lower(h.pergunta))
                            h.pergunta, h.resposta_ia, u.nome,
                            to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') as data_busca, h.criado_em
                        FROM historico_buscas_psy h
                        LEFT JOIN usuarios u ON h.usuario_id = u.id
                        ORDER BY lower(h.pergunta), h.criado_em DESC
                    ) sub ORDER BY criado_em DESC LIMIT :limite
                    """
                )
                df_recentes = pd.read_sql(
                    query_recentes,
                    conn,
                    params={"limite": int(st.session_state[hist_limit_key])},
                )
        if not df_recentes.empty:
            for idx, row in df_recentes.iterrows():
                nome_autor = row.get("nome") or row.get("Nome") or "Membro da Equipe"
                pergunta = row.get("pergunta") or row.get("Pergunta") or ""
                quando = row.get("quando") or row.get("data_busca") or ""
                assunto = row.get("assunto") or pergunta[:80]
                resposta = row.get("resposta_ia") or row.get("Resposta") or ""
                titulo = f"👤 {nome_autor} — {quando} — **{str(assunto)[:70]}…**"
                with st.expander(titulo):
                    st.caption(f"Pergunta registrada: {pergunta}")
                    st.markdown(resposta)
            if len(df_recentes) == int(st.session_state[hist_limit_key]):
                if st.button("📥 Carregar mais 20 (Histórico)", key="btn_hist_load_more", use_container_width=True):
                    st.session_state[hist_limit_key] += 20
                    st.rerun()
        else:
            st.info("Ainda não há registros de buscas ao Psy.")

    with col_rank:
        st.markdown("#### 🏆 Top 5 assuntos")
        df_ranking_buscas = pd.DataFrame()
        if _busca_sem_ok and ranking_topicos_agregado:
            try:
                # Assistente + Wiki + Manual no mesmo ranking global (soma por tópico já está em busca_topicos por origem)
                # Unimos os três origens num único "volume" por label seria duplicado; melhor: top ASSISTENTE + mesclar
                ra = ranking_topicos_agregado(engine, "ASSISTENTE", 5)
                rw = ranking_topicos_agregado(engine, "WIKI", 5)
                rm = ranking_topicos_agregado(engine, "MANUAL", 5)
                merged = {}
                for label, n in ra + rw + rm:
                    merged[label] = merged.get(label, 0) + n
                top = sorted(merged.items(), key=lambda x: -x[1])[:5]
                df_ranking_buscas = pd.DataFrame(top, columns=["Assunto (tema)", "Total buscas"])
            except Exception:
                df_ranking_buscas = pd.DataFrame()
        if df_ranking_buscas.empty:
            with engine.connect() as conn:
                query_ranking_buscas = text(
                    'SELECT INITCAP(lower(pergunta)) as "Assunto", COUNT(id) as "Volume" '
                    "FROM historico_buscas_psy GROUP BY lower(pergunta) ORDER BY \"Volume\" DESC LIMIT 5"
                )
                df_ranking_buscas = pd.read_sql(query_ranking_buscas, conn)
        if not df_ranking_buscas.empty:
            st.dataframe(df_ranking_buscas, width="stretch", hide_index=True)


# ==========================================
# ABA 6: NOVA CONTRIBUIÇÃO (INSERÇÃO MANUAL)
# ==========================================
with aba_nova:
    st.markdown("### 📝 Adicionar Nova Contribuição")
    
    with st.form("form_contribuicao", clear_on_submit=True):
        titulo = st.text_input("📌 Título", placeholder="Título claro e objetivo")
        
        col_menu, col_modalidade, col_data = st.columns([1, 1, 1])

        with col_menu:
            menu = st.selectbox(
                "📂 Menu",
                list(menus.keys())
            )

        # with col_submenu:
        #     submenu = st.selectbox(
        #         "📁 Submenu",
        #         list(menus[menu].keys())
        #     )

        # subsubmenus = menus[menu][submenu]

        # with col_subsubmenu:
        #     if subsubmenus:
        #         subsubmenu = st.selectbox(
        #             "📄 Sub-submenu",
        #             subsubmenus
        #         )
        #     else:
        #         subsubmenu = None

        with col_modalidade:
            modalidade_rotulo = st.selectbox(
                "🏷️ Tipo da Contribuição",
                options=["🟢 Evento Atual", "🕘 Evento Passado"],
                index=0,
                help=(
                    "Evento Atual: pontua por prazo (0-7 dias: 100, 8-14: 75, 15-21: 25, >21: 0). "
                    "Evento Passado: valor fixo de 90 XP quando aprovado."
                ),
            )
            modalidade_contribuicao = (
                "EVENTO_ATUAL"
                if modalidade_rotulo == "🟢 Evento Atual"
                else "EVENTO_PASSADO"
            )

        with col_data:
            data_evento = st.date_input(
                "📅 Data do Ocorrido",
                help="Quanto mais recente o registro em relação ao fato, mais XP você ganha!"
            )
        
        conteudo = st.text_area("📝 Conteúdo", height=250, placeholder="Descrição detalhada...")
        
        st.markdown("---")
        st.markdown("📎 **Anexar Evidências**")
        
        arquivo_anexo = st.file_uploader(
            "Formatos aceitos: PDF, TXT, SQL, Imagens, Vídeos...",
            type=["pdf", "txt", "csv", "xlsx", "xls", "xml", "sql", "png", "jpg", "jpeg", "pgz", "fr3", "mp3", "mp4"],
            accept_multiple_files=True,
        )
        
        btn_salvar = st.form_submit_button("💾 Salvar Contribuição", type="primary")
        
        if btn_salvar:
            if len(arquivo_anexo) > MAX_ANEXOS_CONTRIBUICAO:
                st.error(f"Máximo de {MAX_ANEXOS_CONTRIBUICAO} anexos por contribuição.")
                st.stop()
            if not titulo or not menu or not conteudo or not data_evento:
                st.warning("⚠️ Preencha Título, Menu (categoria), Conteúdo e Data do Ocorrido.")
            else:
                # Processamento de anexo (Mantive sua lógica original)
                texto_extraido = ""
                caminho_anexo_db = None
                if arquivo_anexo:
                    with st.spinner("Processando anexos..."):
                        timestamp = int(time.time())
                        # pasta dedicada para os arquivos desta contribuição
                        safe_base = re.sub(r'[^a-zA-Z0-9_-]', '_', (titulo or 'contribuicao'))
                        pasta_contrib = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_base}")
                        os.makedirs(pasta_contrib, exist_ok=True)
                        arquivos_salvos = []
                        for idx, arquivo in enumerate(arquivo_anexo, start=1):
                            try:
                                if len(arquivo.getvalue()) > MAX_BYTES_ANEXO_CONTRIBUICAO:
                                    st.error(
                                        f"Anexo '{arquivo.name}' excede o limite de "
                                        f"{MAX_BYTES_ANEXO_CONTRIBUICAO / 1024 / 1024:.0f} MB."
                                    )
                                    st.stop()
                            except Exception:
                                pass
                            nome_original = os.path.basename(str(arquivo.name or f"anexo_{idx}"))
                            nome_seguro = re.sub(r"[^A-Za-z0-9._-]", "_", nome_original).strip("._")
                            if not nome_seguro:
                                nome_seguro = f"anexo_{idx}"
                            nome_seguro = f"{idx}_{nome_seguro[:112]}"
                            caminho_fisico = os.path.join(pasta_contrib, nome_seguro)
                            with open(caminho_fisico, "wb") as f:
                                f.write(arquivo.getbuffer())
                            arquivos_salvos.append((caminho_fisico, arquivo))
                            # Extração de texto (quando aplicável) para enriquecer o conteúdo
                            ext = nome_seguro.rsplit(".", 1)[-1].lower()
                            try:
                                if ext in ['txt', 'sql', 'xml', 'csv']:
                                    texto_extraido += arquivo.getvalue().decode('utf-8', errors='ignore') + "\n\n"
                                elif ext == 'pdf':
                                    import pypdf
                                    pdf_reader = pypdf.PdfReader(arquivo)
                                    texto_extraido += " ".join(
                                        [p.extract_text() for p in pdf_reader.pages if p.extract_text()]
                                    ) + "\n\n"
                                elif ext in ['xlsx', 'xls']:
                                    import pandas as pd
                                    texto_extraido += pd.read_excel(arquivo).to_string() + "\n\n"
                            except Exception as e:
                                st.warning(f"Texto não extraído de {arquivo.name}: {e}")
                        # Empacota todos os anexos em um único ZIP para manter compatibilidade com o campo caminho_anexo
                        zip_path = os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_base}.zip")
                        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                            for caminho_fisico, arquivo in arquivos_salvos:
                                zf.write(caminho_fisico, arcname=os.path.basename(caminho_fisico))
                        caminho_anexo_db = zip_path

                conteudo_final = conteudo.strip()
                if texto_extraido:
                    conteudo_final += f"\n\n--- CONTEÚDO DO ANEXO ---\n{texto_extraido}"
                
                try:
                    with engine.begin() as conn:
                        status_inicial = "APROVADO" if perfil_logado == "admin" else "PENDENTE"
                        categoria_final = menu.strip().upper()
                        subcategoria_final = "GERAL"

                        if status_inicial == "APROVADO":
                            agora = datetime.now(timezone.utc)
                            xp_res = computar_xp_aprovacao(
                                conn,
                                autor_id=int(usuario_logado_id),
                                exclude_contribuicao_id=None,
                                modalidade=modalidade_contribuicao,
                                data_ocorrido=data_evento,
                                criado_em=agora,
                                era_revisao_pendente=False,
                            )
                            ins = conn.execute(
                                text("""
                                    INSERT INTO base_conhecimento
                                    (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor,
                                     status, caminho_anexo, qtd_tentativas, data_ocorrido,
                                     pontos_contribuicao, data_avaliacao, id_avaliador, modalidade_contribuicao)
                                    VALUES ('CONHECIMENTO_SUPORTE', :t, :c, :s, :co, :a, :st, :ax, 1, :do,
                                            :pts, CURRENT_TIMESTAMP, :av, :mod)
                                    RETURNING id
                                """),
                                {
                                    "t": titulo.strip(),
                                    "c": categoria_final,
                                    "s": subcategoria_final,
                                    "co": conteudo_final,
                                    "a": usuario_logado_id,
                                    "st": status_inicial,
                                    "ax": caminho_anexo_db,
                                    "do": data_evento,
                                    "pts": xp_res.pontos_contribuicao,
                                    "av": usuario_logado_id,
                                    "mod": modalidade_contribuicao,
                                },
                            )
                            novo_id = ins.scalar_one()
                            registrar_bonus_semanal_contribuicao(
                                conn, int(novo_id), int(usuario_logado_id), xp_res
                            )
                        else:
                            conn.execute(
                                text("""
                                    INSERT INTO base_conhecimento
                                    (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor,
                                     status, caminho_anexo, qtd_tentativas, data_ocorrido, modalidade_contribuicao)
                                    VALUES ('CONHECIMENTO_SUPORTE', :t, :c, :s, :co, :a, :st, :ax, 1, :do, :mod)
                                """),
                                {
                                    "t": titulo.strip(),
                                    "c": categoria_final,
                                    "s": subcategoria_final,
                                    "co": conteudo_final,
                                    "a": usuario_logado_id,
                                    "st": status_inicial,
                                    "ax": caminho_anexo_db,
                                    "do": data_evento,
                                    "mod": modalidade_contribuicao,
                                },
                            )
                    
                    # UX: Feedback elegante conforme solicitado
                    st.toast("✅ Contribuição enviada! Seu XP será atualizado após a aprovação.", icon="🚀")
                    show_gamification_upgrade_card(
                        "Contribuição registrada",
                        "Excelente! Sua contribuição foi enviada para o fluxo de conhecimento.",
                    )
                    
                    try:
                        registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}")
                    except NameError: pass
                    
                except Exception as e:
                    st.error(f"❌ Erro ao salvar: {str(e)}")

# ==========================================
# ABA 7: MINHAS CONTRIBUIÇÕES (editar/excluir: pendente, rejeitado, obsoleto; aprovado só leitura)
# ==========================================
def _icone_status(sts: str) -> str:
    if sts == "APROVADO":
        return "🟢"
    if sts == "PENDENTE" or sts == "REVISAO_PENDENTE":
        return "🟡"
    if sts == "OBSOLETO":
        return "🟠"
    if sts == "REJEITADO":
        return "🔴"
    return "⚪"


with aba_minhas:
    st.subheader("📚 Minhas Contribuições")
    st.caption(
        "Você pode **editar ou excluir** contribuições **Pendentes**, **Rejeitadas** ou **Obsoletas**. "
        "**Aprovadas** não podem ser alteradas até alguém marcar como obsoleta."
    )
    with engine.connect() as conn:
        query_minhas = text("""
            SELECT id, titulo, categoria, subcategoria, status, motivo_rejeicao, conteudo, caminho_anexo,
                   COALESCE(qtd_tentativas, 1) AS qtd_tentativas
            FROM base_conhecimento
            WHERE origem = 'CONHECIMENTO_SUPORTE' AND id_analista_autor = :a
            ORDER BY criado_em DESC
        """)
        df_minhas = pd.read_sql(query_minhas, conn, params={"a": usuario_logado_id})

    obsoletas = df_minhas[df_minhas["status"].astype(str).str.upper() == "OBSOLETO"] if not df_minhas.empty else pd.DataFrame()
    if not obsoletas.empty:
        st.warning(
            f"**📢 Atenção:** {len(obsoletas)} contribuição(ões) sua(s) foram marcadas como **OBSOLETAS**. "
            "Atualize o conteúdo e reenvie para a fila de avaliação."
        )

    if not df_minhas.empty:
        for _, row in df_minhas.iterrows():
            sts = str(row["status"]).upper()
            cor = _icone_status(sts)
            with st.expander(f"{cor} {row['titulo']} (Status: {sts})"):
                st.write(f"**Categoria:** `{row['categoria']}` ➔ `{row['subcategoria']}`")
                st.caption(f"🔄 Tentativas na fila: {row.get('qtd_tentativas', 1)}")

                if row["caminho_anexo"] and os.path.exists(row["caminho_anexo"]):
                    with open(row["caminho_anexo"], "rb") as f:
                        st.download_button(
                            "📎 Anexo",
                            f,
                            file_name=os.path.basename(row["caminho_anexo"]),
                            key=f"dl_m_{row['id']}",
                        )

                # --- APROVADO: só leitura (não some daqui; na Explorar continua público) ---
                if sts == "APROVADO":
                    st.success("Publicada na base. Não é possível editar enquanto estiver aprovada.")
                    st.write(row["conteudo"])
                    continue

                # --- OBSOLETO: aviso + edição → PENDENTE ---
                if sts == "OBSOLETO":
                    st.error(
                        f"**⚠️ Marcada como obsoleta.** Orientação: {row.get('motivo_rejeicao') or 'Atualize o conteúdo conforme o processo atual.'}"
                    )
                    st.info("Após salvar, a contribuição volta para a **fila de avaliação** (status Pendente).")

                # --- REJEITADO ---
                if sts == "REJEITADO":
                    st.error(f"**Motivo da rejeição:** {row.get('motivo_rejeicao') or '—'}")

                # --- PENDENTE / REVISAO_PENDENTE ---
                if sts in ("PENDENTE", "REVISAO_PENDENTE"):
                    st.info("Aguardando avaliação. Você ainda pode ajustar o texto ou excluir antes da aprovação.")

                # Editar + excluir: PENDENTE, REJEITADO, OBSOLETO, REVISAO_PENDENTE
                if sts in ("PENDENTE", "REJEITADO", "OBSOLETO", "REVISAO_PENDENTE"):
                    with st.form(key=f"form_edit_{row['id']}"):
                        novo_titulo = st.text_input("Título:", value=row["titulo"], key=f"t_{row['id']}")
                        novo_conteudo = st.text_area("Conteúdo:", value=row["conteudo"], height=220, key=f"c_{row['id']}")
                        c1, c2 = st.columns(2)
                        with c1:
                            salvar = st.form_submit_button("💾 Salvar e enviar à fila", type="primary")
                        with c2:
                            excluir = st.form_submit_button("🗑️ Excluir definitivamente")
                        if salvar:
                            try:
                                with engine.begin() as conn_upd:
                                    conn_upd.execute(
                                        text("""
                                            UPDATE base_conhecimento
                                            SET titulo = :t, conteudo = :c, status = 'PENDENTE',
                                                motivo_rejeicao = NULL,
                                                qtd_tentativas = COALESCE(qtd_tentativas, 1) + 1
                                            WHERE id = :id AND id_analista_autor = :a
                                              AND status IN ('PENDENTE','REJEITADO','OBSOLETO','REVISAO_PENDENTE')
                                        """),
                                        {
                                            "t": novo_titulo.strip(),
                                            "c": novo_conteudo.strip(),
                                            "id": int(row["id"]),
                                            "a": usuario_logado_id,
                                        },
                                    )
                                st.success("Enviado à fila de avaliação.")
                               
                            except Exception as e:
                                st.error(f"Erro ao salvar: {e}")
                        if excluir:
                            try:
                                with engine.begin() as conn_del:
                                    conn_del.execute(
                                        text(
                                            "DELETE FROM base_conhecimento WHERE id = :id AND id_analista_autor = :a "
                                            "AND status IN ('PENDENTE','REJEITADO','OBSOLETO','REVISAO_PENDENTE')"
                                        ),
                                        {"id": int(row["id"]), "a": usuario_logado_id},
                                    )
                                st.success("Contribuição excluída.")
                                
                               
                            except Exception as e:
                                st.error(f"Erro ao excluir: {e}")
                else:
                    st.write(row["conteudo"])
    else:
        st.info("Nenhuma contribuição sua encontrada. Participe e ganhe pontos no ranking!")

# ==========================================
# ABA 8: FILA DE AVALIAÇÃO (Apenas Coordenadores e Desenvolvedores)
# ==========================================
if perfil_logado == "admin":
    with aba_fila:
        st.subheader("⚖️ Fila de Controle de Qualidade (QA)")
        st.markdown("Avalie as contribuições pendentes. Garanta que o conhecimento salvo siga os padrões técnicos.")
        
        with engine.connect() as conn:
            # Trazendo dados cruzados do autor, data e contador
            query_fila = text("""
                SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo, b.qtd_tentativas,
                       COALESCE(NULLIF(b.modalidade_contribuicao, ''), 'EVENTO_ATUAL') AS modalidade_contribuicao,
                       to_char(b.criado_em, 'DD/MM/YYYY às HH24:MI') as data_envio, u.nome AS autor 
                FROM base_conhecimento b 
                JOIN usuarios u ON b.id_analista_autor = u.id 
                WHERE b.origem = 'CONHECIMENTO_SUPORTE'
                  AND b.status IN ('PENDENTE', 'REVISAO_PENDENTE')
                ORDER BY b.criado_em ASC
            """)
            df_fila = pd.read_sql(query_fila, conn)
            
        if not df_fila.empty:
            for _, row in df_fila.iterrows():
                # Tag de alerta se já foi para a fila várias vezes
                tentativas = row.get('qtd_tentativas', 1)
                alerta_tentativas = f" 🚨 ({tentativas}ª Tentativa)" if tentativas > 1 else ""
                
                with st.expander(f"⏳ {row['titulo']} - {row['autor']}{alerta_tentativas}"):
                    modalidade = str(row.get("modalidade_contribuicao") or "EVENTO_ATUAL").strip().upper()
                    modalidade_badge = "🟢 Evento Atual" if modalidade == "EVENTO_ATUAL" else "🕘 Evento Passado"
                    st.markdown(f"**👤 Autor:** {row['autor']} | **📅 Enviado em:** {row['data_envio']}")
                    st.markdown(
                        f"**📂 Classificação:** `{row['categoria']}` ➔ `{row['subcategoria']}` | "
                        f"**🏷️ Modalidade:** `{modalidade_badge}`"
                    )
                    st.divider()
                    
                    st.markdown("#### 📖 Conteúdo Proposto:")
                    st.info(row['conteudo'])
                    
                    if row['caminho_anexo'] and os.path.exists(row['caminho_anexo']):
                        with open(row['caminho_anexo'], "rb") as f:
                            st.download_button("📎 Ver Anexo Original", f, file_name=os.path.basename(row['caminho_anexo']), key=f"dl_fila_{row['id']}")
                    
                    st.divider()
                    st.markdown("#### ⚖️ Decisão do Avaliador")
                    c1, c2 = st.columns([1, 2])
                    
                    with c1:
                        if st.button("✅ Aprovar e Publicar", key=f"apr_{row['id']}", type="primary", width='stretch'):
                            try:
                                with engine.begin() as conn_apr:
                                    aprovar_contribuicao_conhecimento(
                                        conn_apr,
                                        int(row["id"]),
                                        int(usuario_logado_id),
                                    )
                                registrar_log_auditoria(
                                    usuario_logado_id,
                                    "APROVOU_CONTRIBUICAO",
                                    f"Aprovou ID: {row['id']}",
                                )
                                st.success("Documento homologado e publicado na Base!")
                            except AprovacaoContribuicaoError as e:
                                st.error(str(e))
                            except Exception as e:
                                st.error(f"Erro ao aprovar: {e}")
                    with c2:
                        motivo = st.text_input("Feedback / Motivo da Rejeição (Obrigatório caso rejeite):", key=f"mot_{row['id']}", placeholder="Ex: Faltou print do erro; formatação ruim...")
                        if st.button("❌ Rejeitar e Devolver ao Autor", key=f"rej_{row['id']}", width='stretch'):
                            if not motivo.strip():
                                st.warning("⚠️ Você deve escrever um motivo claro para o analista entender o que precisa corrigir.")
                            else:
                                try:
                                    with engine.begin() as conn_rej: 
                                        conn_rej.execute(text("UPDATE base_conhecimento SET status = 'REJEITADO', motivo_rejeicao = :m WHERE id = :id"), {"m": motivo.strip(), "id": row['id']})
                                    registrar_log_auditoria(usuario_logado_id, "REJEITOU_CONTRIBUICAO", f"Rejeitou ID: {row['id']}")
                                    st.success("Devolvido ao autor para correções!")
                                except Exception as e:
                                    st.error(f"Erro ao rejeitar: {e}")
        else: 
            st.success("🎉 A fila de Qualidade está limpa! Nenhuma contribuição pendente no momento.")


# ==========================================
with aba_explorar:
    usuario_id = st.session_state.get('usuario_id') or st.session_state.get('usuario_logado_id')

    if not usuario_id:
        st.error("⚠️ Erro: Usuário não identificado. Por favor, faça login novamente.")
        st.stop()

    st.title("🔎 Explorar Base de Conhecimento")

    limite_state_key = "explorar_conhecimento_limite"
    filtros_state_key = "explorar_conhecimento_filtros"

    if limite_state_key not in st.session_state:
        st.session_state[limite_state_key] = 5

    with st.container(border=True):
        st.markdown("#### 🎯 Filtros de Pesquisa")
        try:
            with engine.connect() as conn:
                cat_query = text(
                    "SELECT DISTINCT categoria FROM base_conhecimento "
                    "WHERE status IN ('APROVADO','OBSOLETO') AND origem = 'CONHECIMENTO_SUPORTE' ORDER BY categoria"
                )
                categorias_disponiveis = [row[0] for row in conn.execute(cat_query).fetchall() if row[0]]
                aut_query = text(
                    """
                    SELECT DISTINCT COALESCE(u.nome, 'Não informado') AS autor
                    FROM base_conhecimento b
                    LEFT JOIN usuarios u ON b.id_analista_autor = u.id
                    WHERE b.status IN ('APROVADO','OBSOLETO') AND b.origem = 'CONHECIMENTO_SUPORTE'
                    ORDER BY autor
                    """
                )
                autores_disponiveis = [row[0] for row in conn.execute(aut_query).fetchall() if row[0]]
        except Exception:
            categorias_disponiveis = []
            autores_disponiveis = []

        categorias_disponiveis = ["Todas as Categorias"] + categorias_disponiveis
        autores_disponiveis = ["Todos os autores"] + autores_disponiveis

        col_assunto, col_categoria = st.columns(2)
        with col_assunto:
            assunto = st.text_input(
                "Assunto (título ou conteúdo)",
                placeholder="Ex: Erro de impressão em NFC-e",
            )
        with col_categoria:
            categoria_selecionada = st.selectbox("Categoria", categorias_disponiveis)

        col_autor, col_data_ini, col_data_fim = st.columns([1.4, 1, 1])
        with col_autor:
            autor_selecionado = st.selectbox("Autor", autores_disponiveis)
        with col_data_ini:
            data_inicial = st.date_input("Data inicial", value=None)
        with col_data_fim:
            data_final = st.date_input("Data final", value=None)

        filtros_atuais = (
            (assunto or "").strip().lower(),
            categoria_selecionada,
            autor_selecionado,
            data_inicial.isoformat() if data_inicial else "",
            data_final.isoformat() if data_final else "",
        )
        if st.session_state.get(filtros_state_key) != filtros_atuais:
            st.session_state[filtros_state_key] = filtros_atuais
            st.session_state[limite_state_key] = 5

    params = {"uid": usuario_id}
    query_base = """
        SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo,
               COALESCE(b.qtd_upvotes, 0) as qtd_upvotes,
               COALESCE(b.qtd_visualizacoes, 0) as qtd_visualizacoes,
               to_char(b.criado_em, 'DD/MM/YYYY') as data_pub,
               COALESCE(u.nome, 'Não informado') AS autor,
               b.status as status_row,
               EXISTS(SELECT 1 FROM base_conhecimento_votos v
                      WHERE v.id_conhecimento = b.id AND v.id_analista_votante = :uid) as ja_curtiu
        FROM base_conhecimento b
        LEFT JOIN usuarios u ON b.id_analista_autor = u.id
        WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status IN ('APROVADO', 'OBSOLETO')
    """

    if (assunto or "").strip():
        query_base += " AND (b.titulo ILIKE :termo OR b.conteudo ILIKE :termo)"
        params["termo"] = f"%{assunto.strip()}%"

    if categoria_selecionada != "Todas as Categorias":
        query_base += " AND b.categoria = :cat"
        params["cat"] = categoria_selecionada

    if autor_selecionado != "Todos os autores":
        query_base += " AND COALESCE(u.nome, 'Não informado') = :autor"
        params["autor"] = autor_selecionado

    if data_inicial:
        query_base += " AND DATE(b.criado_em) >= :data_ini"
        params["data_ini"] = data_inicial

    if data_final:
        query_base += " AND DATE(b.criado_em) <= :data_fim"
        params["data_fim"] = data_final

    query_base += " ORDER BY b.criado_em DESC LIMIT :limite"
    params["limite"] = int(st.session_state[limite_state_key])

    try:
        with engine.connect() as conn:
            df_conhecimento = pd.read_sql(text(query_base), conn, params=params)

        if df_conhecimento.empty:
            st.info("📭 Nenhuma contribuição encontrada com os filtros atuais.")
        else:
            st.caption(
                f"Exibindo {len(df_conhecimento)} contribuições mais recentes "
                f"(limite atual: {st.session_state[limite_state_key]})."
            )
            nome_marcador = st.session_state.get("usuario_nome") or "Equipe"
            for _, row in df_conhecimento.iterrows():
                is_obsoleto = str(row.get("status_row", "")).upper() == "OBSOLETO"
                with st.container(border=True):
                    col_txt, col_btn = st.columns([4, 1.2])

                    with col_txt:
                        badge = " **🟠 OBSOLETA — aguardando atualização do autor**" if is_obsoleto else ""
                        st.markdown(f"### {row['titulo']}{badge}")
                        st.caption(f"📂 {row['categoria']} | ✍️ {row['autor']} | 📅 {row['data_pub']}")
                        if is_obsoleto and row.get("conteudo"):
                            st.caption("Conteúdo ainda visível; não entra no assistente até ser reavaliada.")

                    with col_btn:
                        if not is_obsoleto:
                            label = f"❤️ {row['qtd_upvotes']}" if row["ja_curtiu"] else f"🤍 {row['qtd_upvotes']}"
                            if st.button(label, key=f"lk_{row['id']}", use_container_width='stretch'):
                                with engine.begin() as conn_voto:
                                    if row["ja_curtiu"]:
                                        conn_voto.execute(
                                            text(
                                                "DELETE FROM base_conhecimento_votos WHERE id_conhecimento = :pid AND id_analista_votante = :uid"
                                            ),
                                            {"pid": row["id"], "uid": usuario_id},
                                        )
                                        conn_voto.execute(
                                            text(
                                                "UPDATE base_conhecimento SET qtd_upvotes = qtd_upvotes - 1 WHERE id = :pid AND qtd_upvotes > 0"
                                            ),
                                            {"pid": row["id"]},
                                        )
                                    else:
                                        conn_voto.execute(
                                            text(
                                                "INSERT INTO base_conhecimento_votos (id_conhecimento, id_analista_votante) VALUES (:pid, :uid)"
                                            ),
                                            {"pid": row["id"], "uid": usuario_id},
                                        )
                                        conn_voto.execute(
                                            text(
                                                "UPDATE base_conhecimento SET qtd_upvotes = COALESCE(qtd_upvotes, 0) + 1 WHERE id = :pid"
                                            ),
                                            {"pid": row["id"]},
                                        )
                                st.rerun()
                        else:
                            st.caption("Votos pausados (obsoleta).")

                        # Marcar obsoleto: só APROVADO; coord/dev (evita abuso)
                        if perfil_logado == "admin" and not is_obsoleto:
                            with st.expander("⚠️ Marcar obsoleta", expanded=False):
                                motivo_obs = st.text_input(
                                    "Motivo / o que o autor deve atualizar",
                                    key=f"mot_obs_{row['id']}",
                                    placeholder="Ex.: Procedure mudou na v2.9; incluir novo print",
                                )
                                if st.button("Confirmar obsoleta + avisar autor", key=f"obs_{row['id']}", use_container_width='stretch'):
                                    if not (motivo_obs or "").strip():
                                        st.warning("Informe um motivo para o autor.")
                                    else:
                                        agora = datetime.now().strftime("%d/%m/%Y %H:%M")
                                        texto_motivo = f"[Obsoleta em {agora} por {nome_marcador}] {motivo_obs.strip()}"
                                        try:
                                            ra = None
                                            with engine.begin() as conn_obs:
                                                ra = conn_obs.execute(
                                                    text(
                                                        "SELECT u.email, u.nome FROM base_conhecimento b JOIN usuarios u ON b.id_analista_autor = u.id WHERE b.id = :pid"
                                                    ),
                                                    {"pid": row["id"]},
                                                ).fetchone()
                                                conn_obs.execute(
                                                    text(
                                                        "UPDATE base_conhecimento SET status = 'OBSOLETO', motivo_rejeicao = :m WHERE id = :pid AND status = 'APROVADO'"
                                                    ),
                                                    {"m": texto_motivo, "pid": row["id"]},
                                                )
                                            if ra:
                                                _notificar_email_obsoleto(
                                                    ra[0], ra[1], row["titulo"], nome_marcador, motivo_obs.strip()
                                                )
                                            try:
                                                registrar_log_auditoria(
                                                    usuario_logado_id,
                                                    "MARCOU_OBSOLETO",
                                                    f"id={row['id']} {row['titulo'][:40]}",
                                                )
                                            except Exception:
                                                pass
                                            st.success("Marcada como obsoleta. O autor foi avisado (e-mail, se configurado).")
                                        
                                            
                                        except Exception as e:
                                            st.error(f"Erro: {e}")

                    with st.expander("📖 Ler solução"):
                        view_key = f"viewed_{row['id']}"
                        if view_key not in st.session_state:
                            with engine.begin() as conn_view:
                                conn_view.execute(
                                    text(
                                        "UPDATE base_conhecimento "
                                        "SET qtd_visualizacoes = COALESCE(qtd_visualizacoes, 0) + 1 "
                                        "WHERE id = :pid"
                                    ),
                                    {"pid": row['id']},
                                )
                            st.session_state[view_key] = True
                        st.markdown(row['conteudo'])

            if len(df_conhecimento) == st.session_state[limite_state_key]:
                if st.button("📥 Carregar mais 20", use_container_width=True, key="btn_carregar_mais_explorar"):
                    st.session_state[limite_state_key] += 20
                    st.rerun()
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")