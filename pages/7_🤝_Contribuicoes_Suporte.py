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

# Define as abas dependendo do perfil
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
    aba_ranking, aba_nova, aba_minhas, aba_fila, aba_gemini = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "⚖️ Fila de Aprovação", "🤖 Busca PSY (Híbrido)"
    ])
else:
    aba_ranking, aba_nova, aba_minhas, aba_gemini = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "🤖 Busca PSY (Híbrido)"
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
                    st.warning("Você deve recriar a dica na Aba 'Nova Contribuição' com os ajustes solicitados e, em seguida, excluir este registo.")
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
# ABA 4: FILA DE APROVAÇÃO (SÓ COORDENAÇÃO/ADMIN)
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
# ABA 5: MOTOR DE BUSCA HÍBRIDO (IA + SQL)
# ==========================================
with aba_gemini:
    st.subheader("🤖 Motor de Busca PSY (Híbrido)")
    st.markdown("Busque informações nos **Manuais, Wikis e Dicas da Equipe**.")
    
    pergunta = st.text_input("Digite sua pesquisa:", placeholder="Ex: Como configurar a balança Toledo?")
    
    if st.button("🔍 Buscar", type="primary"):
        if not pergunta.strip():
            st.warning("Por favor, digite uma pergunta.")
        else:
            with st.spinner("Acionando as engrenagens de busca..."):
                import os
                
                # ==========================================
                # FASE 1: O MOTOR A COMBUSTÃO (SQL Direto)
                # Sempre roda para extrair o contexto real da base
                # ==========================================
                palavras = [p for p in pergunta.replace("?", "").replace(",", "").split() if len(p) > 3]
                contextos_db = []
                resultados_puros = []
                
                if palavras:
                    with engine.connect() as conn:
                        filtros_sql = " OR ".join([f"titulo ILIKE :p{i} OR conteudo ILIKE :p{i}" for i in range(len(palavras))])
                        params = {f"p{i}": f"%{palavras[i]}%" for i in range(len(palavras))}
                        
                        query_rag = text(f"""
                            SELECT titulo, origem, conteudo 
                            FROM base_conhecimento 
                            WHERE status = 'APROVADO' AND ({filtros_sql})
                            LIMIT 5
                        """)
                        resultados = conn.execute(query_rag, params).fetchall()
                        for r in resultados:
                            contextos_db.append(f"📚 FONTE: {r[0]} ({r[1]})\nCONTEÚDO: {r[2]}")
                            resultados_puros.append({"titulo": r[0], "origem": r[1], "conteudo": r[2]})
                
                texto_contexto = "\n\n---\n\n".join(contextos_db)
                
                # ==========================================
                # FASE 2: VERIFICAÇÃO DE ACESSO AO MOTOR ELÉTRICO (IA)
                # ==========================================
                acesso_ia_liberado = perfil_logado in ['administrador', 'superadmin']
                
                if acesso_ia_liberado:
                    try:
                        import google.generativeai as genai
                        from dotenv import load_dotenv
                        from google.api_core.exceptions import ResourceExhausted
                        
                        load_dotenv()
                        gemini_api_key = os.getenv("GEMINI_API_KEY")
                        
                        if not gemini_api_key:
                            raise ValueError("API Key não encontrada no .env.")

                        genai.configure(api_key=gemini_api_key)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        if texto_contexto:
                            prompt = f"""Você é o PSY, Especialista do PostoGestor.
                            Responda com base EXCLUSIVAMENTE nestes documentos.
                            PERGUNTA: "{pergunta}"
                            CONTEXTO OFICIAL:
                            {texto_contexto}
                            """
                        else:
                            prompt = f"Como assistente técnico, dê uma sugestão breve sobre: {pergunta}. Avise que não há manuais oficiais na base sobre isto."

                        # O Salto de Fé: Invoca o Gemini
                        resposta_ia = model.generate_content(prompt)
                        
                        # Extrai a contagem exata de tokens
                        try:
                            t_prompt = resposta_ia.usage_metadata.prompt_token_count
                            t_resp = resposta_ia.usage_metadata.candidates_token_count
                            t_total = resposta_ia.usage_metadata.total_token_count
                        except:
                            t_prompt = t_resp = t_total = 0
                            
                        # Exibe a resposta IA com sucesso
                        st.success("⚡ Motor Elétrico (IA) utilizado com sucesso!")
                        st.markdown(resposta_ia.text)
                        
                        # A Cereja do Bolo: O painel de consumo exigido!
                        st.caption(f"🔋 **Medidor de Carga (Tokens):** Gastou **{t_prompt}** p/ ler + **{t_resp}** p/ responder = **Total {t_total} Tokens** nesta consulta.")
                        
                        # Grava o histórico oficial no BD
                        with engine.begin() as conn_log:
                            conn_log.execute(text("""
                                INSERT INTO historico_buscas_psy (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens)
                                VALUES (:u, :p, :r, :tp, :tr, :tt)
                            """), {"u": usuario_logado_id, "p": pergunta, "r": resposta_ia.text, "tp": t_prompt, "tr": t_resp, "tt": t_total})
                            
                    except ResourceExhausted:
                        # O CARRO HÍBRIDO EM AÇÃO: Bateu no limite da API? Fica frio e liga o motor a combustão!
                        st.warning("⚠️ **Aviso Administrativo:** O Motor Elétrico (IA Gemini) atingiu a sua cota gratuita e está recarregando a bateria. O sistema ligou automaticamente o **Motor a Combustão** (SQL) para não parar a sua operação!")
                        
                        if resultados_puros:
                            st.info("👇 Aqui estão os documentos brutos resgatados da Base de Conhecimento:")
                            for doc in resultados_puros:
                                with st.expander(f"📄 {doc['titulo']} ({doc['origem']})"):
                                    st.write(doc['conteudo'])
                        else:
                            st.write("Nenhum documento encontrado na base.")
                            
                    except Exception as e:
                        st.error(f"❌ Erro na ignição da IA: {e}")
                        
                else:
                    # ==========================================
                    # FASE 3: ACESSO DE ANALISTAS (SÓ COMBUSTÃO POR ENQUANTO)
                    # ==========================================
                    st.info("🔧 Motor a Combustão Ativado: A IA (PSY) está restrita aos Administradores no momento. Os documentos originais foram extraídos com sucesso abaixo:")
                    if resultados_puros:
                        for doc in resultados_puros:
                            with st.expander(f"📄 {doc['titulo']} ({doc['origem']})"):
                                st.write(doc['conteudo'])
                    else:
                        st.warning("Nenhum documento encontrado na base para esta pesquisa.")