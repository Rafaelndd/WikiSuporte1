"""
Essa page foi renomeada para 6_🤝_Contribuicoes_Suporte.py para refletir melhor o conteúdo e evitar confusão com a page de dashboard de tickets. O código da antiga page 5_📊_Dashboard_Tickets_EPSY.py foi mantido aqui para referência, mas a nova page 6 terá foco total em contribuições, avaliações e fila de revisão, enquanto a antiga page 5 continuará sendo o dashboard analítico dos tickets EPSY.

"""
import zipfile
import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection
import os
import time
from datetime import datetime
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

load_dotenv()


try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass
#==================================================================================================================


# Configuração da página (deve ser a primeira chamada Streamlit)
st.set_page_config(page_title="WikiSuporte", page_icon="🏆", layout="wide")

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
            "Acesse WikiSuporte → Central de Conhecimento → Minhas Contribuições, "
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
st.title("🧠 Central de Conhecimento")
st.markdown("Respostas rápidas, manuais do PostoGestor, wikis do HelpDesk e conhecimento colaborativo centralizados em um só lugar!")
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "**Ranking** — XP por contribuições (regra de prazo nos registros). **Assistente** — perguntas com IA sobre a base. "
        "**Acervo** — Manuais/ Wikis. **Adicionar** — envie texto/arquivo para revisão. **Explorar** — busca na base. "
        "Coordenador têm **Fila de avaliação**; demais perfis não tem acesso a essa aba."
    )

# ==========================================
# 4. DEFINIÇÃO DAS ABAS (Nova Ordem de UX)
# ==========================================
if perfil_logado == "admin":
    abas = st.tabs([
        "🏅 Inicio & Ranking", 
        "🤖 Assistente Virtual", 
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
        "🤖 Assistente Virtual", 
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
    st.info("💡 **Regra de Agilidade:** Registros em até 7 dias valem 100 XP. Acima de 21 dias valem 0 XP.")

    # Importamos a lista de níveis para o sumário visual (expander)
    from modules.utils import NIVEIS_CONHECIMENTO, calcular_patente

    with engine.connect() as conn:
        # A query agora busca diretamente as colunas xp_total e medalha_atual do banco
        query_ranking = text("""
            SELECT u.nome AS "Analista", 
                   COUNT(b.id) AS "Dicas Aprovadas", 
                   u.xp_total AS "XP Acumulado",
                   u.medalha_atual AS "Patente"
            FROM usuarios u
            LEFT JOIN base_conhecimento b ON b.id_analista_autor = u.id 
                 AND b.origem = 'CONHECIMENTO_SUPORTE' 
                 AND b.status = 'APROVADO'
            WHERE u.xp_total > 0
            GROUP BY u.nome, u.xp_total, u.medalha_atual
            ORDER BY u.xp_total DESC
        """)
        df_ranking = pd.read_sql(query_ranking, conn)
        
        if not df_ranking.empty:
            # 1. Adicionamos o ÍCONE dinâmico baseado no XP (vido do utils) 
            # Isso garante que o emoji mude conforme o XP que o trigger calculou
            df_ranking.insert(0, "Ícone", df_ranking["XP Acumulado"].apply(lambda x: calcular_patente(x)["icon"]))

            # 2. Exibição da Tabela Principal
            st.dataframe(
                df_ranking, 
                use_container_width='strech', 
                hide_index=True,
                column_config={
                    "Ícone": st.column_config.TextColumn("徽", width="small"),
                    "XP Acumulado": st.column_config.NumberColumn("XP Total", format="%d ⚡"),
                    "Dicas Aprovadas": st.column_config.NumberColumn("Contribuições", width="medium")
                }
            )

            # 3. Sumário de Progressão (Para os analistas saberem o que falta)
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
# ABA 2: MOTOR DE BUSCA HÍBRIDO (Com IA Inteligente)
# ==========================================
with aba_gemini:
    st.subheader("🤖 Pesquisar")
    pergunta = st.text_input("Informe sua dúvida: ", placeholder="Ex: Como configurar o e-mail no PostoGestor?", key="input_psy")
    
    if st.button("🔍 Buscar", type="primary"):
        if not pergunta.strip():
            st.warning("⚠️ Insira uma dúvida válida.")
        else:
            with st.spinner("Analisando base e comparando com o histórico recente..."):
                tem_no_cache = False

                # --- Aviso semântico: mesmo assunto já buscado (embedding) ---
                if _busca_sem_ok and listar_buscas_mesmo_assunto:
                    try:
                        colegas = listar_buscas_mesmo_assunto(
                            engine, pergunta.strip(), usuario_logado_id, "ASSISTENTE", limite=12
                        )
                    except Exception:
                        colegas = []
                    if len(colegas) >= 1:
                        outros = [c for c in colegas if c.get("nome") and True]
                        st.warning(
                            "**Este tema já foi pesquisado antes** (busca semântica — variações como "
                            "\"CertificadoDigital\", \"instalar certificado\", etc. contam como o mesmo assunto)."
                        )
                        st.info(
                            "Na aba **📖 Histórico de Buscas** você vê **quem** buscou e **dia/hora**. "
                            "Abaixo, últimas buscas neste mesmo assunto:"
                        )
                        for c in colegas[:8]:
                            quem = c.get("nome") or "Colega"
                            st.caption(f"**{quem}** — {c.get('quando', '')} — _{str(c.get('pergunta', ''))[:100]}…_")
                
                def normalizar_texto_completo(texto):
                    t = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
                    return re.sub(r'[^a-z0-9\s]', '', t.lower()).strip()
                
                def obter_fatias(texto):
                    stopwords = {'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'em', 'para', 'com', 'como', 'qual', 'quais', 'que', 'e', 'sobre', 'por', 'ou', 'onde', 'quando', 'fazer', 'eu', 'me', 'meu', 'minha', 'instalar', 'instalo', 'configurar', 'configuro'}
                    norm = normalizar_texto_completo(texto)
                    return set([p for p in norm.split() if p not in stopwords and len(p) > 2])

                pergunta_norm = normalizar_texto_completo(pergunta)
                pergunta_glued = pergunta_norm.replace(" ", "")
                fatias_nova = obter_fatias(pergunta)
                match_encontrado = None

                with engine.connect() as conn:
                    query_historico = text("SELECT id, pergunta, resposta_ia, to_char(criado_em, 'DD/MM/YYYY HH24:MI') FROM historico_buscas_psy ORDER BY criado_em DESC LIMIT 50")
                    historico_recente = conn.execute(query_historico).fetchall()
                
                for hist in historico_recente:
                    hist_id, hist_pergunta_original, resposta_cache, data_cache = hist
                    hist_norm = normalizar_texto_completo(hist_pergunta_original)
                    hist_glued = hist_norm.replace(" ", "")
                    fatias_hist = obter_fatias(hist_pergunta_original)
                    
                    if SequenceMatcher(None, pergunta_norm, hist_norm).ratio() > 0.8: match_encontrado = hist; break
                    if len(pergunta_glued) > 5 and len(hist_glued) > 5 and (pergunta_glued in hist_glued or hist_glued in pergunta_glued): match_encontrado = hist; break
                    if fatias_nova and fatias_hist:
                        intersecao = fatias_nova.intersection(fatias_hist)
                        min_len = min(len(fatias_nova), len(fatias_hist))
                        if min_len > 0 and (len(intersecao) / min_len) >= 0.6: match_encontrado = hist; break

                if match_encontrado:
                    hist_id, hist_pergunta_original, resposta_cache, data_cache = match_encontrado
                    st.success(f"⚠️ **Sua dúvida já foi pesquisada recentemente!** Semelhança com: *'{hist_pergunta_original}'*.")
                    with st.expander("📖 Ver resumo resgatado do histórico", expanded=True):
                        st.markdown(resposta_cache)
                        st.caption("⚡ **Motor Elétrico:** Resposta resgatada do cache.")
                    tem_no_cache = True
                    try:
                        if _busca_sem_ok and registrar_busca_com_topico:
                            registrar_busca_com_topico(
                                engine,
                                usuario_logado_id,
                                hist_pergunta_original,
                                resposta_cache or "",
                                "ASSISTENTE",
                            )
                        else:
                            with engine.begin() as conn_log:
                                conn_log.execute(
                                    text(
                                        "INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens) VALUES (:u, :p, :r, 0, 0, 0)"
                                    ),
                                    {"u": usuario_logado_id, "p": hist_pergunta_original, "r": resposta_cache},
                                )
                    except Exception as e:
                        st.error(f"Erro ranking: {e}")
                
                if not tem_no_cache:
                    contextos_db = []
                    resultados_puros = []
                    if fatias_nova:
                        with engine.connect() as conn:
                            clausulas_or, clausulas_score = [], []
                            params = {}
                            mapa_origem = 'áàâãäéèêëíìîïóòôõöúùûüçñ'
                            mapa_destino = 'aaaaaeeeeiiiiooooouuuucn'
                            for i, p in enumerate(fatias_nova):
                                param_name = f"p{i}"
                                params[param_name] = f"%{p}%"
                                clausula_like = f"(translate(lower(titulo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} OR translate(lower(conteudo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name})"
                                clausulas_or.append(clausula_like)
                                clausulas_score.append(f"(CASE WHEN translate(lower(titulo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} THEN 2 ELSE 0 END) + (CASE WHEN translate(lower(conteudo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} THEN 1 ELSE 0 END)")
                            
                            filtros_sql = " OR ".join(clausulas_or)
                            score_sql = " + ".join(clausulas_score)
                            query_rag = text(f"SELECT titulo, origem, conteudo, caminho_anexo, ({score_sql}) as pontuacao_relevancia FROM base_conhecimento WHERE status = 'APROVADO' AND ({filtros_sql}) ORDER BY pontuacao_relevancia DESC LIMIT 5")
                            resultados = conn.execute(query_rag, params).fetchall()
                            for r in resultados:
                                contextos_db.append(f"📚 FONTE: {r[0]}\nCONTEÚDO: {r[2]}")
                                resultados_puros.append({"titulo": r[0], "origem": r[1], "conteudo": r[2], "anexo": r[3], "score": r[4]})
                    
                    texto_contexto = "\n\n---\n\n".join(contextos_db)
                    # --- LIBERA IA PARA TODOS OS PERFIS ---
                    # Antes: acesso_ia_liberado = perfil_logado in ['coordenador', 'dev']
                    acesso_ia_liberado = True
                    if acesso_ia_liberado:
                            from google import genai
                            import requests

                            from dotenv import load_dotenv
                            load_dotenv()

                            api_key_gemini = os.getenv("GEMINI_API_KEY")
                            api_key_deepseek = os.getenv("DEEPSEEK_API_KEY")

                            resposta_texto = None
                            erro_ia = None

                            # 1ª TENTATIVA: GEMINI
                            try:
                                if not api_key_gemini:
                                    raise RuntimeError("GEMINI_API_KEY não configurada.")

                                client = genai.Client(api_key=api_key_gemini)
                                prompt = (
                                    f"Responda diretamente. DÚVIDA: {pergunta}\n\nCONTEXTO:\n{texto_contexto}"
                                    if texto_contexto
                                    else f"Diga que não achou manuais para: {', '.join(fatias_nova)}."
                                )
                                resposta_ia = client.models.generate_content(
                                    model="gemini-2.5-flash",
                                    contents=prompt,
                                )
                                usage = getattr(resposta_ia, "usage_metadata", None)
                                t_prompt = getattr(usage, "input_tokens", None) if usage else None
                                t_resp = getattr(usage, "output_tokens", None) if usage else None
                                t_total = getattr(usage, "total_tokens", None) if usage else None

                                resposta_texto = resposta_ia.text

                            except Exception as e_gemini:
                                erro_ia = e_gemini

                                # 2ª TENTATIVA: DEEPSEEK (se chave existir)
                                try:
                                    if not api_key_deepseek:
                                        raise RuntimeError("DEEPSEEK_API_KEY não configurada.")

                                    headers = {
                                        "Content-Type": "application/json",
                                        "Authorization": f"Bearer {api_key_deepseek}",
                                    }
                                    prompt = (
                                        f"Responda diretamente. DÚVIDA: {pergunta}\n\nCONTEXTO:\n{texto_contexto}"
                                        if texto_contexto
                                        else f"Diga que não achou manuais para: {', '.join(fatias_nova)}."
                                    )
                                    payload = {
                                        "model": "deepseek-chat",
                                        "messages": [
                                            {"role": "system", "content": "Você é um assistente técnico do WikiSuporte."},
                                            {"role": "user", "content": prompt},
                                        ],
                                    }
                                    resp = requests.post(
                                        "https://api.deepseek.com/v1/chat/completions",
                                        headers=headers,
                                        data=json.dumps(payload),
                                        timeout=30,
                                    )
                                    resp.raise_for_status()
                                    data = resp.json()
                                    resposta_texto = data["choices"][0]["message"]["content"]
                                    # DeepSeek não retorna tokens no mesmo formato; usamos zeros por compatibilidade
                                    t_prompt = t_resp = t_total = 0

                                except Exception as e_deepseek:
                                    erro_ia = e_deepseek
                                    resposta_texto = None  # força fallback sem IA

                            # --- SE CONSEGUIU RESPOSTA POR GEMINI OU DEEPSEEK ---
                            if resposta_texto:
                                st.success("⚡ Resposta gerada!")
                                st.markdown(resposta_texto)
                                if t_total is not None:
                                    st.caption(f"🔋 Tokens: {t_total}")

                                try:
                                    if _busca_sem_ok and registrar_busca_com_topico:
                                        registrar_busca_com_topico(
                                            engine,
                                            usuario_logado_id,
                                            pergunta.strip(),
                                            resposta_texto or "",
                                            "ASSISTENTE",
                                            t_prompt or 0,
                                            t_resp or 0,
                                            t_total or 0,
                                        )
                                    else:
                                        with engine.begin() as conn_log:
                                            conn_log.execute(
                                                text(
                                                    "INSERT INTO historico_buscas_psy "
                                                    "(usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens) "
                                                    "VALUES (:u, :p, :r, :tp, :tr, :tt)"
                                                ),
                                                {
                                                    "u": usuario_logado_id,
                                                    "p": pergunta.strip(),
                                                    "r": resposta_texto,
                                                    "tp": t_prompt or 0,
                                                    "tr": t_resp or 0,
                                                    "tt": t_total or 0,
                                                },
                                            )
                                except Exception as db_e:
                                    st.error(f"Erro BD: {db_e}")

                            else:
                                # FALHA NAS CHAMADAS DE IA (limite diário ou erro): FALLBACK PARA BUSCA NO BANCO
                                if erro_ia:
                                    st.warning(
                                        "O motor de IA atingiu o limite diário ou apresentou erro. "
                                        "Usando apenas a busca semântica direta na base de conhecimento."
                                    )

                                if resultados_puros:
                                    st.markdown("### Sugestões encontradas na base de conhecimento")
                                    for doc in resultados_puros:
                                        with st.expander(f"📄 {doc['titulo']} - Score: {doc['score']}"):
                                            st.write(doc['conteudo'])
                                else:
                                            st.info("Nenhum documento relevante foi encontrado na base para esta dúvida.")
                    else:
                                # NUNCA deve cair aqui, pois acesso_ia_liberado = True, mas mantemos por segurança
                                st.info("⚡ Motor a Combustão: IA desativada para este perfil. Veja manuais abaixo:")
                        
                    if resultados_puros:
                        for doc in resultados_puros:
                            with st.expander(f"📄 {doc['titulo']} - Score: {doc['score']}"): st.write(doc['conteudo'])

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
    st.subheader("📖 Histórico e Ranking da Equipe")
    st.caption(
        "Histórico agrupa por **tema semântico** (mesma dúvida em palavras diferentes = um bloco). "
        "Ranking mostra **o que mais gera dúvida** na equipe, sem repetir variações do mesmo assunto."
    )
    col_hist, col_rank = st.columns([2, 1])

    with col_hist:
        st.markdown("#### 🔍 Últimas buscas por tema (quem / quando)")
        df_recentes = pd.DataFrame()
        if _busca_sem_ok and historico_por_topico_recente:
            try:
                recentes = historico_por_topico_recente(engine, 25)
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
                    ) sub ORDER BY criado_em DESC LIMIT 15
                    """
                )
                df_recentes = pd.read_sql(query_recentes, conn)
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
        else:
            st.info("Ainda não há registros de buscas ao Psy.")

    with col_rank:
        st.markdown("#### 🏆 Top assuntos (semântico)")
        df_ranking_buscas = pd.DataFrame()
        if _busca_sem_ok and ranking_topicos_agregado:
            try:
                # Assistente + Wiki + Manual no mesmo ranking global (soma por tópico já está em busca_topicos por origem)
                # Unimos os três origens num único "volume" por label seria duplicado; melhor: top ASSISTENTE + mesclar
                ra = ranking_topicos_agregado(engine, "ASSISTENTE", 6)
                rw = ranking_topicos_agregado(engine, "WIKI", 4)
                rm = ranking_topicos_agregado(engine, "MANUAL", 4)
                merged = {}
                for label, n in ra + rw + rm:
                    merged[label] = merged.get(label, 0) + n
                top = sorted(merged.items(), key=lambda x: -x[1])[:12]
                df_ranking_buscas = pd.DataFrame(top, columns=["Assunto (tema)", "Total buscas"])
            except Exception:
                df_ranking_buscas = pd.DataFrame()
        if df_ranking_buscas.empty:
            with engine.connect() as conn:
                query_ranking_buscas = text(
                    'SELECT INITCAP(lower(pergunta)) as "Assunto", COUNT(id) as "Volume" '
                    "FROM historico_buscas_psy GROUP BY lower(pergunta) ORDER BY \"Volume\" DESC LIMIT 10"
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
        
        col_menu, col_submenu, col_data = st.columns([1,1,1])

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
        accept_multiple_files=True
    )
        
        btn_salvar = st.form_submit_button("💾 Salvar Contribuição", type="primary")
        
        if btn_salvar:
            if not titulo or not categoria or not conteudo or not data_evento:
                st.warning("⚠️ Preencha Título, Categoria, Conteúdo e Data do Ocorrido.")
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
                            nome_seguro = f"{idx}_{arquivo.name.replace(' ', '_')}"
                            caminho_fisico = os.path.join(pasta_contrib, nome_seguro)
                            with open(caminho_fisico, "wb") as f:
                                f.write(arquivo.getbuffer())
                            arquivos_salvos.append((caminho_fisico, arquivo))
                            # Extração de texto (quando aplicável) para enriquecer o conteúdo
                            ext = arquivo.name.split('.')[-1].lower()
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
                        categoria_final = menu.upper()

                        # if subsubmenu:
                        #     subcategoria_final = f"{submenu} > {subsubmenu}".upper()
                        # else:
                        #     subcategoria_final = submenu.upper()
                        # AJUSTE NO SQL: Incluindo data_ocorrido para disparar a Trigger de XP
                        conn.execute(
                            text("""
                                INSERT INTO base_conhecimento 
                                (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor, status, caminho_anexo, qtd_tentativas, data_ocorrido) 
                                VALUES ('CONHECIMENTO_SUPORTE', :t, :c, :s, :co, :a, :st, :ax, 1, :do)
                            """),
                            {
                                "t": titulo.strip(),
                                "c": categoria.strip().upper(),
                                "s": subcategoria.strip().upper() if subcategoria else "GERAL",
                                "co": conteudo_final,
                                "a": usuario_logado_id,
                                "st": status_inicial,
                                "ax": caminho_anexo_db,
                                "do": data_evento  # NOVO VALOR
                            }
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
                       to_char(b.criado_em, 'DD/MM/YYYY às HH24:MI') as data_envio, u.nome AS autor 
                FROM base_conhecimento b 
                JOIN usuarios u ON b.id_analista_autor = u.id 
                WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status = 'PENDENTE'
                ORDER BY b.criado_em ASC
            """)
            df_fila = pd.read_sql(query_fila, conn)
            
        if not df_fila.empty:
            for _, row in df_fila.iterrows():
                # Tag de alerta se já foi para a fila várias vezes
                tentativas = row.get('qtd_tentativas', 1)
                alerta_tentativas = f" 🚨 ({tentativas}ª Tentativa)" if tentativas > 1 else ""
                
                with st.expander(f"⏳ {row['titulo']} - {row['autor']}{alerta_tentativas}"):
                    st.markdown(f"**👤 Autor:** {row['autor']} | **📅 Enviado em:** {row['data_envio']}")
                    st.markdown(f"**📂 Classificação:** `{row['categoria']}` ➔ `{row['subcategoria']}`")
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
                                    conn_apr.execute(text("UPDATE base_conhecimento SET status = 'APROVADO' WHERE id = :id"), {"id": row['id']})
                                registrar_log_auditoria(usuario_logado_id, "APROVOU_CONTRIBUICAO", f"Aprovou ID: {row['id']}")
                                st.success("Documento homologado e publicado na Base!")
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
    # --- RECUPERAÇÃO SEGURA DO ID (RESOLVE O NAMEERROR) ---
    # Tentamos pegar o ID de onde ele estiver guardado na sua sessão
    usuario_id = st.session_state.get('usuario_id') or st.session_state.get('usuario_logado_id')
    
    if not usuario_id:
        st.error("⚠️ Erro: Usuário não identificado. Por favor, faça login novamente.")
        st.stop() # Interrompe a execução desta aba se não houver ID

    st.title("🔎 Explorar Base de Conhecimento")
    
    # Inicialização segura
    df_conhecimento = pd.DataFrame()
    params = {"uid": usuario_id} 
    
    # ... restante do seu código (Filtros, Query e Renderização) ...

    # --- 1. ÁREA DE FILTROS ---
    with st.container(border=True):
        st.markdown("#### 🎯 Filtros de Pesquisa")
        col_busca, col_cat = st.columns([2, 1])
        
        with col_busca:
            termo_pesquisa = st.text_input("Pesquisar por Título ou Conteúdo:", placeholder="Ex: Erro impressora...")
        
        with col_cat:
            try:
                with engine.connect() as conn:
                    cat_query = text(
                        "SELECT DISTINCT categoria FROM base_conhecimento "
                        "WHERE status IN ('APROVADO','OBSOLETO') AND origem = 'CONHECIMENTO_SUPORTE' ORDER BY categoria"
                    )
                    categorias_disponiveis = [row[0] for row in conn.execute(cat_query).fetchall() if row[0]]
            except Exception:
                categorias_disponiveis = []
                
            categorias_disponiveis.insert(0, "Todas as Categorias")
            categoria_selecionada = st.selectbox("Filtrar por Categoria:", categorias_disponiveis)

    # --- 2. MONTAGEM DA QUERY (APROVADO + OBSOLETO: obsoletas permanecem listadas) ---
    query_base = """
        SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo,
               COALESCE(b.qtd_upvotes, 0) as qtd_upvotes,
               COALESCE(b.qtd_visualizacoes, 0) as qtd_visualizacoes,
               to_char(b.criado_em, 'DD/MM/YYYY') as data_pub, u.nome AS autor, b.status as status_row,
               EXISTS(SELECT 1 FROM base_conhecimento_votos v
                      WHERE v.id_conhecimento = b.id AND v.id_analista_votante = :uid) as ja_curtiu
        FROM base_conhecimento b
        LEFT JOIN usuarios u ON b.id_analista_autor = u.id
        WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status IN ('APROVADO', 'OBSOLETO')
    """
    
    if termo_pesquisa.strip():
        query_base += " AND (b.titulo ILIKE :termo OR b.conteudo ILIKE :termo)"
        params["termo"] = f"%{termo_pesquisa.strip()}%"
        
    if categoria_selecionada != "Todas as Categorias":
        query_base += " AND b.categoria = :cat"
        params["cat"] = categoria_selecionada
        
    query_base += " ORDER BY b.criado_em DESC LIMIT 50"

    # --- 3. EXECUÇÃO E RENDERIZAÇÃO ---
    try:
        with engine.connect() as conn:
            df_conhecimento = pd.read_sql(text(query_base), conn, params=params)

        if df_conhecimento.empty:
            st.info("Nenhuma contribuição encontrada.")
        else:
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
                            if st.button(label, key=f"lk_{row['id']}", use_container_width='strech'):
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
                        # Ajuste: Incrementar qtd_visualizacoes ao abrir o expander (considerando que o expander só é "acessado" quando expandido)
                        # Usamos session_state para rastrear se já foi visualizado nesta sessão, para evitar múltiplos increments no mesmo usuário/sessão
                        view_key = f"viewed_{row['id']}"
                        if view_key not in st.session_state:
                            with engine.begin() as conn_view:
                                conn_view.execute(text("UPDATE base_conhecimento SET qtd_visualizacoes = COALESCE(qtd_visualizacoes, 0) + 1 WHERE id = :pid"), {"pid": row['id']})
                            st.session_state[view_key] = True  # Marca como visualizado nesta sessão
                        st.markdown(row['conteudo'])

    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")


    # --- 3. EXIBIÇÃO DOS RESULTADOS (UI/UX) ---
    if df_conhecimento.empty:
        st.info("📭 Nenhuma contribuição encontrada com os filtros atuais.")
    else:
        st.caption(f"A mostrar {len(df_conhecimento)} resultados aprovados.")
        
        for index, row in df_conhecimento.iterrows():
            # Cria um "card" expansível para cada contribuição
            titulo_card = f"📖 {row['titulo']} — (📂 {row['categoria']})"
            
            with st.expander(titulo_card):
                # Cabeçalho do Card
                col_meta1, col_meta2 = st.columns([3, 1])
                with col_meta1:
                    st.markdown(f"**Subcategoria:** `{row['subcategoria']}` | **Autor:** 👤 {row['autor']}")
                with col_meta2:
                    st.markdown(f"📅 *{row['data_pub']}*")
                    
                st.divider()
                
                # Corpo de Texto
                st.markdown("#### Conteúdo")
                st.write(row['conteudo'])
                
                # --- LÓGICA DE EXIBIÇÃO DE ANEXOS E MULTIMÉDIA ---
                caminho_anexo = row.get('caminho_anexo')
                
                # Verifica se a string não é nula e se o ficheiro físico realmente existe
                if pd.notna(caminho_anexo) and str(caminho_anexo).strip() and os.path.exists(str(caminho_anexo)):
                    st.markdown("---")
                    st.markdown("📎 **Evidências e Anexos**")
                    
                    extensao = str(caminho_anexo).split('.')[-1].lower()
                    
                    # 1. Pré-visualização Integrada (Renderização Nativa)
                    if extensao in ['png', 'jpg', 'jpeg']:
                        # Exibe a imagem de forma responsiva sem ultrapassar o layout
                        st.image(str(caminho_anexo), caption="Imagem em Anexo", use_container_width='strech')
                        
                    elif extensao in ['mp4', 'avi', 'mov']:
                        st.video(str(caminho_anexo))
                        
                    elif extensao in ['mp3', 'wav', 'ogg']:
                        st.audio(str(caminho_anexo))
                        
                    # 2. Botão Universal de Download (Para PDFs, TXT, XML, SQL, ZIP, FR3, etc.)
                    # Usamos 'with open' para ler os bytes do ficheiro e passar para o botão
                    try:
                        with open(str(caminho_anexo), "rb") as file:
                            bytes_ficheiro = file.read()
                            nome_original = os.path.basename(str(caminho_anexo))
                            
                            st.download_button(
                                label=f"💾 Descarregar Anexo Original (.{extensao.upper()})",
                                data=bytes_ficheiro,
                                file_name=nome_original,
                                mime="application/octet-stream",
                                # KEY única é estritamente necessária no Streamlit dentro de loops
                                key=f"btn_dl_explorar_{row['id']}_{index}",
                                type="secondary"
                            )
                    except Exception as e:
                        st.warning(f"⚠️ O arquivo não pôde ser carregado:{e}")
                elif pd.notna(caminho_anexo) and str(caminho_anexo).strip():
                    # Caso o registo exista no banco, mas o ficheiro físico tenha sido apagado do servidor
                    st.error("⚠️ O anexo desta contribuição não foi encontrado no servidor físico (Pode ter sido movido ou apagado).")