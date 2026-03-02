import streamlit as st
import pandas as pd
from modules.database import get_connection

# ==========================================
# 1. CONFIGURAÇÃO E AUTENTICAÇÃO
# ==========================================
st.set_page_config(page_title="Wikis Helpdesk", page_icon="📚", layout="wide")

if not st.session_state.get('autenticado'): 
    st.switch_page("app.py")

# ==========================================
# 2. CARREGAMENTO DE DADOS (CACHED)
# ==========================================
@st.cache_data(ttl=3600)
def carregar_wikis():
    engine = get_connection()
    try: 
        # Lendo exatamente a tabela e a origem corretas, ordenado pela data de criação
        query = "SELECT * FROM base_conhecimento WHERE origem = 'WIKI_HELPDESK' ORDER BY criado_em DESC"
        df = pd.read_sql(query, engine)
        return df, None
    except Exception as e: 
        return pd.DataFrame(), str(e)

# ==========================================
# 3. CABEÇALHO E CARDS VISUAIS (UX)
# ==========================================
st.title("📚 Base de Conhecimento (Wikis)")
st.markdown("Consulte procedimentos, manuais e resoluções de erros do Helpdesk para agilizar os seus atendimentos.")

df_wikis, erro_bd = carregar_wikis()

# --- CARDS DE INFORMAÇÃO ---
st.markdown("<br>", unsafe_allow_html=True)
c_card1, c_card2, c_card3 = st.columns(3)

with c_card1:
    with st.container(border=True):
        st.markdown("#### 📂 Acervo Total")
        total_docs = len(df_wikis) if not df_wikis.empty else 0
        st.metric("Documentos Disponíveis", total_docs)

with c_card2:
    with st.container(border=True):
        st.markdown("#### 🔄 Status da Base")
        if erro_bd:
            st.error("Falha na Sincronização")
        elif total_docs == 0:
            st.warning("Base Vazia")
        else:
            st.success("Sincronizado e Ativo")
        st.caption("Última checagem: Agora")

with c_card3:
    with st.container(border=True):
        st.markdown("#### 💡 Dica de Busca")
        st.write("A nossa pesquisa varre o título, categorias e também todo o conteúdo do documento.")

st.divider()

# ==========================================
# 4. ÁREA DE PESQUISA (Sempre visível)
# ==========================================
with st.container(border=True):
    termo_busca = st.text_input("🔍 O que você está procurando hoje?", placeholder="Digite um título, categoria ou palavra-chave do conteúdo...")

# ==========================================
# 5. TRATAMENTO DE ERROS E EXIBIÇÃO
# ==========================================

if erro_bd:
    st.error(f"❌ Ocorreu um erro técnico ao buscar as Wikis no banco de dados. \n\n**Detalhe do Erro (SQL):** `{erro_bd}`")

if df_wikis.empty:
    st.info("O acervo de Wikis do Helpdesk está vazio ou os registros não possuem a origem 'WIKI_HELPDESK'.")
    st.stop()

df = df_wikis.copy()

if termo_busca:
    # Máscara mapeada EXATAMENTE com as colunas do seu banco
    mascara = (
        df['titulo'].astype(str).str.contains(termo_busca, case=False, na=False) |
        df['categoria'].astype(str).str.contains(termo_busca, case=False, na=False) |
        df['subcategoria'].astype(str).str.contains(termo_busca, case=False, na=False) |
        df['conteudo'].astype(str).str.contains(termo_busca, case=False, na=False)
    )
    df = df[mascara]

st.markdown("<br>", unsafe_allow_html=True)

if df.empty:
    st.warning(f"Nenhum documento encontrado para a busca: **'{termo_busca}'**. Tente usar outras palavras-chave.")
else:
    st.subheader(f"📖 Resultados Encontrados ({len(df)})")
    
    for _, row in df.iterrows():
        # Captura os dados com base no SCHEMA REAL que você mandou
        titulo = row.get('titulo', 'Sem Título')
        nr_documento = row.get('nr_documento', 'N/A')
        categoria = row.get('categoria', 'Geral')
        subcategoria = row.get('subcategoria', 'Não especificada')
        conteudo = row.get('conteudo', 'Nenhum conteúdo descrito.')
        status = row.get('status', 'Sem status')
        
        # Lógica inteligente para pegar a data mais recente (Atualização ou Criação)
        data_exibicao = ""
        if pd.notna(row.get('atualizado_em')):
            try: data_exibicao = pd.to_datetime(row['atualizado_em']).strftime("%d/%m/%Y às %H:%M")
            except: pass
        elif pd.notna(row.get('criado_em')):
            try: data_exibicao = pd.to_datetime(row['criado_em']).strftime("%d/%m/%Y às %H:%M")
            except: pass
        
        # Renderização do Expander e do Documento
        with st.expander(f"📑 {titulo} | Doc: #{nr_documento}"):
            # Cabeçalho do documento
            col_info1, col_info2 = st.columns([3, 1])
            with col_info1:
                st.markdown(f"**📂 Categoria:** `{categoria}` ➔ `{subcategoria}`")
            with col_info2:
                st.markdown(f"**Status:** `{status}`")
            
            if data_exibicao:
                st.caption(f"🕒 *Última modificação: {data_exibicao}*")
                
            st.divider()
            
            # Corpo do documento
            st.markdown("#### 📖 Conteúdo / Procedimento")
            st.markdown(conteudo)
            
            # Se houver um anexo, mostra o caminho (ou link futuramente)
            if pd.notna(row.get('caminho_anexo')) and str(row.get('caminho_anexo')).strip():
                st.info(f"📎 **Anexo disponível em:** {row['caminho_anexo']}")