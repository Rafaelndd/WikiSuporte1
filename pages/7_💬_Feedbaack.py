import streamlit as st
import dotenv
dotenv.load_dotenv()  # Carrega as variáveis de ambiente do arquivo .env
import smtplib
from email.message import EmailMessage
from datetime import datetime
from services.ui_realtime import render_global_notifications_listener

# --- 1. CONFIGURAÇÃO INICIAL E SEGURANÇA ---
st.set_page_config(page_title="WikiSuporte - Feedback", page_icon="💬", layout="wide")
if not st.session_state.get("autenticado"):
    st.warning("⚠️ Acesso negado. Por favor, faça o login.")
    st.stop()
render_global_notifications_listener()

# --- 2. ESTILO DISCRETO (SEM GIFS / MASCOTES) ---
st.markdown(
    """
    <style>
        div[data-testid="stButton"] button {
            transition: all 0.2s ease-in-out;
            border-radius: 6px;
        }
        div[data-testid="stButton"] button:hover {
            transform: translateY(-1px);
            box-shadow: 0px 3px 8px rgba(0, 0, 0, 0.15);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Canal de Feedback")
st.markdown(
    "Use este espaço para registrar **experiências com o sistema**, "
    "**críticas**, **relatos de bug**, **sugestões de melhoria** ou **elogios**. "
    "Todas as mensagens são encaminhadas diretamente ao responsável técnico."
)
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Preencha **Assunto** e **Descrição** (obrigatórios). Escolha o **tipo** (sugestão, bug, etc.). "
        "O e-mail de retorno é opcional mas ajuda a responder. O envio usa **SMTP** configurado em `secrets.toml` (email). "
        "Após enviar, aguarde confirmação na tela."
    )

import streamlit as st
import dotenv
dotenv.load_dotenv()  # Carrega as variáveis de ambiente do arquivo .env
import smtplib
from email.message import EmailMessage
from datetime import datetime
from services.ui_realtime import render_global_notifications_listener

# --- 1. CONFIGURAÇÃO INICIAL E SEGURANÇA ---
st.set_page_config(page_title="WikiSuporte - Feedback", page_icon="💬", layout="wide")
if not st.session_state.get("autenticado"):
    st.warning("⚠️ Acesso negado. Por favor, faça o login.")
    st.stop()
render_global_notifications_listener()

# --- 2. ESTILO DISCRETO (SEM GIFS / MASCOTES) ---
st.markdown(
    """
    <style>
        div[data-testid="stButton"] button {
            transition: all 0.2s ease-in-out;
            border-radius: 6px;
        }
        div[data-testid="stButton"] button:hover {
            transform: translateY(-1px);
            box-shadow: 0px 3px 8px rgba(0, 0, 0, 0.15);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Canal de Feedback")
st.markdown(
    "Use este espaço para registrar **experiências com o sistema**, "
    "**críticas**, **relatos de bug**, **sugestões de melhoria** ou **elogios**. "
    "Todas as mensagens são encaminhadas diretamente ao responsável técnico."
)
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Preencha **Assunto** e **Descrição** (obrigatórios). Escolha o **tipo** (sugestão, bug, etc.). "
        "O e-mail de retorno é opcional mas ajuda a responder. O envio usa **SMTP** configurado em `secrets.toml` (email). "
        "Após enviar, aguarde confirmação na tela."
    )

# --- 3. FORMULÁRIO PROFISSIONAL DE FEEDBACK ---
with st.container(border=True):
    st.subheader("Registrar novo feedback")

    with st.form(key="form_feedback", clear_on_submit=True):
        tipo_feedback = st.selectbox(
            "Tipo de feedback",
            options=["Sugestão", "Elogio", "Crítica / Problema", "Relato de Bug"],
            index=0,
        )

        assunto = st.text_input(
            "Assunto",
            placeholder="Resumo curto do tema (ex.: 'Lentidão ao abrir tela de chamados')",
        )

        email_contato = st.text_input(
            "E-mail para retorno",
            placeholder="Seu e-mail para resposta (opcional, mas recomendado)",
        )

        mensagem = st.text_area(
            "Descrição detalhada",
            height=180,
            placeholder=(
                "Descreva o contexto, o que você esperava que acontecesse, o que aconteceu de fato, "
                "passos para reproduzir (no caso de bug) e qualquer informação adicional relevante."
            ),
        )

        enviado = st.form_submit_button("Enviar feedback", use_container_width='strech')

## --- 4. PROCESSAMENTO DO FORMULÁRIO ---
        if enviado:
            if not mensagem.strip() or not assunto.strip():
                st.warning("Por favor, preencha pelo menos **Assunto** e **Descrição detalhada**.")
            else:
                import os
                
                # DIAGNÓSTICO 1: Validar se as variáveis estão sendo lidas
                smtp_server = os.getenv("EMAIL_SUPORTE_HOST")
                
                if not smtp_server:
                    st.error("🚨 ERRO CRÍTICO: O arquivo .env não foi carregado corretamente. O host está vazio.")
                    st.stop() # Para a execução aqui mesmo

                smtp_port = int(os.getenv("EMAIL_SUPORTE_PORT", 465))
                email_conta = os.getenv("EMAIL_SUPORTE_USER")
                senha_smtp = os.getenv("EMAIL_SUPORTE_PASS")
                nome_remetente = os.getenv("EMAIL_SUPORTE_NAME", "Suporte Epsy")

                try:
                    # [ ... Todo o bloco de montagem do corpo do email se mantém igual ... ]
                    msg = EmailMessage()
                    msg["Subject"] = f"WikiSuporte - Novo Feedback ({tipo_feedback})"
                    msg["From"] = f"{nome_remetente} <{email_conta}>"
                    msg["To"] = email_conta
                    
                    email_contato_str = str(email_contato).strip() if email_contato else ""
                    if email_contato_str:
                        msg["Reply-To"] = email_contato_str
                    else:
                        msg["Reply-To"] = email_conta

                    msg.set_content(mensagem) # Simplificado para o teste

                    # DIAGNÓSTICO 2: Adição do timeout=10 para evitar congelamento
                    with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
                        server.login(email_conta, senha_smtp)
                        server.send_message(msg)

                    st.success("✅ SUCESSO! O e-mail foi disparado e aceito pelo servidor.")

                except TimeoutError:
                    st.error("⏱️ ERRO: O servidor mail.epsy.com.br demorou muito para responder (Timeout na porta 465). Isso geralmente indica um bloqueio de rede ou firewall.")
                except smtplib.SMTPAuthenticationError as auth_err:
                    st.error(f"🔐 ERRO DE LOGIN: Usuário ou senha rejeitados pelo servidor. Detalhe: {auth_err}")
                except Exception as e:
                    # DIAGNÓSTICO 3: Expondo o erro real na interface
                    st.error(f"🛑 ERRO DESCONHECIDO: {type(e).__name__} - {str(e)}")