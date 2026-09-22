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
perfil_normalizado = require_login()

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
username = str(dados.get("username") or "").strip()
ramal = str(dados.get("ramal") or "").strip() or "—"
rel_foto = str(dados.get("caminho_foto_perfil") or "").strip()
path_foto = (_ROOT / rel_foto.replace("/", os.sep)) if rel_foto else None
tem_foto_ficheiro = path_foto is not None and path_foto.is_file()

_AVATAR_PX = 132

# Tema é fixo em escuro (ver services/ui_theme_presets.py) — paleta única, sem fallback claro.
st.markdown(
    """
    <style>
    .ws-perfil-card {
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    .ws-perfil-card img,
    .ws-perfil-card div[role="img"] {
        margin: 0 !important;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
        border-radius: 50% !important;
        flex-shrink: 0;
    }
    .ws-perfil-nome {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        font-size: clamp(1.4rem, 3vw, 1.9rem);
        font-weight: 800;
        color: #f8fafc;
        margin: 0 0 0.4rem 0;
        line-height: 1.2;
        letter-spacing: -0.02em;
    }
    .ws-perfil-username {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        color: #94a3b8;
        font-size: 0.95rem;
        margin: 0.5rem 0 0 0;
    }
    .ws-perfil-section-title {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
        font-size: clamp(1.15rem, 2.6vw, 1.4rem);
        font-weight: 800;
        margin: 0 0 0.35rem 0;
        color: #f1f5f9;
        letter-spacing: -0.02em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

nome_safe = html_module.escape(nome or "Usuário")
username_safe = html_module.escape(username)
ramal_safe = html_module.escape(ramal)

with st.container(border=True):
    col_avatar, col_info = st.columns([1, 4], vertical_alignment="center")
    with col_avatar:
        st.markdown(
            '<div class="ws-perfil-card">'
            + html_avatar_perfil_circular(
                str(path_foto) if tem_foto_ficheiro else None,
                tamanho_px=_AVATAR_PX,
            )
            + "</div>",
            unsafe_allow_html=True,
        )
    with col_info:
        st.markdown(f'<p class="ws-perfil-nome">{nome_safe}</p>', unsafe_allow_html=True)
        badge_cargo = (
            ":violet-badge[:material/shield_person: Administrador]"
            if perfil_normalizado == "admin"
            else ":blue-badge[:material/support_agent: Analista]"
        )
        st.markdown(f"{badge_cargo} :gray-badge[:material/call: Ramal {ramal_safe}]")
        if username_safe:
            st.markdown(f'<p class="ws-perfil-username">@{username_safe}</p>', unsafe_allow_html=True)

# ——— Foto de perfil ———
with st.container(border=True):
    st.markdown('<p class="ws-perfil-section-title">🖼️ Foto de perfil</p>', unsafe_allow_html=True)
    st.caption("PNG ou JPEG · até 2,5 MB.")

    _FOTOS_DIR.mkdir(parents=True, exist_ok=True)

    up = st.file_uploader(
        "Nova imagem",
        type=["png", "jpg", "jpeg"],
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

# ——— Senha ———
with st.container(border=True):
    st.markdown('<p class="ws-perfil-section-title">🔒 Segurança da conta</p>', unsafe_allow_html=True)
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
