import streamlit as st
st.set_page_config(page_title="Contribuições EPSY", page_icon="🤝", layout="wide")
if not st.session_state.get('autenticado'): st.switch_page("app.py")

st.title("🤝 Hub de Contribuições (Suporte EPSY)")
st.info("Página de colaboração inicializada. Utilize esta área para documentar dicas diárias não cobertas pela Tecnuv.")
# (Pode colar aqui o formulário de inserção na tabela contribuicoes_suporte)