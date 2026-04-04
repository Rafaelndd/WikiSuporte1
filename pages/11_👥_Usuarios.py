"""
WikiSuporte — Painel de gestão de usuários (apenas perfil admin).
CRUD com soft delete (`ativo = false`). Sem exposição de `password_hash`.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

import cadastro_usuarios as cu
from app.services.penalidades_service import (
    processar_penalidades_contribuicao,
    resumo_para_dict,
)
from modules.database import get_connection
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
    st.error("⛔ Acesso negado. Apenas usuários com perfil **admin**.")
    st.stop()

meu_id = int(st.session_state.get("usuario_id") or 0)

st.title("Gestão de usuários")
st.caption(
    "Consulta e alteração de usuários na base PostgreSQL. "
    "A exclusão lógica apenas desativa o acesso (`ativo = false`), preservando histórico."
)

try:
    ok_lista, err_lista, df_users = cu.listar_usuarios_admin()
except Exception as ex:
    logging.exception("listar_usuarios_admin")
    ok_lista = False
    err_lista = f"Erro inesperado ao listar usuários: {ex}"
    df_users = None

if not ok_lista or df_users is None:
    st.error(err_lista or "Não foi possível carregar a lista de usuários.")
    st.info("Verifique a ligação ao PostgreSQL e se a migração da tabela `usuarios` está aplicada.")
    st.stop()

if df_users.empty:
    st.warning("Não existem usuários na tabela `usuarios`.")
else:
    exibir = df_users.copy()
    exibir.columns = [
        "ID",
        "Nome",
        "Username",
        "Perfil",
        "Ramal",
        "Ativo",
        "Em férias",
        "Atend. externo",
    ]
    st.subheader("Usuários cadastrados")
    st.dataframe(exibir, use_container_width=True, hide_index=True)

tab_novo, tab_editar, tab_fechamento = st.tabs(
    ["➕ Novo utilizador", "✏️ Editar / inativar", "📅 Fechamento Semanal"]
)

with tab_novo:
    st.markdown("#### Cadastrar novo usuário")
    with st.form("form_novo_usuario", clear_on_submit=True):
        fn_nome = st.text_input("Nome (exibição)", placeholder="Ex.: Maria Silva")
        fn_user = st.text_input("Username (login)", placeholder="Ex.: maria.silva")
        fn_ramal = st.text_input("Ramal", placeholder="Opcional")
        fn_perfil = st.selectbox("Perfil", ["analista", "admin"], index=0)
        fn_senha = st.text_input("Senha inicial", type="password")
        fn_ativo = st.toggle("Usuário ativo", value=True)
        fn_ferias = st.toggle("Em férias", value=False)
        fn_ext = st.toggle("Em atendimento externo", value=False)
        sub_novo = st.form_submit_button("Salvar novo usuário", type="primary")

        if sub_novo:
            if not (fn_nome or "").strip() or not (fn_user or "").strip():
                st.error("Nome e username são obrigatórios.")
            elif not (fn_senha or "").strip():
                st.error("Defina uma senha inicial forte para o novo usuário.")
            else:
                try:
                    ok, msg = cu.criar_usuario(
                        (fn_user or "").strip(),
                        fn_senha.strip(),
                        fn_perfil,
                        nome_exibicao=(fn_nome or "").strip(),
                        ramal=(fn_ramal or "").strip(),
                        ativo=fn_ativo,
                        em_ferias=fn_ferias,
                        em_atendimento_externo=fn_ext,
                    )
                except Exception as ex:
                    logging.exception("criar_usuario painel")
                    ok, msg = False, f"Erro inesperado: {ex}"
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with tab_editar:
    if df_users.empty:
        st.info("Não há usuários para editar.")
    else:
        st.markdown("#### Alterar dados do usuário")

        def _label_uid(uid: int) -> str:
            r = df_users.loc[df_users["id"] == uid].iloc[0]
            return f"{int(r['id'])} — {r['nome']}"

        uids = [int(x) for x in df_users["id"].tolist()]
        sel_id = st.selectbox("Usuário", uids, format_func=_label_uid, key="sel_edit_uid")
        row = df_users.loc[df_users["id"] == sel_id].iloc[0]

        with st.form("form_editar_usuario"):
            fe_nome = st.text_input("Nome", value=str(row["nome"] or ""))
            fe_user = st.text_input("Username", value=str(row["username"] or ""))
            fe_ramal = st.text_input("Ramal", value=str(row["ramal"] or ""))
            perfis = ["analista", "admin"]
            p = str(row.get("perfil", "analista") or "analista").lower()
            idx_p = perfis.index(p) if p in perfis else 0
            fe_perfil = st.selectbox("Perfil", perfis, index=idx_p)
            fe_senha = st.text_input(
                "Nova senha (deixe vazio para não alterar)",
                type="password",
                help="Só preencha para forçar reposição da senha (política de senha forte).",
            )
            fe_ativo = st.toggle(
                "Usuário ativo",
                value=bool(row["ativo"]) if pd.notna(row["ativo"]) else True,
            )
            fe_ferias = st.toggle(
                "Em férias",
                value=bool(row["em_ferias"]) if pd.notna(row["em_ferias"]) else False,
            )
            fe_ext = st.toggle(
                "Em atendimento externo",
                value=bool(row["em_atendimento_externo"])
                if pd.notna(row["em_atendimento_externo"])
                else False,
            )
            sub_ed = st.form_submit_button("Guardar alterações", type="primary")

            if sub_ed:
                pwd = fe_senha.strip() if (fe_senha or "").strip() else None
                try:
                    ok, msg = cu.atualizar_usuario_painel(
                        usuario_id=int(sel_id),
                        nome=fe_nome,
                        username=fe_user,
                        ramal=fe_ramal,
                        perfil=fe_perfil,
                        ativo=fe_ativo,
                        em_ferias=fe_ferias,
                        em_atendimento_externo=fe_ext,
                        nova_senha=pwd,
                    )
                except Exception as ex:
                    logging.exception("atualizar_usuario_painel")
                    ok, msg = False, f"Erro inesperado: {ex}"
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        st.markdown("#### Inativar usuário (exclusão lógica)")
        st.caption("O registo permanece na base (histórico, XP, auditoria). Apenas o acesso é bloqueado.")

        sel_inat = st.selectbox(
            "Usuário a inativar",
            uids,
            format_func=_label_uid,
            key="sel_inat_uid",
        )
        confirma = st.checkbox(
            "Confirmo que pretendo inativar este usuário",
            key="chk_inat",
        )
        if st.button("Inativar acesso", type="primary", key="btn_inat"):
            if not confirma:
                st.warning("Marque a confirmação para continuar.")
            elif int(sel_inat) == meu_id:
                st.error("Não pode inativar a sua própria sessão.")
            else:
                try:
                    ok, msg = cu.inativar_usuario_por_id(int(sel_inat))
                except Exception as ex:
                    logging.exception("inativar_usuario_por_id")
                    ok, msg = False, f"Erro inesperado: {ex}"
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with tab_fechamento:
    st.markdown("### Rotinas do sistema")
    st.info(
        "Esta rotina avalia as contribuições da semana e aplica as regras de XP. "
        "O processo é seguro e **não duplicará descontos** se for executada mais de uma vez "
        "(chaves idempotentes por utilizador e semana)."
    )
    st.caption(
        "Apenas utilizadores **analistas** ativos entram na avaliação. Quem está em **férias** ou "
        "**atendimento externo** é ignorado."
    )

    if st.button("Rodar Fechamento de Penalidades", type="primary", key="btn_penalidades"):
        try:
            engine = get_connection()
            with st.spinner("Processando penalidades..."):
                with engine.begin() as conn:
                    res = resumo_para_dict(processar_penalidades_contribuicao(conn))
            st.success(
                "Fechamento concluído.\n\n"
                f"- **Analistas avaliados (não isentos):** {res['processados']}\n"
                f"- **Isentos (férias / externo):** {res['isentos']}\n"
                f"- **Novas penalidades gravadas:** {res['penalizados']}\n"
                f"- **Já existiam nesta semana (sem novo desconto):** {res['penalidades_ja_existiam']}\n"
                f"- **Sem penalidade aplicável (motor):** {res['sem_penalidade_motor']}\n"
                f"- **Total na lista (analistas ativos):** {res['usuarios_listados']}"
            )
        except Exception as ex:
            logging.exception("processar_penalidades_contribuicao painel admin")
            st.error(
                "Não foi possível concluir o fechamento. Verifique a ligação ao PostgreSQL e se as "
                "migrações de `contribution_scoring_rules`, `user_xp_events` e colunas de "
                "`base_conhecimento` estão aplicadas.\n\n"
                f"Detalhe: {ex}"
            )
