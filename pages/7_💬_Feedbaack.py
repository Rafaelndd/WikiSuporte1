import logging

import streamlit as st

from services.auth_guard import require_login
from services.feedback_mailer import resolve_smtp_config, send_feedback_email
from services.feedback_storage import save_feedback_to_disk

st.set_page_config(page_title="WikiSuporte - Feedback", page_icon="💬", layout="wide")

require_login()

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

st.title("Canal de feedback")
st.markdown(
    "Conte como foi sua **experiência** com o WikiSuporte: **sugestões**, **elogios**, "
    "**críticas** ou **relatos de problema**. Quanto mais detalhes você der, mais fácil fica entender e agir."
)

with st.expander("Como preencher"):
    st.markdown(
        "- **Assunto** e **Descrição** são obrigatórios.\n"
        "- Escolha o **tipo** que melhor descreve sua mensagem.\n"
        "- **E-mail para retorno** é opcional — use se quiser facilitar um contato futuro."
    )

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
            placeholder="Resumo curto (ex.: lentidão ao abrir a tela de chamados)",
        )

        email_contato = st.text_input(
            "E-mail para retorno",
            placeholder="Opcional",
        )

        mensagem = st.text_area(
            "Descrição detalhada",
            height=180,
            placeholder=(
                "Contexto, o que você esperava, o que aconteceu e, se for bug, os passos para reproduzir."
            ),
        )

        enviado = st.form_submit_button("Enviar feedback", type="primary", use_container_width=True)

        if enviado:
            if not (mensagem or "").strip() or not (assunto or "").strip():
                st.warning("Preencha **Assunto** e **Descrição detalhada**.")
            else:
                nome_usuario = str(st.session_state.get("usuario_nome") or "")
                uid = st.session_state.get("usuario_id")
                uid_int = int(uid) if uid is not None else None

                ok_disk, _msg_disk, _pasta = save_feedback_to_disk(
                    tipo_feedback=tipo_feedback,
                    assunto=(assunto or "").strip(),
                    mensagem=(mensagem or "").strip(),
                    email_retorno=(email_contato or "").strip(),
                    usuario_nome=nome_usuario,
                    usuario_id=uid_int,
                )

                if not ok_disk:
                    st.error(
                        "Não foi possível registrar seu feedback neste momento. "
                        "Tente de novo em alguns instantes ou fale com o suporte."
                    )
                else:
                    st.success("Obrigado! Seu feedback foi registrado.")

                    cfg = resolve_smtp_config()
                    if cfg:
                        mail_ok, mail_detail = send_feedback_email(
                            cfg,
                            tipo_feedback=tipo_feedback,
                            assunto=(assunto or "").strip(),
                            mensagem=(mensagem or "").strip(),
                            reply_to=(email_contato or "").strip() or None,
                            usuario_nome=nome_usuario or None,
                            usuario_id=uid_int,
                        )
                        if not mail_ok:
                            logging.warning("Feedback: e-mail não enviado: %s", mail_detail)
