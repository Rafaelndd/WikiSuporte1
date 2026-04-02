import streamlit as st

from services.auth_guard import require_login
from services.feedback_mailer import resolve_smtp_config, send_feedback_email
from services.feedback_storage import PASTA_FEEDBACKS, save_feedback_to_disk

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

st.title("Canal de Feedback")
st.markdown(
    "Use este espaço para registrar **experiências com o sistema**, **críticas**, "
    "**relatos de bug**, **sugestões de melhoria** ou **elogios**. "
    f"Cada envio é **gravado na pasta `{PASTA_FEEDBACKS}/`** do projeto (data, tipo e assunto no nome da subpasta). "
    "Se o e-mail estiver configurado, uma cópia também é enviada por SMTP."
)

with st.expander("Como usar esta página?"):
    st.markdown(
        "- Preencha **Assunto** e **Descrição** (obrigatórios) e escolha o **tipo**.\n"
        "- O **e-mail para retorno** é opcional.\n"
        f"- **Arquivos**: em `{PASTA_FEEDBACKS}/` será criada uma pasta por envio, com `feedback.json` e `feedback.txt`.\n"
        "- **E-mail (opcional)**: configure `EMAIL_SUPORTE_*` no `.env` ou `[email]` no `secrets.toml`. "
        "Use `FEEDBACK_TO_EMAIL` se o destino for diferente da conta SMTP.\n"
        "- **SSL**: `pip install -U certifi`; se necessário, `EMAIL_SMTP_SSL_INSECURE=1` no `.env`.\n"
        f"- A pasta `{PASTA_FEEDBACKS}/` está no `.gitignore` para não versionar dados de usuários."
    )
    st.code(
        "# .streamlit/secrets.toml (exemplo — e-mail opcional)\n"
        "[email]\n"
        'smtp_server = "smtp.gmail.com"\n'
        "smtp_port = 465\n"
        'smtp_user = "sua.conta@gmail.com"\n'
        'smtp_password = "senha-de-app"\n'
        'from_name = "WikiSuporte"\n'
        'feedback_to = "caixa.que.recebe@gmail.com"\n',
        language="toml",
    )

cfg_preview = resolve_smtp_config()
if cfg_preview:
    st.caption("Envio por e-mail **ativado** (além do registro em disco).")
else:
    st.info(
        f"Envio por e-mail **não configurado** — o feedback será apenas salvo em **`{PASTA_FEEDBACKS}/`**."
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
            placeholder="Resumo curto do tema (ex.: lentidão ao abrir tela de chamados)",
        )

        email_contato = st.text_input(
            "E-mail para retorno",
            placeholder="Opcional — para você receber resposta direta",
        )

        mensagem = st.text_area(
            "Descrição detalhada",
            height=180,
            placeholder=(
                "Contexto, o que você esperava, o que ocorreu, passos para reproduzir (bugs) e qualquer detalhe útil."
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

                ok_disk, msg_disk, pasta = save_feedback_to_disk(
                    tipo_feedback=tipo_feedback,
                    assunto=(assunto or "").strip(),
                    mensagem=(mensagem or "").strip(),
                    email_retorno=(email_contato or "").strip(),
                    usuario_nome=nome_usuario,
                    usuario_id=uid_int,
                )

                if not ok_disk:
                    st.error(msg_disk)
                else:
                    st.success(msg_disk)

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
                        if mail_ok:
                            st.caption(f"E-mail: {mail_detail}")
                        else:
                            st.warning(
                                "O feedback foi salvo em disco, mas o e-mail não foi enviado: "
                                f"{mail_detail}"
                            )
