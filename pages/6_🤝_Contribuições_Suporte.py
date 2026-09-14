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
    lock_aprovacao_autor,
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
from services.auth_guard import require_login
from services.perfil_usuario import normalizar_perfil_para_sessao
from services.ui_realtime import show_gamification_upgrade_card
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

# Exige login (com restauração de sessão via cookie num F5 direto na página).
require_login()

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


# ==========================================
# 3. TÍTULO E DESCRIÇÃO
# ==========================================
st.title("🧠 Base de Conhecimento")
st.caption("Respostas rápidas, manuais do PostoGestor, wikis do HelpDesk e a Base de Conhecimento colaborativa em um só lugar.")
with st.expander("📋 Regras de contribuições e penalidades", expanded=False):
    st.caption("Guia rápido para pontuação, bônus e descontos semanais.")
    render_contrib_rules_table(compact=True)


# ==========================================
# 4. DEFINIÇÃO DAS ABAS (Nova Ordem de UX)
# ==========================================
ABA_RANKING = "🏅 Início & Ranking"
ABA_BUSCA = "🔎 Buscar na Base de Conhecimento"
ABA_HISTORICO = "📖 Histórico de Buscas"
ABA_NOVA = "📝 Adicionar Contribuição"
ABA_FILA = "⚖️ Fila de Avaliação"
ABA_MINHAS = "📚 Minhas Contribuições"

# ``st.tabs`` reinicia sempre para a primeira aba a cada rerun (inclusive ao apertar
# Enter num campo de texto ou clicar em qualquer botão dentro da própria aba — bug
# conhecido do Streamlit, https://github.com/streamlit/streamlit/issues/12554).
# ``st.segmented_control`` com ``key`` guarda a seleção em session_state como
# qualquer outro widget, então a navegação não pula de volta ao clicar em nada.
labels_abas = [ABA_RANKING, ABA_BUSCA, ABA_HISTORICO, ABA_NOVA]
if perfil_logado == "admin":
    labels_abas += [ABA_FILA, ABA_MINHAS]
else:
    labels_abas += [ABA_MINHAS]

aba_ativa = st.segmented_control(
    "Navegação",
    labels_abas,
    default=labels_abas[0],
    key="cs_aba_ativa",
    label_visibility="collapsed",
    required=True,
)
if aba_ativa not in labels_abas:
    aba_ativa = labels_abas[0]
st.divider()

# ==========================================
# ABA 1: GAMIFICAÇÃO E RANKING (Sincronizado com Trigger)
# ==========================================
if aba_ativa == ABA_RANKING:
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
            with st.container(border=True):
                st.markdown("##### 🏆 Pódio")
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
# ABA 2: BUSCAR NA BASE DE CONHECIMENTO (unifica Busca Semântica + Acervo Digital + Explorar)
# ==========================================
if aba_ativa == ABA_BUSCA:
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
        .ws-busca-hero .wiki { color: #ff9a6b; }
        .ws-busca-hero .suporte { color: #5eb8d9; }
        .ws-busca-hero p {
            color: #d1d5db;
            font-size: 1rem;
            margin: 0.45rem 0 0 0;
        }
        </style>
        <div class="ws-busca-hero">
            <h1><span class="wiki">Wiki</span><span class="suporte">Suporte</span></h1>
            <p><strong>Está com dúvidas, precisa de alguma informação?</strong><br/>Busque em todo o conhecimento registrado: contribuições da equipe, wikis do Helpdesk e manuais do PostoGestor — tudo num só lugar.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        criar_extensao_e_tabela(EMBEDDING_DIM)
    except Exception:
        pass

    ORIGEM_LABELS = {
        "CONHECIMENTO_SUPORTE": "🤝 Contribuição da Equipe",
        "WIKI_HELPDESK": "📘 Wiki Helpdesk",
        "MANUAL_HELPDESK": "📙 Manual PostoGestor",
    }
    ORIGENS_TODAS = list(ORIGEM_LABELS.keys())

    _STOPWORDS_BUSCA_UNI = {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
        "no", "na", "em", "para", "com", "como", "por", "que", "e", "ou",
    }

    def _normalizar_texto_busca_uni(t) -> str:
        s = "" if t is None or (isinstance(t, float) and pd.isna(t)) else str(t)
        txt = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
        return re.sub(r"[^a-z0-9\s]", " ", txt.lower())

    def _tokens_busca_uni(termo_busca: str) -> list[str]:
        norm = _normalizar_texto_busca_uni(termo_busca)
        return [tk for tk in norm.split() if tk not in _STOPWORDS_BUSCA_UNI and len(tk) > 2]

    if perfil_logado == "admin":
        with st.expander("⚙️ Administração da busca vetorial", expanded=False):
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
                    f"⚠️ Dimensão vetorial atual: {dim_atual}. Recomendada para este projeto: {EMBEDDING_DIM}. "
                    "Considere alinhar para manter a precisão da busca semântica."
                )
            st.caption(
                f"Dimensão recomendada no cenário atual: **{EMBEDDING_DIM}**. "
                "Esta dimensão é um bom equilíbrio entre precisão e velocidade para o volume atual."
            )
            if st.button("♻️ Reindexar Base de Conhecimento", key="btn_reindex_rag"):
                with st.spinner("Reindexando embeddings da Base de Conhecimento..."):
                    total_chunks = indexar_base_conhecimento(origens=None, limite=1500)
                st.success(f"Reindexação concluída. Chunks indexados/atualizados: {total_chunks}")

    try:
        with engine.connect() as conn:
            categorias_disponiveis = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT DISTINCT categoria FROM base_conhecimento "
                        "WHERE status IN ('APROVADO','OBSOLETO') AND categoria IS NOT NULL "
                        "ORDER BY categoria"
                    )
                ).fetchall()
                if r[0]
            ]
            autores_disponiveis = [
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT DISTINCT COALESCE(u.nome, 'Equipe HelpDesk') AS autor
                        FROM base_conhecimento b
                        LEFT JOIN usuarios u ON b.id_analista_autor = u.id
                        WHERE b.status IN ('APROVADO','OBSOLETO')
                        ORDER BY autor
                        """
                    )
                ).fetchall()
                if r[0]
            ]
    except Exception:
        categorias_disponiveis = []
        autores_disponiveis = []

    with st.form("form_busca_uni", clear_on_submit=False):
        st.markdown("#### 🎯 Buscar ou filtrar")
        pergunta = st.text_input(
            "O que você está procurando?",
            placeholder="Ex.: Como configuro o e-mail no PostoGestor para envio automático?",
            key="busca_uni_texto",
        )
        col_fonte, col_categoria = st.columns(2)
        with col_fonte:
            fontes_sel_labels = st.multiselect(
                "Fonte",
                options=list(ORIGEM_LABELS.values()),
                default=list(ORIGEM_LABELS.values()),
                key="busca_uni_fontes",
                help="Escolha onde pesquisar para deixar os resultados mais precisos.",
            )
        with col_categoria:
            categoria_sel = st.selectbox(
                "Categoria",
                ["Todas as Categorias"] + categorias_disponiveis,
                key="busca_uni_categoria",
            )
        col_autor, col_ini, col_fim = st.columns([1.4, 1, 1])
        with col_autor:
            autor_sel = st.selectbox(
                "Autor",
                ["Todos os autores"] + autores_disponiveis,
                key="busca_uni_autor",
            )
        with col_ini:
            data_ini_sel = st.date_input("Data inicial", value=None, key="busca_uni_data_ini")
        with col_fim:
            data_fim_sel = st.date_input("Data final", value=None, key="busca_uni_data_fim")

        buscar_uni = st.form_submit_button(
            "🔍 Buscar na Base de Conhecimento",
            type="primary",
            use_container_width=True,
        )

    origens_sel = [k for k, v in ORIGEM_LABELS.items() if v in fontes_sel_labels] or ORIGENS_TODAS

    if buscar_uni:
        st.session_state["busca_uni_params"] = {
            "termo": (pergunta or "").strip(),
            "origens": origens_sel,
            "categoria": categoria_sel,
            "autor": autor_sel,
            "data_ini": data_ini_sel,
            "data_fim": data_fim_sel,
        }
        st.session_state["busca_uni_limite"] = 10
        st.session_state["busca_uni_executada"] = True

        termo_registro = (pergunta or "").strip()
        if termo_registro and _busca_sem_ok and registrar_busca_com_topico:
            try:
                registrar_busca_com_topico(
                    engine,
                    usuario_logado_id,
                    termo_registro,
                    "Busca unificada na Base de Conhecimento",
                    "ASSISTENTE",
                )
            except Exception:
                pass

    if not st.session_state.get("busca_uni_executada"):
        st.info(
            "Digite uma dúvida ou ajuste os filtros acima e clique em **Buscar** "
            "para consultar a Base de Conhecimento."
        )
    else:
        params_busca = st.session_state.get("busca_uni_params", {})
        termo = params_busca.get("termo", "")
        origens_busca = params_busca.get("origens") or ORIGENS_TODAS
        categoria_f = params_busca.get("categoria", "Todas as Categorias")
        autor_f = params_busca.get("autor", "Todos os autores")
        data_ini_f = params_busca.get("data_ini")
        data_fim_f = params_busca.get("data_fim")
        limite_atual = int(st.session_state.get("busca_uni_limite", 10))

        ids_ordenados: list[int] = []
        score_por_id: dict[int, float] = {}

        # Sem GEMINI_API_KEY configurada, a busca semântica cai num embedding local
        # (hash "placeholder") cuja similaridade não tem relação real com o texto —
        # pode "acertar" 100% em algo irrelevante e esconder resultados textuais óbvios.
        # Nesse caso, pulamos direto para a busca textual (ILIKE), que é sempre confiável.
        gemini_disponivel = bool(os.getenv("GEMINI_API_KEY"))

        if termo and gemini_disponivel:
            try:
                with st.spinner("Buscando na Base de Conhecimento..."):
                    resultados_sem = buscar_similares(
                        termo,
                        top_k=max(limite_atual, 30),
                        origens=origens_busca,
                        usar_embedding_query=True,
                    )
                for r in resultados_sem:
                    sim = float(r.get("similaridade", 0.0))
                    if sim < 0.45:
                        continue
                    pid = int(r["id_conhecimento"])
                    if pid not in score_por_id:
                        ids_ordenados.append(pid)
                        score_por_id[pid] = sim
            except Exception:
                ids_ordenados = []

        query_sql = """
            SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo, b.origem,
                   COALESCE(b.qtd_upvotes, 0) as qtd_upvotes,
                   COALESCE(b.qtd_visualizacoes, 0) as qtd_visualizacoes,
                   to_char(b.criado_em, 'DD/MM/YYYY') as data_pub,
                   COALESCE(u.nome, 'Equipe HelpDesk') AS autor,
                   b.status as status_row,
                   EXISTS(SELECT 1 FROM base_conhecimento_votos v
                          WHERE v.id_conhecimento = b.id AND v.id_analista_votante = :uid) as ja_curtiu
            FROM base_conhecimento b
            LEFT JOIN usuarios u ON b.id_analista_autor = u.id
            WHERE b.status IN ('APROVADO', 'OBSOLETO')
              AND b.origem = ANY(:origens)
        """
        params_sql: dict = {"uid": usuario_logado_id, "origens": origens_busca}
        if categoria_f != "Todas as Categorias":
            query_sql += " AND b.categoria = :cat"
            params_sql["cat"] = categoria_f
        if autor_f != "Todos os autores":
            query_sql += " AND COALESCE(u.nome, 'Equipe HelpDesk') = :autor"
            params_sql["autor"] = autor_f
        if data_ini_f:
            query_sql += " AND DATE(b.criado_em) >= :data_ini"
            params_sql["data_ini"] = data_ini_f
        if data_fim_f:
            query_sql += " AND DATE(b.criado_em) <= :data_fim"
            params_sql["data_fim"] = data_fim_f

        df_resultado = pd.DataFrame()
        if ids_ordenados:
            query_sql_ids = query_sql + " AND b.id = ANY(:ids)"
            params_ids = dict(params_sql, ids=ids_ordenados)
            with engine.connect() as conn:
                df_resultado = pd.read_sql(text(query_sql_ids), conn, params=params_ids)
            if not df_resultado.empty:
                ordem = {pid: i for i, pid in enumerate(ids_ordenados)}
                df_resultado["_ordem"] = df_resultado["id"].map(ordem)
                df_resultado = df_resultado.sort_values("_ordem").drop(columns="_ordem")
                df_resultado["similaridade"] = df_resultado["id"].map(score_por_id)
                df_resultado = df_resultado.head(limite_atual)

        if df_resultado.empty and termo:
            # Sem hits semânticos relevantes (ou hits que não bateram com os filtros):
            # busca por palavra (não por substring solta — "tef" não deve casar com
            # "msitef") e ordena por relevância (título > categoria > conteúdo),
            # não apenas por data.
            tokens_busca = _tokens_busca_uni(termo)
            termos_busca = tokens_busca or [termo.strip().lower()]

            or_clauses = []
            params_tok: dict = {}
            for i, tok in enumerate(termos_busca):
                or_clauses.append(f"(b.titulo ILIKE :tok{i} OR b.conteudo ILIKE :tok{i})")
                params_tok[f"tok{i}"] = f"%{tok}%"
            query_sql_txt = (
                query_sql
                + " AND ("
                + " OR ".join(or_clauses)
                + ") ORDER BY b.criado_em DESC LIMIT 300"
            )
            params_txt = dict(params_sql, **params_tok)
            with engine.connect() as conn:
                df_candidatos = pd.read_sql(text(query_sql_txt), conn, params=params_txt)

            if not df_candidatos.empty:
                def _score_linha_busca(row) -> int:
                    score = 0
                    tit_n = _normalizar_texto_busca_uni(row.get("titulo"))
                    cat_n = _normalizar_texto_busca_uni(row.get("categoria"))
                    cont_n = _normalizar_texto_busca_uni(row.get("conteudo"))
                    for tok in termos_busca:
                        padrao = r"\b" + re.escape(tok) + r"\b"
                        if re.search(padrao, tit_n):
                            score += 3
                        if re.search(padrao, cat_n):
                            score += 2
                        if re.search(padrao, cont_n):
                            score += 1
                    return score

                df_candidatos["_score"] = df_candidatos.apply(_score_linha_busca, axis=1)
                df_resultado = (
                    df_candidatos[df_candidatos["_score"] > 0]
                    .sort_values(["_score", "id"], ascending=[False, False])
                    .head(limite_atual)
                    .drop(columns="_score")
                    .copy()
                )
                if not df_resultado.empty:
                    df_resultado["similaridade"] = None
        elif df_resultado.empty:
            query_sql_browse = query_sql + " ORDER BY b.criado_em DESC LIMIT :limite"
            params_browse = dict(params_sql, limite=limite_atual)
            with engine.connect() as conn:
                df_resultado = pd.read_sql(text(query_sql_browse), conn, params=params_browse)
            if not df_resultado.empty:
                df_resultado["similaridade"] = None

        if df_resultado.empty:
            st.info("📭 Nenhum resultado encontrado com os filtros atuais. Ajuste os termos ou os filtros.")
        else:
            st.caption(f"Exibindo {len(df_resultado)} resultado(s).")
            nome_marcador = st.session_state.get("usuario_nome") or "Equipe"
            for _, row in df_resultado.iterrows():
                origem_row = str(row.get("origem") or "")
                is_contribuicao = origem_row == "CONHECIMENTO_SUPORTE"
                is_obsoleto = str(row.get("status_row", "")).upper() == "OBSOLETO"
                badge_origem = ORIGEM_LABELS.get(origem_row, origem_row)
                with st.container(border=True):
                    col_txt, col_btn = st.columns([4, 1.2])

                    with col_txt:
                        badge_obs = " **🟠 OBSOLETA**" if is_obsoleto else ""
                        st.markdown(f"### {row['titulo']}{badge_obs}")
                        sim = row.get("similaridade")
                        sim_txt = (
                            f" | 🎯 {int(float(sim) * 100)}% relevante"
                            if pd.notna(sim)
                            else ""
                        )
                        st.caption(
                            f"{badge_origem} | 📂 {row['categoria'] or '—'} | "
                            f"✍️ {row['autor']} | 📅 {row['data_pub']}{sim_txt}"
                        )
                        if is_obsoleto:
                            st.caption("Conteúdo ainda visível; não entra no assistente até ser reavaliada.")

                    with col_btn:
                        if is_contribuicao and not is_obsoleto:
                            label = f"❤️ {row['qtd_upvotes']}" if row["ja_curtiu"] else f"🤍 {row['qtd_upvotes']}"
                            if st.button(label, key=f"lk_uni_{row['id']}", use_container_width=True):
                                with engine.begin() as conn_voto:
                                    if row["ja_curtiu"]:
                                        conn_voto.execute(
                                            text(
                                                "DELETE FROM base_conhecimento_votos WHERE id_conhecimento = :pid AND id_analista_votante = :uid"
                                            ),
                                            {"pid": row["id"], "uid": usuario_logado_id},
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
                                            {"pid": row["id"], "uid": usuario_logado_id},
                                        )
                                        conn_voto.execute(
                                            text(
                                                "UPDATE base_conhecimento SET qtd_upvotes = COALESCE(qtd_upvotes, 0) + 1 WHERE id = :pid"
                                            ),
                                            {"pid": row["id"]},
                                        )
                                st.rerun()
                        elif is_contribuicao:
                            st.caption("Votos pausados (obsoleta).")

                        if is_contribuicao and perfil_logado == "admin" and not is_obsoleto:
                            with st.expander("⚠️ Marcar obsoleta", expanded=False):
                                motivo_obs = st.text_input(
                                    "Motivo / o que o autor deve atualizar",
                                    key=f"mot_obs_uni_{row['id']}",
                                    placeholder="Ex.: Procedure mudou na v2.9; incluir novo print",
                                )
                                if st.button(
                                    "Confirmar obsoleta + avisar autor",
                                    key=f"obs_uni_{row['id']}",
                                    use_container_width=True,
                                ):
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

                    with st.expander("📖 Ler conteúdo completo"):
                        view_key = f"viewed_uni_{row['id']}"
                        if view_key not in st.session_state:
                            with engine.begin() as conn_view:
                                conn_view.execute(
                                    text(
                                        "UPDATE base_conhecimento "
                                        "SET qtd_visualizacoes = COALESCE(qtd_visualizacoes, 0) + 1 "
                                        "WHERE id = :pid"
                                    ),
                                    {"pid": row["id"]},
                                )
                            st.session_state[view_key] = True
                        st.markdown(row["conteudo"])
                        anexo = row.get("caminho_anexo")
                        if anexo and pd.notna(anexo) and str(anexo).strip() and os.path.exists(str(anexo)):
                            with open(anexo, "rb") as f:
                                st.download_button(
                                    "📎 Baixar anexo",
                                    f,
                                    file_name=os.path.basename(str(anexo)),
                                    key=f"dl_uni_{row['id']}",
                                )

            if len(df_resultado) >= limite_atual:
                if st.button("📥 Carregar mais 20", use_container_width=True, key="btn_carregar_mais_uni"):
                    st.session_state["busca_uni_limite"] = limite_atual + 20
                    st.rerun()

# ==========================================
# ABA 5: HISTÓRICO E RANKING DA EQUIPE
# ==========================================
if aba_ativa == ABA_HISTORICO:
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
        with st.container(border=True):
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
        with st.container(border=True):
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
if aba_ativa == ABA_NOVA:
    st.markdown("### 📝 Adicionar Nova Contribuição")
    
    with st.container(border=True):
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
                                lock_aprovacao_autor(conn, int(usuario_logado_id))
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


if aba_ativa == ABA_MINHAS:
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
if perfil_logado == "admin" and aba_ativa == ABA_FILA:
    st.subheader("⚖️ Fila de Controle de Qualidade (QA)")
    st.caption("Avalie as contribuições pendentes. Garanta que o conhecimento salvo siga os padrões técnicos.")
    
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


