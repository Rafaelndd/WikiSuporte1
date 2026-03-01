import streamlit as st
import pandas as pd
from modules.database import get_connection

st.set_page_config(page_title="Wikis HelpDesk", page_icon="📚", layout="wide")
if not st.session_state.get('autenticado'): st.switch_page("app.py")

@st.cache_data(ttl=3600)
def carregar_wikis():
    engine = get_connection()
    try: return pd.read_sql("SELECT * FROM wikis_tecnuv ORDER BY data_criacao DESC", engine)
    except: return pd.DataFrame()

st.title("📚 Wikis Helpdesk")
df_wikis = carregar_wikis()

if df_wikis.empty:
    st.warning("Wikis não encontradas.")
    st.stop()

with st.expander("🔍 Pesquisa", expanded=True):
    termo_busca = st.text_input("Buscar por Título ou Erro:")

df = df_wikis.copy()
if termo_busca:
    df = df[df['titulo'].str.contains(termo_busca, case=False, na=False) | df['tipo_erro'].str.contains(termo_busca, case=False, na=False)]

st.subheader(f"📖 Wikis ({len(df)})")
for _, row in df.iterrows():
    with st.expander(f"📑 {row['titulo']} | Versão: {row['versao']}"):
        st.markdown(f"**🔴 Erro:** {row['tipo_erro']}")
        st.markdown("**🟢 Procedimento:**")
        st.write(row['procedimento'])