"""
WikiSuporte — Gestão de utilizadores (admin).
A interface completa será evoluída nas fases seguintes; por ora apenas gate de segurança.
"""

import streamlit as st

from services.perfil_usuario import eh_admin
from services.ui_realtime import render_global_notifications_listener
from services.ui_theme_presets import wiki_theme_apply_authenticated

st.set_page_config(page_title="WikiSuporte - Utilizadores", page_icon="👥", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

render_global_notifications_listener()
wiki_theme_apply_authenticated()

perfil_raw = st.session_state.get("perfil", "")
if not eh_admin(perfil_raw):
    st.error("⛔ Acesso Negado. Apenas utilizadores com perfil **admin**.")
    st.stop()

st.title("Gestão de Usuários")
