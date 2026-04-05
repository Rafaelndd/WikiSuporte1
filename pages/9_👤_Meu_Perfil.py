"""
WikiSuporte — Meu perfil: foto e troca de senha (usuário autenticado).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import streamlit as st

import cadastro_usuarios as cu
from services.auth_guard import require_login

st.set_page_config(
    page_title="WikiSuporte — Meu perfil",
    page_icon="👤",
    layout="wide",
)

# ``require_login()`` já aplica notificações globais e tema (evita chave duplicada no rádio ``ws_streamlit_theme``).
require_login()

_ROOT = Path(__file__).resolve().parent.parent
_FOTOS_DIR = _ROOT / "uploads" / "fotos_perfil"

uid = int(st.session_state.get("usuario_id") or 0)
if uid <= 0:
    st.error("Sessão inválida. Volte a iniciar sessão.")
    st.stop()

try:
    ok_d, err_d, dados = cu.obter_dados_perfil_meu_perfil(uid)
except Exception as ex:
    logging.exception("obter_dados_perfil_meu_perfil")
    ok_d, err_d, dados = False, f"Erro inesperado: {ex}", None

if not ok_d or not dados:
    st.error(err_d or "Não foi possível carregar o seu perfil.")
    st.stop()

nome = str(dados.get("nome") or "")
username = str(dados.get("username") or "").strip() or "(não definido)"
ramal = str(dados.get("ramal") or "").strip() or "—"
rel_foto = str(dados.get("caminho_foto_perfil") or "").strip()
path_foto = (_ROOT / rel_foto.replace("/", os.sep)) if rel_foto else None

st.title("Meu Perfil")
st.caption(
    "Atualize sua foto e sua senha. Nome e login administrativos são alterados na gestão de usuários."
)

col_foto, col_info = st.columns([1, 2])

with col_foto:
    st.subheader("Foto")
    _mostrou_foto = False
    if path_foto is not None and path_foto.is_file():
        try:
            st.image(str(path_foto), width=220, caption="Foto atual")
            _mostrou_foto = True
        except Exception as ex:
            logging.warning("st.image falhou: %s", ex)
            st.warning("Não foi possível mostrar a imagem guardada.")
    if not _mostrou_foto:
        st.markdown(
            '<div style="width:220px;min-height:220px;border:2px dashed #94a3b8;'
            "display:flex;align-items:center;justify-content:center;border-radius:12px;"
            'background:#f1f5f9;color:#64748b;">'
            '<div style="text-align:center;"><div style="font-size:4rem;line-height:1;">👤</div>'
            "<div>Sem foto de perfil</div></div></div>",
            unsafe_allow_html=True,
        )

with col_info:
    st.subheader("Os meus dados")
    st.markdown(f"**Nome:** {nome}")
    st.markdown(f"**Username:** {username}")
    st.markdown(f"**Ramal:** {ramal}")

st.divider()
st.subheader("Alterar foto de perfil")
st.caption("Apenas PNG ou JPEG. Tamanho máximo 2,5 MB. O arquivo é salvo com nome padronizado.")

_FOTOS_DIR.mkdir(parents=True, exist_ok=True)

up = st.file_uploader(
    "Escolher imagem",
    type=["png", "jpg", "jpeg"],
    help="Formatos aceitos: .png, .jpg, .jpeg",
    key="upload_foto_perfil",
)

if up is not None:
    if st.button("Guardar nova foto", type="primary", key="btn_salvar_foto"):
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
st.subheader("Alterar senha")

with st.form("form_trocar_senha"):
    s_atual = st.text_input("Senha atual", type="password")
    s_nova = st.text_input("Nova senha", type="password")
    s_conf = st.text_input("Confirmar nova senha", type="password")
    sub = st.form_submit_button("Atualizar senha", type="primary")

    if sub:
        if not (s_atual or "").strip():
            st.error("Indique a senha atual.")
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
                st.info(
                    "Por segurança, se notar comportamento estranho no login, "
                    "termine a sessão (logout) e volte a entrar."
                )
            else:
                st.error(msg_s)
