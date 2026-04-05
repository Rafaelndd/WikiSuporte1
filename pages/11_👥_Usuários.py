"""
WikiSuporte — Painel de gestão de usuários (apenas perfil admin).
CRUD com soft delete (`ativo = false`). Sem exposição de `password_hash`.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from sqlalchemy import text

import cadastro_usuarios as cu
from app.services.penalidades_service import (
    processar_penalidades_contribuicao,
    resumo_para_dict,
)
from modules.database import get_connection
from services.perfil_usuario import eh_admin
from services.ui_realtime import render_global_notifications_listener
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.wiki_authenticator import process_forced_logout_from_url

st.set_page_config(page_title="WikiSuporte - Utilizadores", page_icon="👥", layout="wide")

if process_forced_logout_from_url():
    st.rerun()

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


def _ensure_scoring_schema() -> None:
    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS contribution_scoring_rules (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    pontos_evento_passado INTEGER NOT NULL DEFAULT 90,
                    multiplicador_diario_apos_qtd INTEGER NOT NULL DEFAULT 3,
                    multiplicador_diario_valor INTEGER NOT NULL DEFAULT 2,
                    bonus_semanal_meta_qtd INTEGER NOT NULL DEFAULT 15,
                    bonus_semanal_meta_pontos INTEGER NOT NULL DEFAULT 1000,
                    penalidade_sem_7_dias INTEGER NOT NULL DEFAULT 100,
                    minimo_semanal_sem_penalidade INTEGER NOT NULL DEFAULT 5,
                    penalidade_semana_insuficiente INTEGER NOT NULL DEFAULT 100,
                    janela_carencia_dias INTEGER NOT NULL DEFAULT 7,
                    max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100,
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO contribution_scoring_rules (id) VALUES (1) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.execute(text("ALTER TABLE contribution_scoring_rules ADD COLUMN IF NOT EXISTS janela_carencia_dias INTEGER NOT NULL DEFAULT 7"))
        conn.execute(text("ALTER TABLE contribution_scoring_rules ADD COLUMN IF NOT EXISTS max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100"))


def _carregar_scoring_rules() -> tuple[bool, str, dict[str, int]]:
    defaults = {
        "pontos_evento_passado": 90,
        "multiplicador_diario_apos_qtd": 3,
        "multiplicador_diario_valor": 2,
        "bonus_semanal_meta_qtd": 15,
        "bonus_semanal_meta_pontos": 1000,
        "penalidade_sem_7_dias": 100,
        "minimo_semanal_sem_penalidade": 5,
        "penalidade_semana_insuficiente": 100,
        "janela_carencia_dias": 7,
        "max_desconto_semanal_xp": 100,
    }
    try:
        _ensure_scoring_schema()
        engine = get_connection()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT pontos_evento_passado,
                           multiplicador_diario_apos_qtd,
                           multiplicador_diario_valor,
                           bonus_semanal_meta_qtd,
                           bonus_semanal_meta_pontos,
                           penalidade_sem_7_dias,
                           minimo_semanal_sem_penalidade,
                           penalidade_semana_insuficiente,
                           COALESCE(janela_carencia_dias, 7) AS janela_carencia_dias,
                           COALESCE(max_desconto_semanal_xp, 100) AS max_desconto_semanal_xp
                    FROM contribution_scoring_rules
                    WHERE id = 1
                    """
                )
            ).mappings().first()
        if not row:
            return True, "", defaults
        cfg = defaults.copy()
        for k in cfg:
            cfg[k] = int(row.get(k, cfg[k]))
        return True, "", cfg
    except Exception as ex:
        logging.exception("carregar contribution_scoring_rules")
        return False, str(ex), defaults


def _salvar_scoring_rules(cfg: dict[str, int]) -> tuple[bool, str]:
    try:
        _ensure_scoring_schema()
        payload = dict(cfg)
        payload["penalidade_sem_7_dias"] = min(max(0, int(payload["penalidade_sem_7_dias"])), 100)
        payload["penalidade_semana_insuficiente"] = min(max(0, int(payload["penalidade_semana_insuficiente"])), 100)
        payload["max_desconto_semanal_xp"] = min(max(0, int(payload["max_desconto_semanal_xp"])), 100)
        engine = get_connection()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE contribution_scoring_rules
                    SET pontos_evento_passado = :pontos_evento_passado,
                        multiplicador_diario_apos_qtd = :multiplicador_diario_apos_qtd,
                        multiplicador_diario_valor = :multiplicador_diario_valor,
                        bonus_semanal_meta_qtd = :bonus_semanal_meta_qtd,
                        bonus_semanal_meta_pontos = :bonus_semanal_meta_pontos,
                        penalidade_sem_7_dias = :penalidade_sem_7_dias,
                        minimo_semanal_sem_penalidade = :minimo_semanal_sem_penalidade,
                        penalidade_semana_insuficiente = :penalidade_semana_insuficiente,
                        janela_carencia_dias = :janela_carencia_dias,
                        max_desconto_semanal_xp = :max_desconto_semanal_xp,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """
                ),
                payload,
            )
        return True, "Parâmetros guardados com sucesso."
    except Exception as ex:
        logging.exception("salvar contribution_scoring_rules")
        return False, f"Erro ao guardar parâmetros: {ex}"

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
    st.markdown("### Parâmetros de XP e penalidades")
    ok_cfg, err_cfg, cfg = _carregar_scoring_rules()
    if not ok_cfg:
        st.error(
            "Não foi possível carregar os parâmetros de pontuação. "
            f"Detalhe: {err_cfg}"
        )
    else:
        with st.form("form_scoring_rules_admin"):
            c1, c2, c3 = st.columns(3)
            pontos_evento_passado = c1.number_input(
                "Evento passado (XP)",
                min_value=0,
                max_value=500,
                value=int(cfg["pontos_evento_passado"]),
                step=1,
            )
            multiplicador_diario_apos_qtd = c2.number_input(
                "Multiplicador diário após (qtd aprovações/dia)",
                min_value=0,
                max_value=50,
                value=int(cfg["multiplicador_diario_apos_qtd"]),
                step=1,
            )
            multiplicador_diario_valor = c3.number_input(
                "Multiplicador diário (valor)",
                min_value=1,
                max_value=10,
                value=int(cfg["multiplicador_diario_valor"]),
                step=1,
            )

            c4, c5, c6 = st.columns(3)
            bonus_semanal_meta_qtd = c4.number_input(
                "Meta semanal para bônus (aprovações)",
                min_value=0,
                max_value=100,
                value=int(cfg["bonus_semanal_meta_qtd"]),
                step=1,
            )
            bonus_semanal_meta_pontos = c5.number_input(
                "Bônus semanal (XP)",
                min_value=0,
                max_value=5000,
                value=int(cfg["bonus_semanal_meta_pontos"]),
                step=10,
            )
            minimo_semanal_sem_penalidade = c6.number_input(
                "Meta mínima semanal sem penalidade",
                min_value=0,
                max_value=100,
                value=int(cfg["minimo_semanal_sem_penalidade"]),
                step=1,
            )

            c7, c8, c9 = st.columns(3)
            penalidade_sem_7_dias = c7.number_input(
                "Penalidade sem 7 dias (XP)",
                min_value=0,
                max_value=100,
                value=int(min(cfg["penalidade_sem_7_dias"], 100)),
                step=1,
                help="Limitado a 100 por regra de segurança.",
            )
            penalidade_semana_insuficiente = c8.number_input(
                "Penalidade por semana insuficiente (XP)",
                min_value=0,
                max_value=100,
                value=int(min(cfg["penalidade_semana_insuficiente"], 100)),
                step=1,
                help="Limitado a 100 por regra de segurança.",
            )
            janela_carencia_dias = c9.number_input(
                "Janela de carência (dias)",
                min_value=0,
                max_value=30,
                value=int(cfg["janela_carencia_dias"]),
                step=1,
                help="Aplica para novo colaborador e retorno de férias/atendimento externo.",
            )

            max_desconto_semanal_xp = st.number_input(
                "Teto de desconto semanal (XP)",
                min_value=0,
                max_value=100,
                value=int(min(cfg["max_desconto_semanal_xp"], 100)),
                step=1,
                help="Mesmo com múltiplas regras, o desconto semanal não passa deste valor.",
            )

            salvar_cfg = st.form_submit_button("💾 Guardar parâmetros", type="primary")
            if salvar_cfg:
                payload = {
                    "pontos_evento_passado": int(pontos_evento_passado),
                    "multiplicador_diario_apos_qtd": int(multiplicador_diario_apos_qtd),
                    "multiplicador_diario_valor": int(multiplicador_diario_valor),
                    "bonus_semanal_meta_qtd": int(bonus_semanal_meta_qtd),
                    "bonus_semanal_meta_pontos": int(bonus_semanal_meta_pontos),
                    "penalidade_sem_7_dias": int(penalidade_sem_7_dias),
                    "minimo_semanal_sem_penalidade": int(minimo_semanal_sem_penalidade),
                    "penalidade_semana_insuficiente": int(penalidade_semana_insuficiente),
                    "janela_carencia_dias": int(janela_carencia_dias),
                    "max_desconto_semanal_xp": int(max_desconto_semanal_xp),
                }
                ok_save, msg_save = _salvar_scoring_rules(payload)
                if ok_save:
                    st.success(msg_save)
                    st.rerun()
                else:
                    st.error(msg_save)

    st.divider()
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
