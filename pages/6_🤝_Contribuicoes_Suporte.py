import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection
import os
import time
import unicodedata
import re
from difflib import SequenceMatcher

try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass

# ==========================================
# 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# ==========================================
st.set_page_config(page_title="WikiSuporte </>", page_icon="🏆", layout="wide")

if not st.session_state.get('autenticado'): 
    st.switch_page("app.py")

usuario_logado_id = st.session_state.get('usuario_id')
perfil_logado = str(st.session_state.get('perfil', 'analista')).lower()

UPLOAD_DIR = "uploads_wiki"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
st.title("🤝 Central Única de Conhecimento")
st.markdown("Respostas rápidas, manuais do PostoGestor, wikis do HelpDesk e conhecimento colaborativo centralizados em um só lugar!")

# ==========================================
# 4. DEFINIÇÃO DAS ABAS (Nova Ordem de UX)
# ==========================================
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
    abas = st.tabs([
        "🏅 Inicio & Ranking", 
        "🤖 Assistente Virtual - Psy", 
        "📘 Wikis Helpdesk", 
        "📙 Manuais PostoGestor", 
        "📖 Histórico de Buscas", 
        "📝 Nova Contribuição", 
        "📚 Minhas Contribuições", 
        "⚖️ Fila de Avaliação"
    ])
    aba_ranking, aba_gemini, aba_wikis, aba_manuais, aba_arquivo, aba_nova, aba_minhas, aba_fila = abas
else:
    abas = st.tabs([
        "🏅 Home & Ranking", 
        "🤖 Psy Assistente (IA)", 
        "📘 Wikis Helpdesk", 
        "📙 Manuais PostoGestor", 
        "📖 Histórico de Buscas", 
        "📝 Nova Contribuição", 
        "📚 Minhas Contribuições"
    ])
    aba_ranking, aba_gemini, aba_wikis, aba_manuais, aba_arquivo, aba_nova, aba_minhas = abas

# ==========================================
# ABA 1: GAMIFICAÇÃO E RANKING (Cards Removidos)
# ==========================================
with aba_ranking:
    st.subheader("🏅 Ranking dos Contribuidores de Suporte")
    st.info("Sua contribuição é a força vital do nosso suporte! Cada dica aprovada vale pontos, e os melhores recebem troféus simbólicos.")
    
    engine = get_connection()
    with engine.connect() as conn:
        query_ranking = text("""
            SELECT u.nome AS "Analista", 
                   COUNT(b.id) AS "Dicas Aprovadas", 
                   (COUNT(b.id) * 50) AS "XP Total"
            FROM base_conhecimento b
            JOIN usuarios u ON b.id_analista_autor = u.id
            WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status = 'APROVADO'
            GROUP BY u.nome
            ORDER BY "XP Total" DESC
        """)
        df_ranking = pd.read_sql(query_ranking, conn)
        
        if not df_ranking.empty:
            trofeus = []
            for i in range(len(df_ranking)):
                if i == 0: trofeus.append("🥇 Ouro")
                elif i == 1: trofeus.append("🥈 Prata")
                elif i == 2: trofeus.append("🥉 Bronze")
                else: trofeus.append("🏅 Honra")
            
            df_ranking.insert(0, "Troféu", trofeus)
            st.dataframe(df_ranking, width='stretch', hide_index=True)
        else:
            st.write("Nenhuma contribuição aprovada ainda. Seja o primeiro a contribuir!")

# ==========================================
# ABA 2: MOTOR DE BUSCA HÍBRIDO (Com IA Inteligente)
# ==========================================
with aba_gemini:
    st.subheader("🤖 Pesquisar com o Psy")
    pergunta = st.text_input("Informe sua dúvida: ", placeholder="Ex: Como configurar o e-mail no PostoGestor?", key="input_psy")
    
    if st.button("🔍 Buscar no Motor Psy", type="primary"):
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
                    acesso_ia_liberado = perfil_logado in ['administrador', 'superadmin', 'coordenação', 'desenvolvedor']
                    
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
# ABA 3: WIKIS HELPDESK (COM BUSCA INTELIGENTE E RANKING)
# ==========================================
with aba_wikis:
    st.subheader("📚 Acervo Helpdesk")
    st.markdown("Consulte procedimentos, manuais e resoluções de erros do Helpdesk para agilizar os seus atendimentos.")

    df_wikis, erro_bd = carregar_wikis()

    # --- 🏆 RANKING DAS WIKIS MAIS BUSCADAS ---
    st.markdown("##### 🏆 Termos mais pesquisados nas Wikis")
    with engine.connect() as conn:
        # Filtra apenas buscas com o prefixo oculto [WIKI] e remove o prefixo na exibição
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

    st.divider()

    # --- 🔍 MOTOR DE BUSCA INTELIGENTE (SEM CUSTO DE IA) ---
    col_busca_w, col_btn_w = st.columns([4, 1])
    with col_busca_w:
        termo_busca_wiki = st.text_input("🔍 O que você está procurando nas Wikis?", placeholder="Ex: Erro nota fiscal...", key="busca_wiki_input")
    with col_btn_w:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_buscar_wiki = st.button("Pesquisar Wiki", width='stretch', type="primary")

    if erro_bd: 
        st.error(f"❌ Ocorreu um erro técnico: `{erro_bd}`")
    elif df_wikis.empty: 
        st.info("O acervo de Wikis do Helpdesk está vazio.")
    else:
        df_w = df_wikis.copy()

        # Se o usuário clicou em buscar e digitou algo
        if btn_buscar_wiki and termo_busca_wiki.strip():
            # 1. Registra a busca silenciosamente no banco para alimentar o Ranking
            try:
                with engine.begin() as conn_log:
                    conn_log.execute(text("""
                        INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                        VALUES (:u, :p, 'Busca Inteligente Wiki', 0, 0, 0)
                    """), {"u": usuario_logado_id, "p": f"[WIKI] {termo_busca_wiki.strip()}"})
            except Exception as e:
                st.error(f"Erro ao registrar métrica de busca: {e}")

            # 2. Lógica de Scoring (Motor a Combustão no Pandas)
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
                        if f in tit: score += 3  # Peso maior pro Título
                        if f in cat: score += 2  # Peso médio pra Categoria
                        if f in cont: score += 1 # Peso menor pro Conteúdo
                    return score

                df_w['score'] = df_w.apply(calcular_score, axis=1)
                df_w = df_w[df_w['score'] > 0].sort_values(by='score', ascending=False)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Exibição dos resultados
        if btn_buscar_wiki and termo_busca_wiki.strip() and df_w.empty:
            st.warning(f"Nenhum documento encontrado para as palavras-chave: **'{termo_busca_wiki}'**.")
        else:
            if btn_buscar_wiki and termo_busca_wiki.strip():
                st.markdown(f"**📖 Resultados Encontrados ({len(df_w)}) - Ordenados por relevância**")
            
            # Mostra apenas os top 20 para não travar a tela
            for _, row in df_w.head(20).iterrows():
                titulo = row.get('titulo', 'Sem Título')
                categoria = row.get('categoria', 'Geral')
                subcategoria = row.get('subcategoria', 'Não especificada')
                conteudo = row.get('conteudo', 'Nenhum conteúdo descrito.')
                
                # Tag visual de relevância caso tenha feito a busca
                tag_score = f"⭐ Score: {row['score']}" if 'score' in df_w.columns else ""
                
                with st.expander(f"📑 {titulo} {tag_score}"):
                    st.markdown(f"**📂 Categoria:** `{categoria}` ➔ `{subcategoria}`")
                    st.divider()
                    st.markdown("#### 📖 Conteúdo")
                    st.markdown(conteudo)
                    if pd.notna(row.get('caminho_anexo')) and str(row.get('caminho_anexo')).strip():
                        st.info(f"📎 **Anexo disponível em:** {row['caminho_anexo']}")

# ==========================================
# ABA 4: MANUAIS POSTOGESTOR (Antiga Page 8)
# ==========================================
# ==========================================
# ABA 4: MANUAIS POSTOGESTOR (COM BUSCA INTELIGENTE E RANKING)
# ==========================================
with aba_manuais:
    st.subheader("📙 Repositório de Manuais (PostoGestor)")
    st.markdown("Acesse as documentações e guias oficiais do PostoGestor.")

    df_manuais, erro_bd = carregar_manuais()

    # --- 🏆 RANKING DOS MANUAIS MAIS BUSCADOS ---
    st.markdown("##### 🏆 Termos mais pesquisados nos Manuais")
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

    st.divider()

    # --- 🔍 MOTOR DE BUSCA INTELIGENTE (SEM CUSTO DE IA) ---
    col_busca_m, col_btn_m = st.columns([4, 1])
    with col_busca_m:
        termo_busca_manual = st.text_input("🔍 O que você está procurando nos Manuais?", placeholder="Ex: Configurar impressora...", key="busca_manual_input")
    with col_btn_m:
        st.markdown("<br>", unsafe_allow_html=True)
        btn_buscar_manual = st.button("Pesquisar Manual", width='stretch', type="primary")

    if erro_bd:
        st.error(f"❌ Ocorreu um erro técnico: `{erro_bd}`")
    elif df_manuais.empty:
        st.warning("Nenhum manual com a origem 'MANUAL_HELPDESK' foi encontrado.")
    else:
        df_m = df_manuais.copy()

        # Se o usuário clicou em buscar e digitou algo
        if btn_buscar_manual and termo_busca_manual.strip():
            # 1. Registra a busca para o Ranking
            try:
                with engine.begin() as conn_log:
                    conn_log.execute(text("""
                        INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                        VALUES (:u, :p, 'Busca Inteligente Manual', 0, 0, 0)
                    """), {"u": usuario_logado_id, "p": f"[MANUAL] {termo_busca_manual.strip()}"})
            except Exception as e:
                st.error(f"Erro ao registrar métrica de busca: {e}")

            # 2. Lógica de Scoring
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
        
        # Exibição dos resultados
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
                            st.download_button("📎 Baixar Anexo", f, file_name=os.path.basename(str(anexo)), key=f"dl_man_{row.get('id', titulo)}")
        else:
            # Visão padrão (sem busca): Agrupado por categoria
            categorias = df_m['categoria'].fillna('Geral').unique()
            for cat in sorted(categorias):
                st.markdown(f"#### 📁 Categoria: {cat}")
                df_cat = df_m[df_m['categoria'] == cat]
                for _, row in df_cat.iterrows():
                    titulo = row.get('titulo', 'Sem Título')
                    with st.expander(f"📖 {titulo}"):
                        st.markdown(row.get('conteudo', ''))
                        anexo = row.get('caminho_anexo', '')
                        if pd.notna(anexo) and str(anexo).strip() and os.path.exists(str(anexo)):
                            with open(anexo, "rb") as f:
                                st.download_button("📎 Baixar Anexo", f, file_name=os.path.basename(str(anexo)), key=f"dl_man_def_{row.get('id', titulo)}")
                st.divider()
# ==========================================
# ABA 5: HISTÓRICO E RANKING DA EQUIPE
# ==========================================
with aba_arquivo:
    st.subheader("📖 Histórico e Ranking da Equipe")
    col_hist, col_rank = st.columns([2, 1])
    
    with col_hist:
        st.markdown("#### 🔍 Últimas Perguntas")
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

# ==========================================
# ABA 6: NOVA CONTRIBUIÇÃO
# ==========================================
with aba_nova:
    st.markdown("### 📝 Adicionar Nova Contribuição")
    with st.form("form_contribuicao", clear_on_submit=True):
        titulo = st.text_input("📌 Título", placeholder="Ex: Instalação de Certificado Digital...")
        col1, col2 = st.columns(2)
        with col1: categoria = st.text_input("📂 Categoria", placeholder="Ex: Financeiro")
        with col2: subcategoria = st.text_input("📁 Subcategoria", placeholder="Ex: Contas a Pagar")
        conteudo = st.text_area("🧠 Conteúdo", height=200)
        
        st.markdown("📎 **Anexar Evidências ou Manuais**")
        arquivo_anexo = st.file_uploader("Formatos: PDF, TXT, CSV, XLSX, XML, SQL, Imagens", type=["pdf", "txt", "csv", "xlsx", "xml", "sql", "png", "jpg", "jpeg"])
        btn_salvar = st.form_submit_button("🚀 Salvar Contribuição", type="primary")
        
        if btn_salvar:
            if not titulo or not categoria or not conteudo: 
                st.warning("⚠️ Preencha Título, Categoria e Conteúdo.")
            else:
                texto_extraido, caminho_db = "", None
                if arquivo_anexo is not None:
                    with st.spinner("Processando anexo..."):
                        nome_arquivo = f"{int(time.time())}_{arquivo_anexo.name.replace(' ', '_')}"
                        caminho_fisico = os.path.join(UPLOAD_DIR, nome_arquivo)
                        with open(caminho_fisico, "wb") as f: f.write(arquivo_anexo.getbuffer())
                        caminho_db = caminho_fisico
                        ext = arquivo_anexo.name.split('.')[-1].lower()
                        try:
                            if ext in ['txt', 'sql', 'xml', 'csv']: texto_extraido = arquivo_anexo.getvalue().decode('utf-8', errors='ignore')
                            elif ext == 'pdf':
                                import PyPDF2
                                texto_extraido = " ".join([p.extract_text() for p in PyPDF2.PdfReader(arquivo_anexo).pages if p.extract_text()])
                            elif ext in ['xlsx', 'xls']: texto_extraido = pd.read_excel(arquivo_anexo).to_string()
                            elif ext in ['png', 'jpg', 'jpeg']:
                                import google.generativeai as genai
                                from PIL import Image
                                from dotenv import load_dotenv
                                load_dotenv(); genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                                texto_extraido = f"[TEXTO DO PRINT]:\n{genai.GenerativeModel('gemini-2.5-flash').generate_content(['Transcreva.', Image.open(arquivo_anexo)]).text}"
                        except Exception as e: st.warning(f"Falha na extração, mas salvo: {e}")

                conteudo_final = conteudo.strip() + (f"\n\n--- DADOS DO ANEXO ---\n{texto_extraido}" if texto_extraido else "")
                try:
                    with engine.begin() as conn:
                        status_inicial = "APROVADO" if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor'] else "PENDENTE"
                        
                        # Inserindo com qtd_tentativas = 1 explicitamente (mesmo com o DEFAULT do BD)
                        query_insert = text("""
                            INSERT INTO base_conhecimento 
                            (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor, status, caminho_anexo, qtd_tentativas) 
                            VALUES ('CONHECIMENTO_SUPORTE', :t, :c, :s, :co, :a, :st, :ax, 1)
                        """)
                        conn.execute(query_insert, {
                            "t": titulo.strip(), "c": categoria.strip().upper(), 
                            "s": subcategoria.strip().upper() if subcategoria else "GERAL", 
                            "co": conteudo_final, "a": usuario_logado_id, 
                            "st": status_inicial, "ax": caminho_db
                        })
                    st.success("✅ Salvo e Aprovado!" if status_inicial == "APROVADO" else "✅ Enviado para a Fila de Avaliação!")
                    registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}")
                    time.sleep(2); st.rerun()
                except Exception as e: 
                    st.error(f"❌ Erro BD ao salvar contribuição: {e}")

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
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
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