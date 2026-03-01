import streamlit as st
import pandas as pd
from sqlalchemy import text
from modules.database import get_connection

try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(user_id: int, acao: str, detalhe: str) -> None: pass

# ==========================================
# 1. CONFIGURAÇÕES DA PÁGINA E SEGURANÇA
# ==========================================
st.set_page_config(page_title="WikiSuporte - Hub de Conhecimento", page_icon="🏆", layout="wide")

if not st.session_state.get('autenticado'): 
    st.switch_page("app.py")

usuario_logado_id = st.session_state.get('usuario_id')
perfil_logado = str(st.session_state.get('perfil', 'analista')).lower()

# ==========================================
# 2. CABEÇALHO E ABAS
# ==========================================
st.title("🏆 Hub de Conhecimento & Gamificação")
st.markdown("Compartilhe o seu conhecimento, suba no ranking da equipa e acesse o motor de busca unificado!")

# Define as abas dependendo do perfil (ADICIONADA A NOVA ABA 6: ARQUIVO PSY)
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
    aba_ranking, aba_nova, aba_minhas, aba_fila, aba_gemini, aba_arquivo = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "⚖️ Fila de Aprovação", "🤖 Busca PSY", "📖 Arquivo PSY"
    ])
else:
    aba_ranking, aba_nova, aba_minhas, aba_gemini, aba_arquivo = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "🤖 Busca PSY", "📖 Arquivo PSY"
    ])

# ==========================================
# ABA 1: GAMIFICAÇÃO E RANKING
# ==========================================
with aba_ranking:
    st.subheader("Leaderboard - Os Mestres do Suporte")
    st.info("💡 Cada contribuição aprovada vale **50 XP**. Compartilhe soluções e conquiste os troféus de Ouro, Prata e Bronze!")
    
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
            st.dataframe(df_ranking, use_container_width=True, hide_index=True)
        else:
            st.write("Ainda não temos campeões no ranking. Seja o primeiro!")

# ==========================================
# ABA 2: NOVA CONTRIBUIÇÃO (Regra da Fila)
# ==========================================
with aba_nova:
    st.markdown("### Enviar Nova Solução / Workaround")
    with st.form("form_contribuicao", clear_on_submit=True):
        titulo = st.text_input("📌 Título da Contribuição", placeholder="Ex: Erro X na Balança Toledo - Solução")
        col1, col2 = st.columns(2)
        with col1: categoria = st.text_input("📂 Categoria", placeholder="Ex: DICAS TECNUV")
        with col2: subcategoria = st.text_input("📁 Subcategoria", placeholder="Ex: BALANÇAS")
            
        conteudo = st.text_area("🧠 Passo a Passo da Solução", height=200)
        btn_salvar = st.form_submit_button("🚀 Submeter para Avaliação", type="primary")
        
        if btn_salvar:
            if not titulo or not categoria or not conteudo:
                st.warning("⚠️ Preencha Título, Categoria e Conteúdo.")
            else:
                try:
                    with engine.begin() as conn:
                        status_inicial = "APROVADO" if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor'] else "PENDENTE"
                        
                        query = text("""
                            INSERT INTO base_conhecimento (origem, titulo, categoria, subcategoria, conteudo, id_analista_autor, status)
                            VALUES ('CONHECIMENTO_SUPORTE', :tit, :cat, :subcat, :cont, :autor, :status)
                        """)
                        conn.execute(query, {
                            "tit": titulo.strip(), "cat": categoria.strip().upper(),
                            "subcat": subcategoria.strip().upper() if subcategoria else "GERAL",
                            "cont": conteudo.strip(), "autor": usuario_logado_id, "status": status_inicial
                        })
                        
                    if status_inicial == "PENDENTE":
                        st.success("✅ Contribuição enviada! Ela está na fila para avaliação. Ganhará os seus XP assim que aprovada!")
                    else:
                        st.success("✅ Contribuição salva e aprovada automaticamente!")
                        
                    registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}...")
                    import time; time.sleep(2); st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro no banco de dados: {e}")

# ==========================================
# ABA 3: MINHAS CONTRIBUIÇÕES
# ==========================================
with aba_minhas:
    st.subheader("O Seu Histórico de Conhecimento")
    with engine.connect() as conn:
        query_minhas = text("""
            SELECT id, titulo, categoria, status, motivo_rejeicao, conteudo
            FROM base_conhecimento 
            WHERE origem = 'CONHECIMENTO_SUPORTE' AND id_analista_autor = :autor
            ORDER BY criado_em DESC
        """)
        df_minhas = pd.read_sql(query_minhas, conn, params={"autor": usuario_logado_id})
        
    if not df_minhas.empty:
        for index, row in df_minhas.iterrows():
            cor_status = "🟢" if row['status'] == "APROVADO" else "🟡" if row['status'] == "PENDENTE" else "🔴"
            with st.expander(f"{cor_status} {row['titulo']} (Status: {row['status']})"):
                st.write(f"**Categoria:** {row['categoria']}")
                if row['status'] == 'REJEITADO':
                    st.error(f"**Motivo da Rejeição:** {row['motivo_rejeicao']}")
                    st.warning("Você deve recriar a dica na Aba 'Nova Contribuição' com os ajustes solicitados e, em seguida, excluir este registro.")
                    if st.button(f"🗑️ Excluir Contribuição Rejeitada", key=f"del_{row['id']}"):
                        try:
                            with engine.begin() as conn_del:
                                conn_del.execute(text("DELETE FROM base_conhecimento WHERE id = :id"), {"id": row['id']})
                            registrar_log_auditoria(usuario_logado_id, "EXCLUIU_REJEITADO", f"ID: {row['id']}")
                            st.success("Excluído com sucesso!"); import time; time.sleep(1); st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir: {e}")
                else:
                    st.write(row['conteudo'])
                    if row['status'] == 'APROVADO':
                        st.caption("🔒 Registros aprovados não podem ser alterados/excluídos. Solicite à coordenação.")
    else:
        st.info("Você ainda não possui contribuições.")

# ==========================================
# ABA 4: FILA DE APROVAÇÃO
# ==========================================
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
    with aba_fila:
        st.subheader("⚖️ Avaliação de Contribuições")
        with engine.connect() as conn:
            query_fila = text("""
                SELECT b.id, b.titulo, b.categoria, b.conteudo, u.nome AS autor
                FROM base_conhecimento b
                JOIN usuarios u ON b.id_analista_autor = u.id
                WHERE b.origem = 'CONHECIMENTO_SUPORTE' AND b.status = 'PENDENTE'
            """)
            df_fila = pd.read_sql(query_fila, conn)
            
        if not df_fila.empty:
            for index, row in df_fila.iterrows():
                with st.expander(f"⏳ {row['titulo']} (Autor: {row['autor']})"):
                    st.write(f"**Categoria:** {row['categoria']}")
                    st.info(row['conteudo'])
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Aprovar", key=f"apr_{row['id']}", type="primary"):
                            with engine.begin() as conn_apr:
                                conn_apr.execute(text("UPDATE base_conhecimento SET status = 'APROVADO' WHERE id = :id"), {"id": row['id']})
                            registrar_log_auditoria(usuario_logado_id, "APROVOU_DICA", f"ID: {row['id']}")
                            st.success("Aprovado!"); import time; time.sleep(1); st.rerun()
                    with c2:
                        motivo = st.text_input("Motivo da Rejeição:", key=f"motivo_{row['id']}")
                        if st.button("❌ Rejeitar", key=f"rej_{row['id']}"):
                            if not motivo: st.warning("Informe o motivo para o analista corrigir.")
                            else:
                                with engine.begin() as conn_rej:
                                    conn_rej.execute(text("UPDATE base_conhecimento SET status = 'REJEITADO', motivo_rejeicao = :m WHERE id = :id"), {"m": motivo, "id": row['id']})
                                registrar_log_auditoria(usuario_logado_id, "REJEITOU_DICA", f"ID: {row['id']}")
                                st.success("Devolvido ao autor!"); import time; time.sleep(1); st.rerun()
        else:
            st.success("🎉 Fila limpa!")

# ==========================================
# ABA 5: MOTOR DE BUSCA HÍBRIDO (COM INTERCEPTADOR DE CACHE)
# ==========================================
with aba_gemini:
    st.subheader("🤖 Motor de Busca PSY (Híbrido)")
    st.markdown("Busque informações nos **Manuais, Wikis e Dicas da Equipe**.")
    
    pergunta = st.text_input("Digite sua pesquisa:", placeholder="Ex: Como configurar a balança Toledo?")
    
    if st.button("🔍 Buscar", type="primary"):
        if not pergunta.strip():
            st.warning("Por favor, digite uma pergunta.")
        else:
            with st.spinner("Analisando cérebro neural..."):
                
                # ==========================================
                # 🛑 FASE 0: INTERCEPTADOR SEMÂNTICO (CACHE)
                # Verifica se a mesma pergunta já foi feita para não gastar API
                # ==========================================
                tem_no_cache = False
                with engine.connect() as conn:
                    # Remove acentos do BD e da pergunta para uma busca tolerante a erros
                    mapa_origem = 'áàâãäéèêëíìîïóòôõöúùûüçñ'
                    mapa_destino = 'aaaaaeeeeiiiiooooouuuucn'
                    query_cache = text(f"""
                        SELECT u.nome, h.resposta_ia, to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') as data_busca
                        FROM historico_buscas_psy h
                        LEFT JOIN usuarios u ON h.usuario_id = u.id
                        WHERE translate(lower(h.pergunta), '{mapa_origem}', '{mapa_destino}') = translate(lower(:pergunta_exata), '{mapa_origem}', '{mapa_destino}')
                        ORDER BY h.criado_em DESC LIMIT 1
                    """)
                    cache_result = conn.execute(query_cache, {"pergunta_exata": pergunta.strip()}).fetchone()
                
                if cache_result:
                    nome_colega, resposta_cache, data_cache = cache_result
                    nome_exibicao = nome_colega if nome_colega else "um colega da equipe"
                    
                    st.success(f"♻️ **Cache Ativado!** Você e **{nome_exibicao}** estão na mesma sintonia. Esta mesma dúvida foi resolvida pela IA hoje às {data_cache}.")
                    st.markdown(resposta_cache)
                    st.caption("⚡ **Motor Elétrico Poupado:** 0 Tokens consumidos nesta busca.")
                    tem_no_cache = True
                
                # Se NÃO tiver no cache, roda a IA normalmente
                if not tem_no_cache:
                    import os
                    import unicodedata
                    import re
                    
                    # === FASE 1: NORMALIZAÇÃO DE TEXTO ===
                    def normalizar_texto(texto):
                        texto_sem_acento = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
                        texto_limpo = re.sub(r'[^a-z0-9\s]', '', texto_sem_acento.lower())
                        return texto_limpo.strip()
                    
                    palavras_ignoradas = {'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'em', 'para', 'com', 'como', 'qual', 'quais', 'que', 'e', 'sobre', 'por', 'ou', 'onde', 'quando', 'fazer'}
                    
                    pergunta_normalizada = normalizar_texto(pergunta)
                    termos = pergunta_normalizada.split()
                    palavras_chave = [p for p in termos if p not in palavras_ignoradas and len(p) > 1]
                    
                    contextos_db = []
                    resultados_puros = []
                    
                    # === FASE 2: MOTOR A COMBUSTÃO (SQL SCORING) ===
                    if palavras_chave:
                        with engine.connect() as conn:
                            clausulas_or = []
                            clausulas_score = []
                            params = {}
                            
                            for i, p in enumerate(palavras_chave):
                                param_name = f"p{i}"
                                params[param_name] = f"%{p}%"
                                
                                clausula_like = f"(translate(lower(titulo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} OR translate(lower(conteudo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name})"
                                clausulas_or.append(clausula_like)
                                
                                clausula_peso = f"(CASE WHEN translate(lower(titulo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} THEN 2 ELSE 0 END) + (CASE WHEN translate(lower(conteudo), '{mapa_origem}', '{mapa_destino}') LIKE :{param_name} THEN 1 ELSE 0 END)"
                                clausulas_score.append(clausula_peso)
                                
                            filtros_sql = " OR ".join(clausulas_or)
                            score_sql = " + ".join(clausulas_score)
                            
                            query_rag = text(f"""
                                SELECT titulo, origem, conteudo, ({score_sql}) as pontuacao_relevancia
                                FROM base_conhecimento 
                                WHERE status = 'APROVADO' AND ({filtros_sql})
                                ORDER BY pontuacao_relevancia DESC
                                LIMIT 5
                            """)
                            
                            resultados = conn.execute(query_rag, params).fetchall()
                            for r in resultados:
                                contextos_db.append(f"📚 FONTE: {r[0]} ({r[1]})\nCONTEÚDO: {r[2]}")
                                resultados_puros.append({"titulo": r[0], "origem": r[1], "conteudo": r[2], "score": r[3]})
                    
                    texto_contexto = "\n\n---\n\n".join(contextos_db)
                    
                    # === FASE 3: VERIFICAÇÃO DE ACESSO (MOTOR ELÉTRICO) ===
                    acesso_ia_liberado = perfil_logado in ['administrador', 'superadmin', 'coordenação', 'desenvolvedor']
                    
                    if acesso_ia_liberado:
                        import google.generativeai as genai
                        from google.api_core.exceptions import ResourceExhausted
                        from dotenv import load_dotenv
                        import os
                        
                        try:
                            load_dotenv()
                            gemini_api_key = os.getenv("GEMINI_API_KEY")
                            if not gemini_api_key: raise ValueError("API Key não encontrada no arquivo .env.")

                            genai.configure(api_key=gemini_api_key)
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            
                            if texto_contexto:
                                prompt = f"""Você é o PSY, Especialista de Suporte do sistema PostoGestor.
                                Faça um RESUMO DIRETO E OBJETIVO para responder à dúvida do usuário, usando EXCLUSIVAMENTE o contexto oficial abaixo.
                                Seja didático. Se houver passo a passo, use bullet points ou numeração.
                                
                                DÚVIDA DO USUÁRIO: "{pergunta}"
                                
                                CONTEXTO OFICIAL ORDENADO POR RELEVÂNCIA:
                                {texto_contexto}
                                """
                            else:
                                prompt = f"O usuário perguntou sobre: '{pergunta}'. Avise educadamente que após filtrar as palavras '{', '.join(palavras_chave)}', não encontrou nenhum manual na base oficial."

                            resposta_ia = model.generate_content(prompt)
                            
                            try:
                                t_prompt = resposta_ia.usage_metadata.prompt_token_count
                                t_resp = resposta_ia.usage_metadata.candidates_token_count
                                t_total = resposta_ia.usage_metadata.total_token_count
                            except:
                                t_prompt = t_resp = t_total = 0
                                
                            st.success("⚡ Resumo Inteligente (PSY):")
                            st.markdown(resposta_ia.text)
                            st.caption(f"🔋 **Medidor de Tokens:** Gastou **{t_prompt}** p/ ler + **{t_resp}** p/ responder = **Total {t_total} Tokens**.")
                            
                            if resultados_puros:
                                st.info("👇 Documentos originais consultados para gerar este resumo:")
                                for doc in resultados_puros:
                                    with st.expander(f"📄 {doc['titulo']} ({doc['origem']}) - Score: {doc['score']}"):
                                        st.write(doc['conteudo'])
                            
                            try:
                                with engine.begin() as conn_log:
                                    conn_log.execute(text("""
                                        INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                                        VALUES (:u, :p, :r, :tp, :tr, :tt)
                                    """), {"u": usuario_logado_id, "p": pergunta.strip(), "r": resposta_ia.text, "tp": t_prompt, "tr": t_resp, "tt": t_total})
                            except Exception as db_e:
                                st.error(f"⚠️ Erro ao gravar histórico: {db_e}")
                                
                        except ResourceExhausted:
                            st.warning("⚠️ **Aviso Administrativo:** A IA Gemini atingiu a cota. O sistema ligou o **Motor a Combustão** (SQL)!")
                            if resultados_puros:
                                for doc in resultados_puros:
                                    with st.expander(f"📄 {doc['titulo']} ({doc['origem']}) - Score: {doc['score']}"):
                                        st.write(doc['conteudo'])
                            else:
                                st.write("Nenhum documento encontrado.")
                        except Exception as e:
                            st.error(f"❌ Erro na IA: {e}")
                    else:
                        # === FASE 4: ACESSO DE ANALISTAS (SÓ COMBUSTÃO) ===
                        st.info("🔧 Motor a Combustão: A IA (PSY) está restrita aos Administradores. Aqui estão os manuais:")
                        if resultados_puros:
                            for doc in resultados_puros:
                                with st.expander(f"📄 {doc['titulo']} ({doc['origem']}) - Score: {doc['score']}"):
                                    st.write(doc['conteudo'])
                        else:
                            st.warning("Nenhum documento oficial encontrado.")

# ==========================================
# ABA 6: ARQUIVO PSY (HISTÓRICO E RANKING DA EQUIPE)
# ==========================================
with aba_arquivo:
    st.subheader("📖 Arquivo PSY (Memória Coletiva)")
    st.markdown("Consulte as dúvidas já resolvidas pelo Motor Elétrico e descubra os temas mais quentes da nossa operação. As soluções aqui armazenadas servem de atalho para problemas recorrentes.")
    
    col_hist, col_rank = st.columns([2, 1])
    
    with col_hist:
        st.markdown("#### 🕒 Últimas Respostas da IA")
        with engine.connect() as conn:
            query_recentes = text("""
                SELECT h.pergunta, h.resposta_ia, u.nome, to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') as data_busca
                FROM historico_buscas_psy h
                LEFT JOIN usuarios u ON h.usuario_id = u.id
                ORDER BY h.criado_em DESC LIMIT 15
            """)
            df_recentes = pd.read_sql(query_recentes, conn)
            
        if not df_recentes.empty:
            for idx, row in df_recentes.iterrows():
                nome_autor = row['nome'] if row['nome'] else 'Membro da Equipe'
                with st.expander(f"👤 {nome_autor} buscou: {row['pergunta']} ({row['data_busca']})"):
                    st.markdown(row['resposta_ia'])
        else:
            st.info("Nenhuma busca foi registrada no cérebro do PSY ainda.")
            
    with col_rank:
        st.markdown("#### 🔥 Assuntos Mais Buscados")
        with engine.connect() as conn:
            query_ranking_buscas = text("""
                SELECT pergunta as "Assunto", COUNT(id) as "Volume"
                FROM historico_buscas_psy
                GROUP BY pergunta
                ORDER BY "Volume" DESC
                LIMIT 10
            """)
            df_ranking_buscas = pd.read_sql(query_ranking_buscas, conn)
        
        if not df_ranking_buscas.empty:
            st.dataframe(df_ranking_buscas, use_container_width=True, hide_index=True)
        else:
            st.write("Aguardando volume de buscas para gerar o ranking.")