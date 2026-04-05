"""
WikiSuporte — Meu perfil: foto e troca de senha (usuário autenticado).
"""

from __future__ import annotations

import html as html_module
import logging
import os
from pathlib import Path

import streamlit as st

import cadastro_usuarios as cu
from services.auth_guard import require_login
from services.ui_avatar import html_avatar_perfil_circular

st.set_page_config(
    page_title="WikiSuporte — Meu perfil",
    page_icon="👤",
    layout="wide",
)

# ``require_login()`` já aplica notificações globais e tema.
require_login()

_ROOT = Path(__file__).resolve().parent.parent
_FOTOS_DIR = _ROOT / "uploads" / "fotos_perfil"
MAX_BYTES_FOTO_PERFIL = cu._MAX_BYTES_FOTO_PERFIL

uid = int(st.session_state.get("usuario_id") or 0)
if uid <= 0:
    st.error("Sessão inválida. Faça login novamente.")
    st.stop()

try:
    ok_d, err_d, dados = cu.obter_dados_perfil_meu_perfil(uid)
except Exception as ex:
    logging.exception("obter_dados_perfil_meu_perfil")
    ok_d, err_d, dados = False, f"Erro inesperado: {ex}", None

if not ok_d or not dados:
    st.error(err_d or "Não foi possível carregar seu perfil.")
    st.stop()

nome = str(dados.get("nome") or "")
ramal = str(dados.get("ramal") or "").strip() or "—"
rel_foto = str(dados.get("caminho_foto_perfil") or "").strip()
path_foto = (_ROOT / rel_foto.replace("/", os.sep)) if rel_foto else None
tem_foto_ficheiro = path_foto is not None and path_foto.is_file()

_AVATAR_PX = 268

st.markdown(
    """
    <style>
    .ws-perfil-hero-avatar {
        display: flex;
        justify-content: flex-start;
        align-items: flex-start;
        padding: 0 0 0.35rem 0;
    }
    .ws-perfil-hero-avatar img,
    .ws-perfil-hero-avatar div[role="img"] {
        margin: 0 !important;
        box-shadow: 0 14px 36px rgba(15, 23, 42, 0.14);
        border-radius: 50% !important;
    }
    html[data-theme="dark"] .ws-perfil-hero-avatar img,
    html[data-theme="dark"] .ws-perfil-hero-avatar div[role="img"] {
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.4);
    }
    .ws-perfil-welcome-wrap {
        text-align: center;
        margin: 0.85rem auto 0.5rem;
        max-width: 48rem;
        padding: 0 1rem;
    }
    .ws-perfil-dados-wrap {
        max-width: 36rem;
        margin: 0.35rem 0 0 0;
        margin-right: auto;
        padding: 0;
        text-align: left;
    }
    .ws-perfil-welcome-italic {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        color: #475569;
        font-size: clamp(1.05rem, 2.2vw, 1.28rem);
        font-weight: 500;
        font-style: italic;
        line-height: 1.55;
        margin: 0 auto;
        max-width: 40rem;
    }
    html[data-theme="dark"] .ws-perfil-welcome-italic { color: #94a3b8; }
    .ws-perfil-dado-linha {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        font-size: clamp(1.15rem, 2.6vw, 1.45rem);
        font-weight: 700;
        color: #0f172a;
        margin: 0 0 0.65rem 0;
        line-height: 1.3;
    }
    html[data-theme="dark"] .ws-perfil-dado-linha { color: #f1f5f9; }
    .ws-perfil-dado-linha .ws-perfil-rotulo {
        color: #64748b;
        font-weight: 700;
        margin-right: 0.35rem;
    }
    html[data-theme="dark"] .ws-perfil-dado-linha .ws-perfil-rotulo { color: #94a3b8; }
    .ws-perfil-dado-linha .ws-perfil-valor {
        font-weight: 800;
        color: #0f172a;
    }
    html[data-theme="dark"] .ws-perfil-dado-linha .ws-perfil-valor { color: #f8fafc; }
    .ws-perfil-section-title {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        font-size: clamp(1.25rem, 3vw, 1.6rem);
        font-weight: 800;
        margin: 0 0 0.35rem 0;
        color: #0f172a;
        letter-spacing: -0.02em;
    }
    html[data-theme="dark"] .ws-perfil-section-title { color: #f1f5f9; }
    </style>
    """,
    unsafe_allow_html=True,
)

_msg_boas_vindas = (
    "Este é o seu espaço: adicione ou altere sua foto de perfil e sua senha. "
    "Em breve teremos novas funcionalidades."
)
nome_safe = html_module.escape(nome)
ramal_safe = html_module.escape(ramal)
msg_safe = html_module.escape(_msg_boas_vindas)

st.markdown(
    '<div class="ws-perfil-hero-avatar">'
    + html_avatar_perfil_circular(
        str(path_foto) if tem_foto_ficheiro else None,
        tamanho_px=_AVATAR_PX,
    )
    + "</div>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="ws-perfil-welcome-wrap">'
    f'<p class="ws-perfil-welcome-italic">{msg_safe}</p></div>',
    unsafe_allow_html=True,
)

st.divider()

st.markdown(
    f'<div class="ws-perfil-dados-wrap">'
    f'<p class="ws-perfil-dado-linha">'
    f'<span class="ws-perfil-rotulo">Usuário:</span>'
    f'<span class="ws-perfil-valor">{nome_safe}</span></p>'
    f'<p class="ws-perfil-dado-linha">'
    f'<span class="ws-perfil-rotulo">Meu Ramal:</span>'
    f'<span class="ws-perfil-valor">{ramal_safe}</span></p>'
    f"</div>",
    unsafe_allow_html=True,
)

st.divider()

# ——— Foto de perfil ———
with st.container(border=True):
    st.markdown('<p class="ws-perfil-section-title">Foto de perfil</p>', unsafe_allow_html=True)
    st.caption("PNG ou JPEG · até 2,5 MB.")

    _FOTOS_DIR.mkdir(parents=True, exist_ok=True)

    up = st.file_uploader(
        "Nova imagem",
        type=["png", "jpg", "jpeg"],
        max_bytes=MAX_BYTES_FOTO_PERFIL,
        help="Formatos: .png, .jpg, .jpeg",
        key="upload_foto_perfil",
    )
    st.caption("Arraste um arquivo ou clique para escolher.")

    ac1, ac2, ac3 = st.columns([1, 1, 2])
    with ac1:
        guardar = st.button("Salvar foto", type="primary", use_container_width=True, key="btn_salvar_foto")
    with ac2:
        remover = st.button(
            "Remover foto",
            use_container_width=True,
            key="btn_remover_foto",
            disabled=not (rel_foto and tem_foto_ficheiro),
            help="Remove a foto atual e limpa o registro no banco de dados.",
        )

    if remover:
        try:
            ok_rm, msg_rm = cu.atualizar_caminho_foto_perfil_usuario(uid, "")
        except Exception as ex:
            logging.exception("remover foto perfil")
            ok_rm, msg_rm = False, f"Erro: {ex}"
        if ok_rm:
            if path_foto and path_foto.is_file():
                try:
                    path_foto.unlink()
                except OSError:
                    logging.warning("Não foi possível apagar o arquivo: %s", path_foto)
            st.success("Foto de perfil removida com sucesso.")
            st.rerun()
        else:
            st.error(msg_rm)

    if guardar:
        if up is None:
            st.warning("Escolha primeiro uma imagem para salvar.")
        else:
            try:
                raw = up.getvalue()
            except Exception as ex:
                logging.exception("getvalue upload")
                st.error(f"Falha ao ler o arquivo: {ex}")
            else:
                ok_img, ext_or_err = cu.validar_bytes_imagem_perfil(raw)
                if not ok_img:
                    st.error(ext_or_err)
                else:
                    ext = ext_or_err
                    slug = cu.slug_para_nome_arquivo_perfil(
                        str(dados.get("username") or "") or str(dados.get("nome") or ""),
                        uid,
                    )
                    filename = f"foto_perfil_{slug}{ext}"
                    rel_novo = f"uploads/fotos_perfil/{filename}"
                    dest = _ROOT / rel_novo.replace("/", os.sep)
                    antigo = rel_foto.replace("/", os.sep) if rel_foto else ""
                    path_antigo = (_ROOT / antigo) if antigo else None
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(raw)
                        ok_db, msg_db = cu.atualizar_caminho_foto_perfil_usuario(uid, rel_novo)
                    except OSError as ex:
                        logging.exception("gravar foto perfil")
                        ok_db, msg_db = False, f"Erro ao salvar o arquivo: {ex}"
                    if ok_db:
                        if (
                            path_antigo
                            and path_antigo.is_file()
                            and path_antigo.resolve() != dest.resolve()
                        ):
                            try:
                                path_antigo.unlink()
                            except OSError:
                                logging.warning("Não foi possível remover foto antiga: %s", path_antigo)
                        st.success("Foto de perfil atualizada.")
                        st.rerun()
                    else:
                        try:
                            if dest.is_file():
                                dest.unlink()
                        except OSError:
                            pass
                        st.error(msg_db)

st.divider()

# ——— Senha ———
with st.container(border=True):
    st.markdown('<p class="ws-perfil-section-title">Segurança da conta</p>', unsafe_allow_html=True)
    st.caption("Escolha uma senha forte. Se algo parecer estranho após a troca, saia e entre de novo.")

    with st.form("form_trocar_senha", clear_on_submit=False):
        s_atual = st.text_input("Senha atual", type="password", autocomplete="current-password")
        s_nova = st.text_input("Nova senha", type="password", autocomplete="new-password")
        s_conf = st.text_input("Confirmar nova senha", type="password", autocomplete="new-password")
        sub = st.form_submit_button("Atualizar senha", type="primary", use_container_width=True)

        if sub:
            if not (s_atual or "").strip():
                st.error("Informe a senha atual.")
            elif not (s_nova or "").strip() or not (s_conf or "").strip():
                st.error("Preencha a nova senha e a confirmação.")
            else:
                try:
                    ok_s, msg_s = cu.trocar_senha_meu_perfil(
                        uid,
                        s_atual,
                        s_nova.strip(),
                        s_conf.strip(),
                    )
                except Exception as ex:
                    logging.exception("trocar_senha_meu_perfil")
                    ok_s, msg_s = False, f"Erro inesperado: {ex}"
                if ok_s:
                    try:
                        from services.wiki_authenticator import load_credentials_for_stauth

                        load_credentials_for_stauth.clear()
                    except Exception as ex:
                        logging.warning("clear credentials cache: %s", ex)
                    st.success(msg_s)
                    st.info("Se algo não atualizar na hora, use **Sair** e entre de novo.", icon="🔒")
                else:
                    st.error(msg_s)
