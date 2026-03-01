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
st.markdown("Compartilhe o seu conhecimento, suba no ranking da equipa e acesse a Inteligência Artificial!")

# Define as abas dependendo do perfil
if perfil_logado in ['coordenação', 'superadmin', 'administrador', 'desenvolvedor']:
    aba_ranking, aba_nova, aba_minhas, aba_fila, aba_gemini = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "⚖️ Fila de Aprovação", "🤖 Busca Gemini (IA)"
    ])
else:
    aba_ranking, aba_nova, aba_minhas, aba_gemini = st.tabs([
        "🏅 Ranking e Troféus", "📝 Nova Dica", "📚 Minhas Contribuições", "🤖 Busca Gemini (IA)"
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
            # Adiciona os Troféus baseados na posição
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
    st.image("mascote/psy_sorriso.png", width=100)
    st.markdown("### Compartilhe seu Conhecimento com a Equipe!")
    
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
                        # Se for coordenador/admin, aprova direto. Se for analista, vai para PENDENTE.
                        status_inicial = "APROVADO" if perfil_logado in ['coordenação', 'superadmin'] else "PENDENTE"
                        
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
                        st.success("✅ Contribuição enviada! Ela está na fila para avaliação da Coordenação. Ganhará seus XP assim que aprovada!")
                    else:
                        st.success("✅ Contribuição salva e aprovada automaticamente (Privilégio de Coordenação)!")
                        
                    registrar_log_auditoria(usuario_logado_id, "NOVA_CONTRIBUICAO", f"Submeteu: {titulo[:30]}...")
                    import time; time.sleep(2); st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro no banco de dados: {e}")

# ==========================================
# ABA 3: MINHAS CONTRIBUIÇÕES (Edição e Exclusão Segura)
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
                
                # Se foi rejeitada, mostra o motivo e permite excluir ou ajustar
                if row['status'] == 'REJEITADO':
                    st.error(f"**Motivo da Rejeição:** {row['motivo_rejeicao']}")
                    st.warning("Você deve recriar a dica na Aba 'Nova Contribuição' com os ajustes solicitados e, em seguida, excluir este registro rejeitado abaixo.")
                    
                    if st.button(f"🗑️ Excluir Contribuição Rejeitada (ID {row['id']})", key=f"del_{row['id']}"):
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
                        st.caption("🔒 Registros aprovados não podem ser alterados/excluídos por Analistas. Solicite à coordenação em caso de inconsistência.")
    else:
        st.info("Você ainda não possui contribuições.")

# ==========================================
# ABA 4: FILA DE APROVAÇÃO (SÓ COORDENAÇÃO)
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
                        if st.button("✅ Aprovar e Publicar na IA", key=f"apr_{row['id']}", type="primary"):
                            with engine.begin() as conn_apr:
                                conn_apr.execute(text("UPDATE base_conhecimento SET status = 'APROVADO' WHERE id = :id"), {"id": row['id']})
                            registrar_log_auditoria(usuario_logado_id, "APROVOU_DICA", f"ID: {row['id']}")
                            st.success("Aprovado!"); import time; time.sleep(1); st.rerun()
                    with c2:
                        motivo = st.text_input("Motivo da Rejeição (Ajuste esperado):", key=f"motivo_{row['id']}")
                        if st.button("❌ Rejeitar e Devolver", key=f"rej_{row['id']}"):
                            if not motivo:
                                st.warning("Informe o motivo da rejeição para o analista poder corrigir.")
                            else:
                                with engine.begin() as conn_rej:
                                    conn_rej.execute(text("UPDATE base_conhecimento SET status = 'REJEITADO', motivo_rejeicao = :m WHERE id = :id"), {"m": motivo, "id": row['id']})
                                registrar_log_auditoria(usuario_logado_id, "REJEITOU_DICA", f"ID: {row['id']}")
                                st.success("Devolvido ao autor!"); import time; time.sleep(1); st.rerun()
        else:
            st.success("🎉 Fila limpa! Não há contribuições pendentes de avaliação.")

# ==========================================
# ABA 5: MOTOR DE BUSCA GEMINI (Interface)
# ==========================================
with aba_gemini:
    st.subheader("🤖 PSY Assistente Virtual WikiSuporte")
    st.markdown("O seu assistente inteligente treinado com **Manuais, Wikis e Contribuições da Equipe**.")
    
    pergunta = st.text_input("Faça uma pergunta sobre o PostoGestor:", placeholder="Ex: Como instalar o PostgreSQL 17?")
    
    if st.button("🔍 Perguntar ao PSY"):
        if pergunta:
            with st.spinner("Consultando as centenas de Manuais e Wikis na nossa Base de Dados..."):
                # TODO: Na próxima etapa, conectaremos o backend do LangChain/GoogleGenAI aqui!
                st.info("A interface está pronta! Na nossa próxima sessão de engenharia, vamos ligar as engrenagens da API Key do Gemini aqui dentro.")
                st.success("**Resposta Simulada:** Para configurar o TEF Sitef, você deve aceder ao Menu X, conforme descrito no 'Manual 435' e na 'Wiki 12'.")
        else:
            st.warning("Digite uma pergunta primeiro.")