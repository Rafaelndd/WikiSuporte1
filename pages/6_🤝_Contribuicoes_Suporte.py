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
from menus import *
from utils import inicializar_usuario, calcular_patente


load_dotenv()


try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass



# # ==========================================
# # 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# # ==========================================
# st.set_page_config(page_title="WikiSuporte", page_icon="🏆", layout="wide")

# if not st.session_state.get('autenticado'): 
#     st.switch_page("app.py")

# usuario_logado_id = st.session_state.get('usuario_id')
# perfil_logado = str(st.session_state.get('perfil', 'analista')).lower()

# UPLOAD_DIR = "uploads_wiki"
# os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==========================================
# 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# =========================================

# Configuração da página (deve ser a primeira chamada Streamlit)
st.set_page_config(page_title="WikiSuporte", page_icon="🏆", layout="wide")

# Verificação de autenticação com default explícito para False e mensagem de redirecionamento para melhor UX
if not st.session_state.get('autenticado', False):
    st.info("Redirecionando para a página de login...")  # Sugestão: Adicionar feedback ao usuário
    st.switch_page("app.py")

# Recuperação de variáveis de sessão com verificações para evitar erros
usuario_logado_id = st.session_state.get('usuario_id')
if usuario_logado_id is None:  # Sugestão: Verificação para ID ausente
    st.error("ID de usuário não encontrado. Por favor, faça login novamente.")
    st.switch_page("app.py")  # Redireciona se ID não existir

# Definição de perfis válidos como constante para validação (sugestão para consistência e manutenção)
PERFIS_VALIDOS = ['analista', 'dev', 'coordenador']  # Adicione mais perfis conforme necessário
perfil_logado = str(st.session_state.get('perfil', 'analista')).lower()
if perfil_logado not in PERFIS_VALIDOS:  # Sugestão: Validação de perfil
    st.warning(f"Perfil '{perfil_logado}' não reconhecido. Usando default 'analista'.")
    perfil_logado = 'analista'

# Configuração do diretório de upload (sem mudanças significativas, mas com comentário para segurança)
UPLOAD_DIR = "uploads_wiki"
os.makedirs(UPLOAD_DIR, exist_ok=True)  # Em produção, considere usar armazenamento em nuvem para maior segurança

# ==========================================
# 2. FUNÇÕES DE CACHE (Trazidas das Pages 6 e 8)
# ==========================================
@st.cache_data(ttl=3600)
def carregar_wikis():
    try: 
        engine = get_connection()
        query = "SELECT * FROM base_conhecimento WHERE origem = 'WIKI_HELPDESK' ORDER BY criado_em DESC"
        df = pd.read_sql(query, engine)
        return df, None
    except Exception as e: 
        return pd.DataFrame(), str(e)

@st.cache_data(ttl=3600)
def carregar_manuais():
    try:
        engine = get_connection()
        # Apontando para a tabela correta e filtrando pela origem exata
        query = "SELECT * FROM base_conhecimento WHERE origem = 'MANUAL_HELPDESK' ORDER BY criado_em DESC"
        df = pd.read_sql(query, engine)
        return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)

# ==========================================
# 3. TÍTULO E DESCRIÇÃO
# ==========================================
st.title("🧠 Central de Conhecimento")
st.markdown("Respostas rápidas, manuais do PostoGestor, wikis do HelpDesk e conhecimento colaborativo centralizados em um só lugar!")

# ==========================================
# 4. DEFINIÇÃO DAS ABAS (Nova Ordem de UX)
# ==========================================
if perfil_logado in ['coordenador', 'dev']:
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
    from utils import NIVEIS_CONHECIMENTO, calcular_patente

    engine = get_connection()
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
                use_container_width=True, 
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
                        with engine.begin() as conn_log: conn_log.execute(text("INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens) VALUES (:u, :p, :r, 0, 0, 0)"), {"u": usuario_logado_id, "p": hist_pergunta_original, "r": resposta_cache})
                    except Exception as e: st.error(f"Erro ranking: {e}")
                
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
                    acesso_ia_liberado = perfil_logado in ['coordenador', 'dev']
                    
                    if acesso_ia_liberado:
                        import google.generativeai as genai
                        from dotenv import load_dotenv
                        try:
                            load_dotenv()
                            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            prompt = f"Responda diretamente. DÚVIDA: {pergunta}\n\nCONTEXTO:\n{texto_contexto}" if texto_contexto else f"Diga que não achou manuais para: {', '.join(fatias_nova)}."
                            resposta_ia = model.generate_content(prompt)
                            t_prompt = resposta_ia.usage_metadata.prompt_token_count
                            t_resp = resposta_ia.usage_metadata.candidates_token_count
                            t_total = resposta_ia.usage_metadata.total_token_count
                            
                            st.success("⚡ Resposta gerada!")
                            st.markdown(resposta_ia.text)
                            st.caption(f"🔋 Tokens: {t_total}")
                            try:
                                with engine.begin() as conn_log: conn_log.execute(text("INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens) VALUES (:u, :p, :r, :tp, :tr, :tt)"), {"u": usuario_logado_id, "p": pergunta.strip(), "r": resposta_ia.text, "tp": t_prompt, "tr": t_resp, "tt": t_total})
                            except Exception as db_e: st.error(f"Erro BD: {db_e}")
                        except Exception as e: st.error(f"❌ Erro IA: {e}")
                    else:
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
        with st.expander("🏆 Ver os assuntos mais pesquisados nas Wikis"):
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
                st.dataframe(df_rank_wiki, width='stretch', hide_index=True)
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

            # Lógica Intacta
            if btn_buscar_wiki and termo_busca_wiki.strip():
                try:
                    with engine.begin() as conn_log:
                        conn_log.execute(text("""
                            INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                            VALUES (:u, :p, 'Busca Inteligente Wiki', 0, 0, 0)
                        """), {"u": usuario_logado_id, "p": f"[WIKI] {termo_busca_wiki.strip()}"})
                except Exception as e:
                    st.error(f"Erro ao registrar métrica de busca: {e}")

                import unicodedata, re
                def norm_text(t):
                    return re.sub(r'[^a-z0-9\s]', '', unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8').lower()).strip()
                
                stopwords = {'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'em', 'para', 'com', 'como'}
                fatias = [p for p in norm_text(termo_busca_wiki).split() if p not in stopwords and len(p) > 2]

                if fatias:
                    def calcular_score(row):
                        score = 0
                        tit = norm_text(row.get('titulo', ''))
                        cat = norm_text(row.get('categoria', ''))
                        cont = norm_text(row.get('conteudo', ''))
                        for f in fatias:
                            if f in tit: score += 3
                            if f in cat: score += 2
                            if f in cont: score += 1
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
        with st.expander("🏆 Ver os assuntos mais pesquisados nos Manuais"):
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
                st.dataframe(df_rank_man, width='stretch', hide_index=True)
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

            # Lógica Intacta
            if btn_buscar_manual and termo_busca_manual.strip():
                try:
                    with engine.begin() as conn_log:
                        conn_log.execute(text("""
                            INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                            VALUES (:u, :p, 'Busca Inteligente Manual', 0, 0, 0)
                        """), {"u": usuario_logado_id, "p": f"[MANUAL] {termo_busca_manual.strip()}"})
                except Exception as e:
                    st.error(f"Erro ao registrar métrica de busca: {e}")

                import unicodedata, re
                def norm_text(t):
                    return re.sub(r'[^a-z0-9\s]', '', unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8').lower()).strip()
                
                stopwords = {'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'em', 'para', 'com', 'como'}
                fatias = [p for p in norm_text(termo_busca_manual).split() if p not in stopwords and len(p) > 2]

                if fatias:
                    def calcular_score_m(row):
                        score = 0
                        tit = norm_text(row.get('titulo', ''))
                        cat = norm_text(row.get('categoria', ''))
                        cont = norm_text(row.get('conteudo', ''))
                        for f in fatias:
                            if f in tit: score += 3
                            if f in cat: score += 2
                            if f in cont: score += 1
                        return score

                    df_m['score'] = df_m.apply(calcular_score_m, axis=1)
                    df_m = df_m[df_m['score'] > 0].sort_values(by='score', ascending=False)

            st.markdown("<br>", unsafe_allow_html=True)
            
            # Exibição
            if btn_buscar_manual and termo_busca_manual.strip() and df_m.empty:
                st.warning(f"Nenhum manual encontrado para as palavras-chave: **'{termo_busca_manual}'**.")
            elif btn_buscar_manual and termo_busca_manual.strip():
                st.markdown(f"**📖 Resultados Encontrados ({len(df_m)}) - Ordenados por relevância**")
                for _, row in df_m.head(20).iterrows():
                    titulo = row.get('titulo', 'Sem Título')
                    conteudo = row.get('conteudo', 'Nenhum conteúdo disponível.')
                    anexo = row.get('caminho_anexo', '')
                    tag_score = f"⭐ Score: {row['score']}"
                    
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
    col_hist, col_rank = st.columns([2, 1])
    
    with col_hist:
        st.markdown("#### 🔍 Últimas Perguntas buscadas")
        with engine.connect() as conn:
            query_recentes = text("SELECT pergunta, resposta_ia, nome, data_busca FROM (SELECT DISTINCT ON (lower(h.pergunta)) h.pergunta, h.resposta_ia, u.nome, to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') as data_busca, h.criado_em FROM historico_buscas_psy h LEFT JOIN usuarios u ON h.usuario_id = u.id ORDER BY lower(h.pergunta), h.criado_em DESC) sub ORDER BY criado_em DESC LIMIT 15")
            df_recentes = pd.read_sql(query_recentes, conn)
        if not df_recentes.empty:
            for idx, row in df_recentes.iterrows():
                nome_autor = row['nome'] if row['nome'] else 'Membro da Equipe'
                with st.expander(f"👤 {nome_autor} buscou: {row['pergunta']} ({row['data_busca']})"): st.markdown(row['resposta_ia'])
        else: st.info("Ainda não há registros de buscas ao Psy.")
            
    with col_rank:
        st.markdown("#### 🏆 Top 10 Assuntos")
        with engine.connect() as conn:
            query_ranking_buscas = text("SELECT INITCAP(lower(pergunta)) as \"Assunto\", COUNT(id) as \"Volume\" FROM historico_buscas_psy GROUP BY lower(pergunta) ORDER BY \"Volume\" DESC LIMIT 10")
            df_ranking_buscas = pd.read_sql(query_ranking_buscas, conn)
        if not df_ranking_buscas.empty: st.dataframe(df_ranking_buscas, width='stretch', hide_index=True)


# # ==========================================
# # ABA 6: NOVA CONTRIBUIÇÃO (INSERÇÃO MANUAL)
# # ==========================================
# with aba_nova:
#     st.markdown("### 📝 Adicionar Nova Contribuição")
    
#     # Usamos clear_on_submit=True para limpar automaticamente os campos após salvar
#     with st.form("form_contribuicao", clear_on_submit=True):
#         titulo = st.text_input(
#             "📌 Título", 
#             placeholder="Título claro e objetivo"
#         )
        
#         col1, col2 = st.columns(2)
#         with col1:
#             categoria = st.text_input(
#                 "📂 Categoria", 
#                 placeholder="Ex: Hardware, Software, Rede..."
#             )
#         with col2:
#             subcategoria = st.text_input(
#                 "📁 Subcategoria", 
#                 placeholder="Ex: Impressoras, Windows, VPN..."
#             )
        
#         conteudo = st.text_area(
#             "📝 Conteúdo", 
#             height=250,
#             placeholder="Descrição detalhada do conhecimento..."
#         )
        
#         st.markdown("---")
#         st.markdown("📎 **Anexar Evidências ou Documentos**")
        
#         # Aceitando todos os formatos solicitados
#         arquivo_anexo = st.file_uploader(
#             "Formatos aceitos: PDF, TXT, CSV, XLSX, XML, SQL, Imagens, Áudio, Vídeo, Sistemas", 
#             type=["pdf", "txt", "csv", "xlsx", "xls", "xml", "sql", "png", "jpg", "jpeg", "pgz", "fr3", "mp3", "mp4"]
#         )
        
#         btn_salvar = st.form_submit_button("💾 Salvar Contribuição", type="primary")
        
#         if btn_salvar:
#             if not titulo or not categoria or not conteudo:
#                 st.warning("⚠️ Preencha pelo menos o Título, Categoria e Conteúdo.")
#             else:
#                 # Processa anexo se houver
#                 texto_extraido = ""
#                 caminho_anexo_db = None
                
#                 if arquivo_anexo:
#                     with st.spinner("A processar anexo..."):
#                         # Salva o arquivo fisicamente no diretório
#                         nome_seguro = f"{int(time.time())}_{arquivo_anexo.name.replace(' ', '_')}"
#                         caminho_fisico = os.path.join(UPLOAD_DIR, nome_seguro)
                        
#                         with open(caminho_fisico, "wb") as f:
#                             f.write(arquivo_anexo.getbuffer())
#                         caminho_anexo_db = caminho_fisico
                        
#                         # Extrai texto de documentos suportados (ignora ficheiros multimédia/sistemas)
#                         ext = arquivo_anexo.name.split('.')[-1].lower()
#                         try:
#                             if ext in ['txt', 'sql', 'xml', 'csv']:
#                                 texto_extraido = arquivo_anexo.getvalue().decode('utf-8', errors='ignore')
#                             elif ext == 'pdf':
#                                 import PyPDF2
#                                 pdf_reader = PyPDF2.PdfReader(arquivo_anexo)
#                                 texto_extraido = " ".join([
#                                     p.extract_text() for p in pdf_reader.pages if p.extract_text()
#                                 ])
#                             elif ext in ['xlsx', 'xls']:
#                                 import pandas as pd
#                                 texto_extraido = pd.read_excel(arquivo_anexo).to_string()
#                         except Exception as e:
#                             st.warning(f"Anexo guardado com sucesso, mas o texto não pôde ser extraído: {e}")
                
#                 # Prepara o conteúdo final agregando o texto extraído (se existir)
#                 conteudo_final = conteudo.strip()
#                 if texto_extraido:
#                     conteudo_final += f"\n\n--- CONTEÚDO DO ANEXO ---\n{texto_extraido}"
                
#                 # Salva no banco de dados
#                 try:
#                     with engine.begin() as conn:
#                         status_inicial = "APROVADO" if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor'] else "PENDENTE"
                        
#                         conn.execute(
#                             text("""
#                                 INSERT INTO base_conhecimento 
#                                 (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor, status, caminho_anexo, qtd_tentativas) 
#                                 VALUES ('CONHECIMENTO_SUPORTE', :t, :c, :s, :co, :a, :st, :ax, 1)
#                             """),
#                             {
#                                 "t": titulo.strip(),
#                                 "c": categoria.strip().upper(),
#                                 "s": subcategoria.strip().upper() if subcategoria else "GERAL",
#                                 "co": conteudo_final,
#                                 "a": usuario_logado_id,
#                                 "st": status_inicial,
#                                 "ax": caminho_anexo_db
#                             }
#                         )
                    
#                     st.success("✅ Contribuição salva com sucesso!")
                    
#                     # Regista na auditoria (se a função existir no seu código base)
#                     try:
#                         registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}")
#                     except NameError:
#                         pass # Ignora caso o módulo de auditoria não esteja ativo
                        
#                     time.sleep(2)
#                     st.rerun()
                    
#                 except Exception as e:
#                     st.error(f"❌ Erro ao salvar na base de dados: {str(e)}")
#                     try:
#                         logger.error(f"Erro BD: {e}")
#                     except NameError:
#                         pass

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
            type=["pdf", "txt", "csv", "xlsx", "xls", "xml", "sql", "png", "jpg", "jpeg", "pgz", "fr3", "mp3", "mp4"]
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
                    with st.spinner("Processando anexo..."):
                        nome_seguro = f"{int(time.time())}_{arquivo_anexo.name.replace(' ', '_')}"
                        caminho_fisico = os.path.join(UPLOAD_DIR, nome_seguro)
                        
                        with open(caminho_fisico, "wb") as f:
                            f.write(arquivo_anexo.getbuffer())
                        caminho_anexo_db = caminho_fisico
                        
                        ext = arquivo_anexo.name.split('.')[-1].lower()
                        try:
                            if ext in ['txt', 'sql', 'xml', 'csv']:
                                texto_extraido = arquivo_anexo.getvalue().decode('utf-8', errors='ignore')
                            elif ext == 'pdf':
                                import PyPDF2
                                pdf_reader = PyPDF2.PdfReader(arquivo_anexo)
                                texto_extraido = " ".join([p.extract_text() for p in pdf_reader.pages if p.extract_text()])
                            elif ext in ['xlsx', 'xls']:
                                import pandas as pd
                                texto_extraido = pd.read_excel(arquivo_anexo).to_string()
                        except Exception as e:
                            st.warning(f"Texto não extraído: {e}")

                conteudo_final = conteudo.strip()
                if texto_extraido:
                    conteudo_final += f"\n\n--- CONTEÚDO DO ANEXO ---\n{texto_extraido}"
                
                try:
                    with engine.begin() as conn:
                        status_inicial = "APROVADO" if perfil_logado in ['coordenador', 'dev'] else "PENDENTE"
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
                    
                    try:
                        registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}")
                    except NameError: pass
                        
                    time.sleep(1.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao salvar: {str(e)}")

# ==========================================
# ABA 7: MINHAS CONTRIBUIÇÕES (Com Correção de Rejeitados)
# ==========================================
with aba_minhas:
    st.subheader("📚 Minhas Contribuições")
    with engine.connect() as conn:
        # Trazendo a nova coluna qtd_tentativas
        query_minhas = text("""
            SELECT id, titulo, categoria, subcategoria, status, motivo_rejeicao, conteudo, caminho_anexo, qtd_tentativas 
            FROM base_conhecimento 
            WHERE origem = 'CONHECIMENTO_SUPORTE' AND id_analista_autor = :a 
            ORDER BY criado_em DESC
        """)
        df_minhas = pd.read_sql(query_minhas, conn, params={"a": usuario_logado_id})
        
    if not df_minhas.empty:
        for _, row in df_minhas.iterrows():
            cor_status = "🟢" if row['status'] == "APROVADO" else "🟡" if row['status'] == "PENDENTE" else "🔴"
            
            with st.expander(f"{cor_status} {row['titulo']} (Status: {row['status']})"):
                st.write(f"**Categoria:** `{row['categoria']}` ➔ `{row['subcategoria']}`")
                st.caption(f"🔄 Tentativas de aprovação: {row.get('qtd_tentativas', 1)}")
                
                if row['caminho_anexo'] and os.path.exists(row['caminho_anexo']):
                    with open(row['caminho_anexo'], "rb") as f: 
                        st.download_button("📎 Anexo", f, file_name=os.path.basename(row['caminho_anexo']), key=f"dl_m_{row['id']}")
                
                if row['status'] == 'REJEITADO':
                    st.error(f"⚠️ **Motivo da Rejeição:** {row['motivo_rejeicao']}")
                    st.info("Corrija o conteúdo abaixo com base no feedback e reenvie para avaliação.")
                    
                    # Formulário de Reenvio Interativo
                    with st.form(key=f"form_reenvio_{row['id']}"):
                        novo_titulo = st.text_input("Corrigir Título:", value=row['titulo'])
                        novo_conteudo = st.text_area("Corrigir Conteúdo:", value=row['conteudo'], height=200)
                        
                        col_btn1, col_btn2 = st.columns([1, 1])
                        with col_btn1:
                            if st.form_submit_button("🚀 Corrigir e Reenviar", type="primary"):
                                try:
                                    with engine.begin() as conn_upd:
                                        query_upd = text("""
                                            UPDATE base_conhecimento 
                                            SET titulo = :t, conteudo = :c, status = 'PENDENTE', 
                                                motivo_rejeicao = NULL, qtd_tentativas = COALESCE(qtd_tentativas, 1) + 1 
                                            WHERE id = :id
                                        """)
                                        conn_upd.execute(query_upd, {"t": novo_titulo, "c": novo_conteudo, "id": row['id']})
                                    st.success("Reenviado para avaliação!"); time.sleep(1); st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao reenviar: {e}")
                        
                        # Mantém a opção de excluir permanentemente caso ele desista
                        with col_btn2:
                            if st.form_submit_button("🗑️ Desistir e Excluir"):
                                try:
                                    with engine.begin() as conn_del: 
                                        conn_del.execute(text("DELETE FROM base_conhecimento WHERE id = :id"), {"id": row['id']})
                                    st.success("Excluído permanentemente!"); time.sleep(1); st.rerun()
                                except Exception as e: 
                                    st.error(f"Erro ao excluir: {e}")
                else: 
                    st.write(row['conteudo'])
    else: 
        st.info("Nenhuma contribuição sua encontrada. Participe e ganhe pontos no ranking!")

# ==========================================
# ABA 8: FILA DE AVALIAÇÃO (Apenas Coordenadores e Desenvolvedores)
# ==========================================
if perfil_logado in ['coordenador', 'dev']:
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
                                st.success("Documento homologado e publicado na Base!"); time.sleep(1); st.rerun()
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
                                    st.success("Devolvido ao autor para correções!"); time.sleep(1); st.rerun()
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
                    cat_query = text("SELECT DISTINCT categoria FROM base_conhecimento WHERE status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE' ORDER BY categoria")
                    categorias_disponiveis = [row[0] for row in conn.execute(cat_query).fetchall() if row[0]]
            except:
                categorias_disponiveis = []
                
            categorias_disponiveis.insert(0, "Todas as Categorias")
            categoria_selecionada = st.selectbox("Filtrar por Categoria:", categorias_disponiveis)

    # --- 2. MONTAGEM DA QUERY ---
    query_base = """
        SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo, 
               COALESCE(b.qtd_upvotes, 0) as qtd_upvotes, 
               COALESCE(b.qtd_visualizacoes, 0) as qtd_visualizacoes,
               to_char(b.criado_em, 'DD/MM/YYYY') as data_pub, u.nome AS autor,
               EXISTS(SELECT 1 FROM base_conhecimento_votos v 
                      WHERE v.id_conhecimento = b.id AND v.id_analista_votante = :uid) as ja_curtiu
        FROM base_conhecimento b 
        LEFT JOIN usuarios u ON b.id_analista_autor = u.id 
        WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status = 'APROVADO'
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
            for _, row in df_conhecimento.iterrows():
                with st.container(border=True):
                    col_txt, col_btn = st.columns([4, 1.2])
                    
                    with col_txt:
                        st.markdown(f"### {row['titulo']}")
                        st.caption(f"📂 {row['categoria']} | ✍️ {row['autor']} | 📅 {row['data_pub']}")
                    
                    with col_btn:
                        # Botão de Curtir/Descurtir
                        label = f"❤️ {row['qtd_upvotes']}" if row['ja_curtiu'] else f"🤍 {row['qtd_upvotes']}"
                        if st.button(label, key=f"lk_{row['id']}", use_container_width=True):
                            with engine.begin() as conn_voto:
                                if row['ja_curtiu']:
                                    conn_voto.execute(text("DELETE FROM base_conhecimento_votos WHERE id_conhecimento = :pid AND id_analista_votante = :uid"), {"pid": row['id'], "uid": usuario_id})
                                    # Ajuste: Decrementar qtd_upvotes na tabela base_conhecimento (se não houver trigger no BD)
                                    conn_voto.execute(text("UPDATE base_conhecimento SET qtd_upvotes = qtd_upvotes - 1 WHERE id = :pid AND qtd_upvotes > 0"), {"pid": row['id']})
                                else:
                                    conn_voto.execute(text("INSERT INTO base_conhecimento_votos (id_conhecimento, id_analista_votante) VALUES (:pid, :uid)"), {"pid": row['id'], "uid": usuario_id})
                                    # Ajuste: Incrementar qtd_upvotes na tabela base_conhecimento (se não houver trigger no BD)
                                    conn_voto.execute(text("UPDATE base_conhecimento SET qtd_upvotes = COALESCE(qtd_upvotes, 0) + 1 WHERE id = :pid"), {"pid": row['id']})
                            st.rerun()

                        # Botão Obsoleto
                        if st.button("⚠️ Obsoleto", key=f"obs_{row['id']}", use_container_width=True):
                            with engine.begin() as conn_obs:
                                conn_obs.execute(text("UPDATE base_conhecimento SET status = 'REVISAO_PENDENTE' WHERE id = :pid"), {"pid": row['id']})
                            st.warning("Enviado para revisão!")
                            time.sleep(1)
                            st.rerun()

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

# with aba_explorar:
#     st.title("🔎 Explorar Base de Conhecimento")
#     st.markdown("Consulte as contribuições aprovadas pela equipa, visualize evidências e descarregue os anexos necessários.")
    
#     # --- 1. ÁREA DE FILTROS (Layout Responsivo) ---
#     with st.container(border=True):
#         st.markdown("#### 🎯 Filtros de Pesquisa")
#         col_busca, col_cat = st.columns([2, 1])
        
#         with col_busca:
#             termo_pesquisa = st.text_input("Pesquisar por Título ou Conteúdo:", placeholder="Ex: Erro impressora fiscal...")
        
#         with col_cat:
#             # Busca categorias dinamicamente para o selectbox
#             try:
#                 with engine.connect() as conn:
#                     cat_query = text("SELECT DISTINCT categoria FROM base_conhecimento WHERE status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE' ORDER BY categoria")
#                     categorias_disponiveis = [row[0] for row in conn.execute(cat_query).fetchall() if row[0]]
#             except Exception:
#                 categorias_disponiveis = []
                
#             categorias_disponiveis.insert(0, "Todas as Categorias")
#             categoria_selecionada = st.selectbox("Filtrar por Categoria:", categorias_disponiveis)

#     st.markdown("<br>", unsafe_allow_html=True)

#     # --- 2. CONSULTA AO BANCO DE DADOS ---
#     try:
#         with engine.connect() as conn:
#             # Montagem dinâmica da query baseada nos filtros
#             query_base = """
#                 SELECT b.id, b.titulo, b.categoria, b.subcategoria, b.conteudo, b.caminho_anexo, 
#                        to_char(b.criado_em, 'DD/MM/YYYY') as data_pub, u.nome AS autor 
#                 FROM base_conhecimento b 
#                 LEFT JOIN usuarios u ON b.id_analista_autor = u.id 
#                 WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status = 'APROVADO'
#             """
            
#             params = {}
#             if termo_pesquisa.strip():
#                 query_base += " AND (b.titulo ILIKE :termo OR b.conteudo ILIKE :termo)"
#                 params["termo"] = f"%{termo_pesquisa.strip()}%"
                
#             if categoria_selecionada != "Todas as Categorias":
#                 query_base += " AND b.categoria = :cat"
#                 params["cat"] = categoria_selecionada
                
#             query_base += " ORDER BY b.criado_em DESC LIMIT 50" # Limite de paginação para performance
            
#             df_conhecimento = pd.read_sql(text(query_base), conn, params=params)
            
#     except Exception as e:
#         st.error(f"❌ Erro ao carregar a base de conhecimento: {e}")
#         df_conhecimento = pd.DataFrame()

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
                        st.image(str(caminho_anexo), caption="Imagem em Anexo", use_container_width=True)
                        
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