import streamlit as st
import smtplib
from email.message import EmailMessage
from datetime import datetime
import os

# --- 1. CONFIGURAÇÃO INICIAL E SEGURANÇA ---
if not st.session_state.get("autenticado") or not st.session_state.get("termos_aceitos"):
    st.warning("⚠️ Acesso negado. Por favor, faça o login e aceite os termos da LGPD.")
    st.stop()

# --- 2. INJEÇÃO DE CSS (EFEITOS MODERNOS E INTERATIVOS) ---
# Aqui criamos as animações de "hover" (passar o mouse) para botões e containers
st.markdown("""
<style>
    /* Efeito suave ao passar o mouse nos botões */
    div[data-testid="stButton"] button {
        transition: all 0.3s ease-in-out;
        border-radius: 8px;
    }
    div[data-testid="stButton"] button:hover {
        transform: translateY(-2px); /* Levanta o botão levemente */
        box-shadow: 0px 6px 12px rgba(0, 123, 255, 0.3); /* Cria uma sombra azulada (Light Mode) */
        border-color: #007BFF;
    }
    
    /* Efeito de destaque no container do formulário */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        transition: all 0.3s ease-in-out;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.1); /* Sombra suave para destacar o card */
        border-color: #007BFF;
    }
</style>
""", unsafe_allow_html=True)

st.title("💬 Feedback do WikiSuporte")

# --- 3. INTERFACE INTERATIVA COM O MASCOTE Psy (GIFs) ---
tipo_feedback = st.selectbox(
    "Sobre o que você quer falar?",
    options=["💡 Sugestão", "✅ Elogio", "❌ Crítica / Problema", "🐞 Relato de Bug"],
    index=0
)

col_img, col_texto = st.columns([1, 4], vertical_alignment="center")

with col_texto:
    # Lógica Interativa: A fala e o GIF do Psy mudam conforme a escolha!
    if "Sugestão" in tipo_feedback:
        fala_psy = "Olá! Eu sou o Psy. Adoro novas ideias! O que você sugere para deixarmos o sistema ainda melhor? 💡"
        caminho_psy = "mascote/psy_sorriso.png" # Exemplo: Psy com uma lâmpada ou pensando
    elif "Elogio" in tipo_feedback:
        fala_psy = "Eba! Fico muito feliz em saber que estamos ajudando! Conta mais? 🤩"
        caminho_psy = "assets/psy_recebendo_feedbaack.gif" # Exemplo: Psy pulando ou sorrindo
    elif "Bug" in tipo_feedback:
        fala_psy = "Opa, Vamos investigar 🕵️‍♂️ Por favor, me dê o máximo de detalhes para o nosso Desenvolvedor corrigir."
        caminho_psy = "assets/psy_digitado.gif" # Exemplo: Psy com uma lupa
    else:
        fala_psy = "Estou aqui para ouvir. Prometo que nossa equipe vai analisar sua situação com muito cuidado! 💙"
        caminho_psy = "assets/psy_manutencao.gif" # Exemplo: Psy acenando ou prestando atenção
        
    st.info(f"**Psy diz:** {fala_psy}")

with col_img:
    # Renderizando o GIF animado do Psy
    if os.path.exists(caminho_psy):
        st.image(caminho_psy, use_container_width='stretch')
    else:
        # Fallback caso o GIF ainda não exista na pasta
        st.markdown("<h1 style='text-align: center;'>🐾</h1>", unsafe_allow_html=True)
        st.caption(f"*(GIF {caminho_psy} não encontrado)*")

st.divider()

# --- 4. ÁREA DE DIGITAÇÃO E ENVIO ---
with st.container(border=True):
    with st.form(key="form_feedback", clear_on_submit=True):
        mensagem = st.text_area(
            "Descreva sua experiência em detalhes:",
            height=150,
            placeholder="Escreva sua mensagem aqui para o Psy..."
        )
        
        enviado = st.form_submit_button("🚀 Enviar Feedback", use_container_width='stretch')
        
        # --- 5. PROCESSAMENTO DO FORMULÁRIO ---
        if enviado:
            if not mensagem.strip():
                st.warning("⚠️ Por favor, escreva uma mensagem antes de enviar.")
            else:
                id_usuario = st.session_state.get("usuario_id", "ID_DESCONHECIDO")
                data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                
                try:
                    # Buscando credenciais
                    smtp_server = st.secrets["email"]["smtp_server"]
                    smtp_port = st.secrets["email"]["smtp_port"]
                    email_remetente = st.secrets["email"]["remetente"]
                    senha_remetente = st.secrets["email"]["senha"]
                    email_destinatario = st.secrets["email"]["destinatario"]
                    
                    msg = EmailMessage()
                    msg['Subject'] = f"WikiSuporte - Novo Feedback ({tipo_feedback})"
                    msg['From'] = email_remetente
                    msg['To'] = email_destinatario
                    
                    corpo_email = f"""
                    Novo feedback recebido através do sistema WikiSuporte.
                    
                    📋 DADOS DO USUÁRIO
                    -------------------
                    ID do Usuário: {id_usuario}
                    Data/Hora de Envio: {data_atual}
                    
                    💬 MENSAGEM
                    -------------------
                    Tipo: {tipo_feedback}
                    
                    Conteúdo:
                    {mensagem}
                    """
                    
                    msg.set_content(corpo_email)
                    
                    with smtplib.SMTP(smtp_server, smtp_port) as server:
                        server.starttls() 
                        server.login(email_remetente, senha_remetente)
                        server.send_message(msg)
                        
                    st.success("✅ O Psy entregou o seu feedback para a equipe de desenvolvimento. Muito obrigado!")
                    
                except Exception as e:
                    st.error(f"Erro ao processar o envio do e-mail: {e}")