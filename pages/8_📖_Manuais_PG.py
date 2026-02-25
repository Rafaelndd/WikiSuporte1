import streamlit as st
import pandas as pd
from modules.database import get_connection

st.set_page_config(page_title="Manuais PostoGestor", page_icon="📖", layout="wide")
if not st.session_state.get('autenticado'): st.switch_page("app.py")

@st.cache_data(ttl=3600)
def carregar_manuais():
    engine = get_connection()
    try: return pd.read_sql("SELECT * FROM manuais_tecnuv", engine)
    except: return pd.DataFrame()

st.title("📖 Repositório de Manuais (PostoGestor)")
st.markdown("Acesse as documentações e guias oficiais extraídos do HelpDesk.")

df_manuais = carregar_manuais()

if df_manuais.empty:
    st.warning("Nenhum manual encontrado. Aguarde a raspagem do Bot Logístico.")
else:
    for cat in df_manuais['categoria'].unique():
        st.subheader(cat)
        df_cat = df_manuais[df_manuais['categoria'] == cat]
        for _, row in df_cat.iterrows():
            st.markdown(f"- [{row['titulo']}]({row['link_acesso']})")