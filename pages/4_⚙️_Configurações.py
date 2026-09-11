"""
WikiSuporte - Página de Configurações.
Cadastro de clientes com telefones e administração de comunicados globais.
Acesso restrito ao perfil **admin**. O robô de varredura roda em modo único
e automático (ciclo diário à meia-noite, via `motor_extracao.py`) e não é
mais controlado por esta tela — ver `oraculo_engine.log` para status. O
cadastro de clientes/telefones é usado para cruzar dados de suporte. Logs
de auditoria registram ações importantes.
"""
import re
import urllib.request
from datetime import datetime

import pandas as pd
import streamlit as st

from services.clientes_service import (
    buscar_clientes_autocomplete,
    garantir_indices_clientes_busca,
    listar_clientes_telefones_resumo,
    vincular_telefone_cliente,
)
from services.system_notifications import (
    bloqueios_versao_ativos,
    criar_notificacao,
    desativar_notificacao,
    ensure_schema as ensure_notifications_schema,
    listar_notificacoes_admin,
    normalizar_tipo_notificacao,
    registrar_bloqueio_versao,
    resolver_bloqueio_versao,
)
from services.perfil_usuario import eh_admin
from services.ui_realtime import render_global_notifications_listener
from services.ui_theme_presets import wiki_theme_apply_authenticated
from services.wiki_authenticator import process_forced_logout_from_url

try:
    from modules.auditoria import registrar_log_auditoria
except ImportError:
    def registrar_log_auditoria(*args): pass

st.set_page_config(page_title="WikiSuporte - Configurações", page_icon="⚙️", layout="wide")

if process_forced_logout_from_url():
    st.rerun()

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

usuario_id = st.session_state.get("usuario_id")
nome_usuario = str(st.session_state.get("usuario_nome", "Sistema"))
perfil_raw = st.session_state.get("perfil", "")
render_global_notifications_listener()
wiki_theme_apply_authenticated()
ensure_notifications_schema()

if not eh_admin(perfil_raw):
    st.error("⛔ Acesso Negado. Apenas usuários com perfil **admin**.")
    st.stop()

perfil_usuario = "admin"

st.title("⚙️ WikiSuporte - Configurações")
st.markdown("Clientes, telefones e comunicados globais do sistema.")

nomes_abas = [
    "🏢 Clientes e Telefones",
]
tem_painel_notifs = True
if tem_painel_notifs:
    nomes_abas.append("📣 Notificações e Comunicados")
abas = st.tabs(nomes_abas)
aba_clientes = abas[0]
aba_notificacoes = abas[1] if tem_painel_notifs else None

# ==========================================
# ABA 1: CLIENTES E TELEFONES
# ==========================================
def _apenas_numeros(txt):
    return re.sub(r"\D", "", str(txt)) if txt else ""

with aba_clientes:
    st.subheader("Cadastre e Vincule números de Telefone/Celular ao cadastro dos clientes cadastrados")

    ok_idx, msg_idx = garantir_indices_clientes_busca()
    if not ok_idx:
        st.warning(f"Não foi possível validar os índices de busca agora: {msg_idx}")

    if "cfg_cli_razao_social" not in st.session_state:
        st.session_state["cfg_cli_razao_social"] = ""
    if "cfg_cli_cnpj" not in st.session_state:
        st.session_state["cfg_cli_cnpj"] = ""
    if "cfg_cli_telefone" not in st.session_state:
        st.session_state["cfg_cli_telefone"] = ""
    if "cfg_cli_last_sel_razao" not in st.session_state:
        st.session_state["cfg_cli_last_sel_razao"] = ""
    if "cfg_cli_last_sel_cnpj" not in st.session_state:
        st.session_state["cfg_cli_last_sel_cnpj"] = ""

    def _aplicar_sugestao_cliente(label_escolhido: str, opcoes: dict[str, dict]) -> None:
        escolhido = opcoes.get(label_escolhido)
        if not escolhido:
            return
        st.session_state["cfg_cli_razao_social"] = str(escolhido.get("razao_social") or "")
        st.session_state["cfg_cli_cnpj"] = str(escolhido.get("cnpj") or "")
        st.rerun()

    st.markdown("#### Busca inteligente em tempo real")
    b1, b2 = st.columns(2)
    with b1:
        busca_razao = st.text_input(
            "Buscar por razão social/nome/CNPJ",
            key="cfg_cli_busca_razao",
            placeholder="Digite parte do nome, razão social ou CNPJ",
        )
        if (busca_razao or "").strip():
            df_sug_razao = buscar_clientes_autocomplete(busca_razao, limite=12)
            if not df_sug_razao.empty:
                opcoes_razao = {"": {}}
                for _, row in df_sug_razao.iterrows():
                    label = f"{row['razao_social']} | CNPJ: {row['cnpj'] or 'não informado'}"
                    opcoes_razao[label] = {
                        "razao_social": str(row["razao_social"] or ""),
                        "cnpj": str(row["cnpj"] or ""),
                    }
                escolha_razao = st.selectbox(
                    "Sugestões da busca por razão social",
                    list(opcoes_razao.keys()),
                    key="cfg_cli_sug_razao",
                )
                if escolha_razao and escolha_razao != st.session_state.get("cfg_cli_last_sel_razao", ""):
                    st.session_state["cfg_cli_last_sel_razao"] = escolha_razao
                    _aplicar_sugestao_cliente(escolha_razao, opcoes_razao)
                elif not escolha_razao:
                    st.session_state["cfg_cli_last_sel_razao"] = ""
            else:
                st.caption("Nenhuma correspondência encontrada para essa busca.")
    with b2:
        busca_cnpj = st.text_input(
            "Buscar por CNPJ (com ou sem máscara)",
            key="cfg_cli_busca_cnpj",
            placeholder="Ex.: 12.345.678/0001-90 ou 12345678000190",
        )
        if (busca_cnpj or "").strip():
            df_sug_cnpj = buscar_clientes_autocomplete(busca_cnpj, limite=12)
            if not df_sug_cnpj.empty:
                opcoes_cnpj = {"": {}}
                for _, row in df_sug_cnpj.iterrows():
                    label = f"{row['cnpj'] or 'não informado'} | {row['razao_social']}"
                    opcoes_cnpj[label] = {
                        "razao_social": str(row["razao_social"] or ""),
                        "cnpj": str(row["cnpj"] or ""),
                    }
                escolha_cnpj = st.selectbox(
                    "Sugestões da busca por CNPJ",
                    list(opcoes_cnpj.keys()),
                    key="cfg_cli_sug_cnpj",
                )
                if escolha_cnpj and escolha_cnpj != st.session_state.get("cfg_cli_last_sel_cnpj", ""):
                    st.session_state["cfg_cli_last_sel_cnpj"] = escolha_cnpj
                    _aplicar_sugestao_cliente(escolha_cnpj, opcoes_cnpj)
                elif not escolha_cnpj:
                    st.session_state["cfg_cli_last_sel_cnpj"] = ""
            else:
                st.caption("Nenhuma correspondência encontrada para esse CNPJ.")

    st.markdown("#### Vincular telefone")
    c1, c2, c3 = st.columns(3)
    with c1:
        razao = st.text_input(
            "Razão Social *",
            key="cfg_cli_razao_social",
            placeholder="Ex.: Posto Avenida LTDA",
        )
    with c2:
        cnpj_in = st.text_input(
            "CNPJ",
            key="cfg_cli_cnpj",
            placeholder="00.000.000/0000-00",
        )
    with c3:
        tel_in = st.text_input(
            "Telefone/Celular *",
            key="cfg_cli_telefone",
            placeholder="48999999999",
        )

    if st.button("Salvar e vincular", type="primary", key="cfg_cli_btn_salvar", use_container_width=True):
        razao_limpa = (razao or "").strip()
        cnpj_limpo = _apenas_numeros(cnpj_in)
        tel_limpo = _apenas_numeros(tel_in)
        if not razao_limpa or not tel_limpo:
            st.warning("Preencha Razão Social e Telefone/Celular.")
        else:
            ok, msg = vincular_telefone_cliente(
                razao_social=razao_limpa,
                numero_raw=tel_limpo,
                cnpj=cnpj_limpo or None,
            )
            if ok:
                st.success("Vínculo salvo com sucesso. Os dados já ficam disponíveis na página de Registro de Atendimentos.")
                st.session_state["cfg_cli_telefone"] = ""
                st.rerun()
            else:
                st.error(msg)

    try:
        df_cli = listar_clientes_telefones_resumo(limite=2000)
        if not df_cli.empty:
            df_cli = df_cli.rename(
                columns={
                    "razao_social": "Razão Social",
                    "cnpj": "CNPJ",
                    "qtd_telefones": "Qtd. Telefones",
                }
            )
            st.dataframe(df_cli, hide_index=True, use_container_width="stretch")
    except Exception as e:
        st.caption(f"Listagem indisponível: {e}")

if aba_notificacoes:
    with aba_notificacoes:
        st.subheader("📣 Painel do Suporte para Notificações")
        st.caption(
            "Dispare comunicados em tempo real para usuários ativos. "
            "Tipos: comunicado, aviso, erro crítico e bloqueio de versão."
        )

        with st.form("form_notificacao_admin"):
            c1, c2, c3 = st.columns(3)
            tipo = c1.selectbox(
                "Tipo *",
                [
                    "Comunicado",
                    "Aviso",
                    "Erro Crítico",
                    "Versão Bloqueada",
                ],
                help="Erro crítico e versão bloqueada aparecem com destaque no topo.",
            )
            target_role = c2.selectbox("Público-alvo", ["Todos", "Analistas", "Supervisores", "Coordenadores", "Desenvolvedores"])
            horas_expira = c3.number_input("Expira em (horas)", min_value=0, max_value=720, value=0, step=1)
            minutos_expira = st.number_input(
                "Expira em (minutos)",
                min_value=0,
                max_value=59,
                value=0,
                step=1,
                help="Use horas e minutos. Ex.: 1 hora e 30 minutos.",
            )
            tipo_bloqueio = tipo == "Versão Bloqueada"

            titulo = st.text_input("Título")
            mensagem = st.text_area("Mensagem *", height=120)

            modulo_nome = ""
            versao_prob = ""
            motivo_bloqueio = ""
            if tipo_bloqueio:
                cmod1, cmod2 = st.columns(2)
                modulo_nome = cmod1.text_input("Módulo com erro de versão (opcional)")
                versao_prob = cmod2.text_input("Versão problemática (opcional)")
                motivo_bloqueio = st.text_area(
                    "Motivo do bloqueio de versão (opcional)",
                    height=80,
                )

            salvar_notif = st.form_submit_button("🚀 Publicar notificação", type="primary", use_container_width=True)

            if salvar_notif:
                if not mensagem.strip():
                    st.error("Mensagem é obrigatória.")
                else:
                    tipo_norm = normalizar_tipo_notificacao(tipo)
                    if not tipo_norm:
                        st.error("Tipo de notificação inválido.")
                    else:
                        titulo_publicar = titulo
                        mensagem_publicar = mensagem
                        with st.status("Publicando comunicado...", expanded=False) as status:
                            exp = None
                            total_minutos_exp = (int(horas_expira or 0) * 60) + int(minutos_expira or 0)
                            if total_minutos_exp > 0:
                                exp = datetime.now() + pd.Timedelta(minutes=total_minutos_exp)
                            ok, msg = criar_notificacao(
                                tipo=tipo_norm,
                                mensagem=mensagem_publicar,
                                autor=nome_usuario,
                                titulo=titulo_publicar,
                                target_role=target_role,
                                data_expiracao=exp,
                                dedupe_seconds=120,
                            )
                            if ok and tipo_norm == "versao_bloqueada" and modulo_nome.strip() and versao_prob.strip():
                                okb, _ = registrar_bloqueio_versao(
                                    modulo_nome.strip(), versao_prob.strip(), motivo_bloqueio.strip()
                                )
                                if not okb:
                                    st.warning("Notificação publicada, mas falhou ao gravar em bloqueio_versoes.")
                            if ok:
                                status.update(label="Notificação publicada com sucesso.", state="complete")
                                st.toast("✅ Comunicado publicado em tempo real.", icon="✅")
                                st.success(msg)
                                st.rerun()
                            else:
                                status.update(label="Falha ao publicar.", state="error")
                                st.error(msg)

        st.markdown("### Notificações recentes")
        df_not = listar_notificacoes_admin(120)
        if df_not.empty:
            st.info("Nenhuma notificação cadastrada.")
        else:
            st.dataframe(df_not, hide_index=True, use_container_width=True)
            with st.form("form_desativar_notificacao"):
                ativo_series = df_not["ativo"].astype(str).str.lower().isin(["true", "t", "1"])
                ids = df_not[ativo_series]["id"].tolist()
                id_desativar = st.selectbox("Desativar notificação ativa", [""] + [str(i) for i in ids])
                btn_off = st.form_submit_button("Desativar", use_container_width=True)
                if btn_off and id_desativar:
                    okd, msgd = desativar_notificacao(int(id_desativar))
                    if okd:
                        st.cache_data.clear()
                        st.success(msgd)
                        st.rerun()
                    else:
                        st.error(msgd)

        st.markdown("### Bloqueios de versão ativos")
        df_blocks = bloqueios_versao_ativos()
        if df_blocks.empty:
            st.caption("Sem bloqueios ativos.")
        else:
            st.dataframe(df_blocks, hide_index=True, use_container_width=True)
            with st.form("form_resolver_bloqueio_versao"):
                id_resolver = st.selectbox(
                    "Marcar bloqueio como resolvido",
                    [""] + [str(i) for i in df_blocks["id"].astype(int).tolist()],
                )
                btn_resolver = st.form_submit_button("Resolver bloqueio", use_container_width=True)
                if btn_resolver and id_resolver:
                    okr, msgr = resolver_bloqueio_versao(int(id_resolver))
                    if okr:
                        st.cache_data.clear()
                        st.success(msgr)
                        st.rerun()
                    else:
                        st.error(msgr)
