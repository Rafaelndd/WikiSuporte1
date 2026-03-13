import streamlit as st
import smtplib
from email.message import EmailMessage
from datetime import datetime

# --- 1. CONFIGURAÇÃO INICIAL E SEGURANÇA ---
st.set_page_config(page_title="WikiSuporte - Feedback", page_icon="💬", layout="wide")
if not st.session_state.get("autenticado"):
    st.warning("⚠️ Acesso negado. Por favor, faça o login.")
    st.stop()

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

        # --- 4. PROCESSAMENTO DO FORMULÁRIO ---
        if enviado:
            if not mensagem.strip() or not assunto.strip():
                st.warning("Por favor, preencha pelo menos **Assunto** e **Descrição detalhada**.")
            else:
                id_usuario = st.session_state.get("usuario_id", "ID_DESCONHECIDO")
                nome_usuario = st.session_state.get("usuario_nome", "NOME_DESCONHECIDO")
                data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                try:
                    # Buscando credenciais de e-mail já configuradas em st.secrets
                    smtp_server = st.secrets["email"]["smtp_server"]
                    smtp_port = st.secrets["email"]["smtp_port"]
                    email_remetente = st.secrets["email"]["remetente"]
                    senha_remetente = st.secrets["email"]["senha"]
                    email_destinatario = st.secrets["email"]["destinatario"]

                    msg = EmailMessage()
                    msg["Subject"] = f"WikiSuporte - Novo Feedback ({tipo_feedback})"
                    msg["From"] = email_remetente
                    msg["To"] = email_destinatario

                    corpo_email = f"""
Novo feedback recebido através do sistema WikiSuporte.

=== DADOS DO USUÁRIO ===
ID do Usuário.....: {id_usuario}
Nome do Usuário...: {nome_usuario}
Data/Hora de Envio: {data_atual}
E-mail para retorno: {email_contato or 'não informado'}

=== CLASSIFICAÇÃO ===
Tipo..............: {tipo_feedback}
Assunto...........: {assunto}

=== DESCRIÇÃO ===
{mensagem}

-------------------------
Observação: responda para o e-mail informado acima para notificar o usuário.
"""

                    msg.set_content(corpo_email)

                    with smtplib.SMTP(smtp_server, smtp_port) as server:
                        server.starttls()
                        server.login(email_remetente, senha_remetente)
                        server.send_message(msg)

                    st.success(
                        "Seu feedback foi registrado e encaminhado para análise. "
                        "Caso tenha informado um e-mail de contato, você poderá receber um retorno por esse canal."
                    )

                except Exception as e:
                    st.error(f"Erro ao processar o envio do e-mail de feedback: {e}")