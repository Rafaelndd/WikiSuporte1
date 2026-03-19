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

# --- 4. PROCESSAMENTO DO FORMULÁRIO ---
        if enviado:
            if not mensagem.strip() or not assunto.strip():
                st.warning("Por favor, preencha pelo menos **Assunto** e **Descrição detalhada**.")
            else:
                import os # Importar no topo do seu arquivo principal
                
                id_usuario = st.session_state.get("usuario_id", "ID_DESCONHECIDO")
                nome_usuario = st.session_state.get("usuario_nome", "NOME_DESCONHECIDO")
                data_atual = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                # Resgate seguro de variáveis de ambiente
                smtp_server = os.getenv("EMAIL_SUPORTE_HOST")
                smtp_port = int(os.getenv("EMAIL_SUPORTE_PORT", 465))
                email_conta = os.getenv("EMAIL_SUPORTE_USER")
                senha_smtp = os.getenv("EMAIL_SUPORTE_PASS")
                nome_remetente = os.getenv("EMAIL_SUPORTE_NAME", "Suporte Epsy")

                # Validação de segurança básica antes de tentar a conexão
                if not senha_smtp or not smtp_server:
                    st.error("Erro interno: Credenciais de envio não configuradas no ambiente.")
                    st.stop()

                try:
                    msg = EmailMessage()
                    msg["Subject"] = f"WikiSuporte - Novo Feedback ({tipo_feedback})"
                    
                    # Formatação profissional: Exibe o nome amigável e oculta o e-mail bruto na interface do usuário
                    msg["From"] = f"{nome_remetente} <{email_conta}>"
                    msg["To"] = email_conta # O sistema envia para a própria caixa de suporte
                    
                    # Fluxo operacional otimizado: Permite responder direto ao usuário
                    if email_contato.strip():
                        msg["Reply-To"] = email_contato
                    else:
                        msg["Reply-To"] = email_conta

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
Observação: Se o usuário informou um e-mail, basta clicar em 'Responder' no seu cliente de e-mail para contatá-lo.
"""
                    msg.set_content(corpo_email)

                    # CONEXÃO ATUALIZADA: Uso obrigatório de SMTP_SSL para a porta 465
                    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                        server.login(email_conta, senha_smtp)
                        server.send_message(msg)

                    st.success(
                        "Seu feedback foi registrado e encaminhado para nossa equipe. "
                        "Agradecemos sua contribuição para a melhoria do sistema!"
                    )

                except smtplib.SMTPAuthenticationError:
                    st.error("Falha na autenticação. Verifique o usuário e senha configurados no servidor.")
                    print("[ERRO SMTP] Falha de autenticação - Senha ou Usuário incorretos.")
                except Exception as e:
                    st.error("Não foi possível processar o envio no momento. Tente novamente mais tarde.")
                    print(f"[ERRO SMTP] Falha geral no envio de feedback: {e}")