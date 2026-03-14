from __future__ import annotations

import io
import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import text

from modules.database import get_connection
from services.atendimentos_service import (
    CANAIS_PADRAO,
    CRITICIDADES,
    atualizar_atendimento,
    buscar_correspondencias_cliente,
    consultar_atendimentos,
    ensure_schema,
    listar_anexos_atendimento,
    listar_clientes,
    metricas_resumo,
    ranking_clientes_motivos,
    registrar_atendimento,
)
from services.auth_guard import require_login, normalize_perfil

st.set_page_config(page_title="Registro de Atendimentos", page_icon="📝", layout="wide")

perfil = require_login()
usuario_id = st.session_state.get("usuario_id")
nome_usuario = str(st.session_state.get("usuario_nome", "Analista"))

ensure_schema()

st.title("📝 Registro de Atendimentos")
st.markdown("Lançamento diário de atendimentos com cliente obrigatório, anexos, filtros e busca semântica.")

with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "- Registre atendimentos em sequência no formulário da aba **Lançar Atendimento**.\n"
        "- O cliente é obrigatório e o formulário valida os campos críticos antes de salvar.\n"
        "- Use a aba **Consulta** para filtrar por período e buscar por assunto (busca semântica).\n"
        "- Coordenador/Supervisor/Dev têm visão consolidada na aba **Gestão**."
    )

abas = ["📝 Lançar Atendimento", "🔎 Consulta de Atendimentos"]
if perfil in ("coordenador", "dev", "supervisor"):
    abas.append("📊 Gestão")
tab_lancar, tab_consulta, *rest = st.tabs(abas)
tab_gestao = rest[0] if rest else None


def _carregar_analistas_ativos() -> pd.DataFrame:
    engine = get_connection()
    q = text(
        """
        SELECT id, nome, perfil
        FROM usuarios
        WHERE ativo = TRUE
        ORDER BY nome
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)
    if df.empty:
        return df
    df["perfil_norm"] = df["perfil"].astype(str).apply(normalize_perfil)
    return df


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Atendimentos")
    return out.getvalue()


with tab_lancar:
    st.subheader("Novo Atendimento")
    if "p8_uploader_nonce" not in st.session_state:
        st.session_state["p8_uploader_nonce"] = 0

    def _reset_form_p8() -> None:
        keys = [
            "p8_razao_social",
            "p8_cnpj",
            "p8_telefone",
            "p8_match_cliente",
            "p8_contato_nome",
            "p8_email_contato",
            "p8_setor",
            "p8_categoria",
            "p8_criticidade",
            "p8_canal",
            "p8_protocolo",
            "p8_duracao_min",
            "p8_motivo",
            "p8_solucao",
            "p8_resolvido",
            "p8_abriu_chamado",
            "p8_nr_chamado",
            "p8_data_atendimento",
        ]
        for k in keys:
            st.session_state.pop(k, None)
        st.session_state["p8_uploader_nonce"] = st.session_state.get("p8_uploader_nonce", 0) + 1

    st.caption("Digite Razão Social/CNPJ/Telefone. O sistema sugere correspondências exatas em tempo real.")
    c_ident1, c_ident2, c_ident3 = st.columns(3)
    razao_social = c_ident1.text_input("Razão Social *", key="p8_razao_social", placeholder="Ex.: Posto Mahl")
    cnpj_in = c_ident2.text_input("CNPJ", key="p8_cnpj", placeholder="00.000.000/0000-00")
    telefone = c_ident3.text_input("Telefone/Celular", key="p8_telefone", placeholder="(xx) xxxxx-xxxx")

    df_matches = buscar_correspondencias_cliente(cnpj=cnpj_in, telefone=telefone, limite=8)
    cliente_id_escolhido = None
    if not df_matches.empty:
        st.markdown("**Correspondências exatas encontradas:**")
        opcoes_match = {
            f"{r['razao_social']} | CNPJ: {r['cnpj'] or 'não informado'} | TEL: {r['telefone'] or '-'} | via {r['origem_match']}": int(r["id_cliente"])
            for _, r in df_matches.iterrows()
        }
        escolha_match = st.selectbox(
            "Selecione a opção correta (mouse/teclado) ou deixe em branco para cadastrar novo",
            ["-- Cadastrar novo cliente/informação --"] + list(opcoes_match.keys()),
            key="p8_match_cliente",
        )
        if escolha_match != "-- Cadastrar novo cliente/informação --":
            cliente_id_escolhido = opcoes_match[escolha_match]
            st.success("Cadastro existente selecionado. Os dados novos (telefone/CNPJ ausentes) serão incorporados se necessário.")
    else:
        if cnpj_in.strip() or telefone.strip():
            st.info("Nenhuma correspondência exata. Ao salvar, o cadastro será criado/atualizado automaticamente.")

    with st.form("form_atendimento", clear_on_submit=False):
        st.markdown("#### 👤 Dados de contato")
        c1, c2 = st.columns(2)
        contato_nome = c1.text_input("Contato", key="p8_contato_nome")
        email_contato = c2.text_input("E-mail do contato", key="p8_email_contato")

        st.markdown("#### 🗂️ Tipificação")
        t1, t2, t3 = st.columns(3)
        setor = t1.selectbox("Setor *", ["Suporte Geral", "TEF"], key="p8_setor")
        categoria = t2.text_input("Categoria *", placeholder="Ex.: Instalação, Dúvida Fiscal, Lentidão...", key="p8_categoria")
        criticidade = t3.selectbox("Criticidade *", CRITICIDADES, key="p8_criticidade")

        st.markdown("#### 📞 Canal")
        cc1, cc2, cc3 = st.columns(3)
        canal = cc1.selectbox("Canal *", CANAIS_PADRAO, key="p8_canal")
        protocolo = cc2.text_input("Protocolo", key="p8_protocolo")
        duracao_min = cc3.number_input("Duração (min)", min_value=0, step=1, value=0, key="p8_duracao_min")
        if canal == "Chat Multi360":
            st.caption("Para canal Multi360, o protocolo é obrigatório.")

        st.markdown("#### 📝 Detalhes")
        motivo = st.text_area("Motivo / Assunto *", height=120, key="p8_motivo")
        solucao = st.text_area("Solução", height=120, key="p8_solucao")
        d1, d2, d3 = st.columns(3)
        resolvido = d1.checkbox("Resolvido?", key="p8_resolvido")
        abriu_chamado = d2.checkbox("Precisou abrir chamado?", key="p8_abriu_chamado")
        nr_chamado = d3.text_input("Nº do chamado (quando houver)", key="p8_nr_chamado")
        data_atendimento = st.date_input("Data do atendimento", value=date.today(), key="p8_data_atendimento")

        st.markdown("#### 📎 Anexos")
        anexos = st.file_uploader(
            "Selecione arquivos (qualquer formato, múltiplos arquivos)",
            accept_multiple_files=True,
            key=f"p8_anexos_{st.session_state['p8_uploader_nonce']}",
        )
        salvar = st.form_submit_button("✅ Registrar atendimento", type="primary", use_container_width=True)

        if salvar:
            payload = {
                "usuario_id": usuario_id,
                "nome_analista": nome_usuario,
                "cliente_id": cliente_id_escolhido,
                "razao_social": razao_social,
                "cnpj": cnpj_in,
                "contato_nome": contato_nome,
                "telefone": telefone,
                "email_contato": email_contato,
                "setor": setor,
                "categoria": categoria,
                "criticidade": criticidade,
                "canal": canal,
                "protocolo": protocolo,
                "duracao_min": int(duracao_min) if duracao_min else None,
                "motivo": motivo,
                "solucao": solucao,
                "resolvido": resolvido,
                "abriu_chamado": abriu_chamado,
                "nr_chamado": nr_chamado,
                "data_atendimento": datetime.combine(data_atendimento, datetime.now().time()),
                "origem_registro": "MANUAL",
            }
            with st.status("Processando registro do atendimento...", expanded=False) as status:
                ok, msg, novo_id = registrar_atendimento(payload, anexos=anexos)
                status.update(label="Finalizado." if ok else "Falha no registro.", state="complete" if ok else "error")
            if ok:
                st.success(f"Atendimento #{novo_id} registrado com sucesso.")
                st.toast("✅ Atendimento registrado com sucesso!", icon="✅")
                _reset_form_p8()
                st.balloons()
                st.rerun()
            else:
                st.error(msg)

with tab_consulta:
    st.subheader("Consulta e Busca Semântica")
    hoje = date.today()
    ini_default = hoje - timedelta(days=30)

    with st.container(border=True):
        f1, f2, f3, f4 = st.columns([1, 1, 1.2, 1.2])
        data_ini = f1.date_input("Data inicial", value=ini_default, key="f_data_ini")
        data_fim = f2.date_input("Data final", value=hoje, key="f_data_fim")
        setor_f = f3.selectbox("Setor", ["Todos", "Suporte Geral", "TEF"], key="f_setor")
        canal_f = f4.selectbox("Canal", ["Todos"] + CANAIS_PADRAO, key="f_canal")

        busca_sem = st.text_input(
            "Busca semântica por assunto/motivo/solução",
            key="f_semantica",
            placeholder="Ex.: problema TEF em fechamento no mês passado",
        )

        cli_termo = st.text_input("Filtrar cliente por nome/CNPJ/alias", key="f_cli_termo")
        cli_df = listar_clientes(cli_termo, limite=50)
        cli_opts = {"Todos": None}
        for _, r in cli_df.iterrows():
            label = f"{r['razao_social']} ({r['cnpj'] or 'sem CNPJ'})"
            cli_opts[label] = int(r["id_cliente"])
        cliente_lbl = st.selectbox("Cliente", list(cli_opts.keys()), key="f_cliente")
        cliente_id = cli_opts[cliente_lbl]

        analistas_df = _carregar_analistas_ativos()
        analista_id = None
        if perfil in ("coordenador", "dev", "supervisor") and not analistas_df.empty:
            dic_analistas = {"Todos": None}
            for _, r in analistas_df.iterrows():
                dic_analistas[f"{r['nome']} ({r['perfil_norm']})"] = int(r["id"])
            analista_lbl = st.selectbox("Analista", list(dic_analistas.keys()), key="f_analista")
            analista_id = dic_analistas[analista_lbl]

        buscar = st.button("Buscar", type="primary", use_container_width=True)

    if buscar:
        df = consultar_atendimentos(
            usuario_id=usuario_id,
            perfil=perfil,
            data_ini=data_ini,
            data_fim=data_fim,
            cliente_id=cliente_id,
            setor=setor_f,
            canal=canal_f,
            analista_id=analista_id,
            busca_semantica=busca_sem,
            limite=1000,
        )
        st.session_state["df_consulta_atend"] = df

    df_result = st.session_state.get("df_consulta_atend", pd.DataFrame())
    if df_result.empty:
        st.info("Nenhum atendimento encontrado para os filtros selecionados.")
    else:
        m = metricas_resumo(df_result)
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Total", m["total"])
        mc2.metric("Dia", m["dia"])
        mc3.metric("Semana", m["semana"])
        mc4.metric("Mês", m["mes"])
        mc5.metric("Ano", m["ano"])

        st.dataframe(df_result, hide_index=True, use_container_width=True)
        col_exp1, col_exp2 = st.columns(2)
        col_exp1.download_button(
            "📥 Exportar Excel",
            data=_to_excel_bytes(df_result),
            file_name=f"atendimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        col_exp2.download_button(
            "📥 Exportar CSV",
            data=df_result.to_csv(index=False).encode("utf-8"),
            file_name=f"atendimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("### ✏️ Editar atendimento")
        edf = df_result[["id_atendimento", "data_atendimento", "cliente", "setor", "categoria", "canal", "motivo"]].copy()
        choices = [f"#{int(r.id_atendimento)} | {r.cliente} | {r.data_atendimento}" for r in edf.itertuples(index=False)]
        escolha = st.selectbox("Selecione o atendimento", choices, key="ed_sel")
        id_editar = int(escolha.split("|")[0].strip().replace("#", ""))
        row = df_result[df_result["id_atendimento"] == id_editar].iloc[0]

        with st.form("form_editar_atendimento"):
            e1, e2, e3 = st.columns(3)
            setor_e = e1.selectbox("Setor", ["Suporte Geral", "TEF"], index=0 if row["setor"] == "Suporte Geral" else 1)
            categoria_e = e2.text_input("Categoria", value=str(row["categoria"] or ""))
            criticidade_e = e3.selectbox(
                "Criticidade",
                CRITICIDADES,
                index=CRITICIDADES.index(str(row["criticidade"])) if str(row["criticidade"]) in CRITICIDADES else 1,
            )
            ec1, ec2, ec3 = st.columns(3)
            canal_e = ec1.selectbox("Canal", CANAIS_PADRAO, index=CANAIS_PADRAO.index(str(row["canal"])) if str(row["canal"]) in CANAIS_PADRAO else 0)
            protocolo_e = ec2.text_input("Protocolo", value=str(row["protocolo"] or ""))
            duracao_e = ec3.number_input("Duração (min)", min_value=0, step=1, value=int(row["duracao_min"] or 0) if "duracao_min" in row else 0)
            motivo_e = st.text_area("Motivo", value=str(row["motivo"] or ""), height=100)
            solucao_e = st.text_area("Solução", value=str(row["solucao"] or ""), height=100)
            eb1, eb2, eb3 = st.columns(3)
            resolvido_e = eb1.checkbox("Resolvido?", value=bool(row["resolvido"]))
            abriu_chamado_e = eb2.checkbox("Abriu chamado?", value=bool(row["abriu_chamado"]))
            nr_chamado_e = eb3.text_input("Nº chamado", value=str(row["nr_chamado"] or ""))

            salvar_ed = st.form_submit_button("Salvar edição", type="primary", use_container_width=True)
            if salvar_ed:
                ok, msg = atualizar_atendimento(
                    id_atendimento=id_editar,
                    usuario_id=int(usuario_id or 0),
                    perfil=perfil,
                    payload={
                        "setor": setor_e,
                        "categoria": categoria_e,
                        "criticidade": criticidade_e,
                        "canal": canal_e,
                        "protocolo": protocolo_e,
                        "duracao_min": int(duracao_e) if duracao_e else None,
                        "motivo": motivo_e,
                        "solucao": solucao_e,
                        "resolvido": resolvido_e,
                        "abriu_chamado": abriu_chamado_e,
                        "nr_chamado": nr_chamado_e,
                    },
                )
                if ok:
                    st.success(msg)
                    st.session_state.pop("df_consulta_atend", None)
                    st.rerun()
                else:
                    st.error(msg)

        anexos_df = listar_anexos_atendimento(id_editar)
        if not anexos_df.empty:
            st.markdown("### 📎 Anexos do atendimento")
            for _, ar in anexos_df.iterrows():
                caminho = str(ar["caminho_arquivo"])
                caminho_abs = caminho if os.path.isabs(caminho) else os.path.join(os.getcwd(), caminho)
                if os.path.exists(caminho_abs):
                    with open(caminho_abs, "rb") as f:
                        st.download_button(
                            label=f"Baixar: {ar['nome_arquivo']}",
                            data=f.read(),
                            file_name=str(ar["nome_arquivo"]),
                            key=f"down_{int(ar['id_anexo'])}",
                        )

if tab_gestao:
    with tab_gestao:
        st.subheader("Visão Consolidada de Gestão")
        df_g = consultar_atendimentos(
            usuario_id=usuario_id,
            perfil=perfil,
            data_ini=date.today() - timedelta(days=3650),
            data_fim=date.today(),
            cliente_id=None,
            setor="Todos",
            canal="Todos",
            analista_id=None,
            busca_semantica="",
            limite=10000,
        )
        if df_g.empty:
            st.info("Sem registros para consolidar.")
        else:
            m = metricas_resumo(df_g)
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Total geral", m["total"])
            k2.metric("Hoje", m["dia"])
            k3.metric("Semana", m["semana"])
            k4.metric("Mês", m["mes"])
            k5.metric("Ano", m["ano"])

            top_clientes, top_motivos = ranking_clientes_motivos(df_g, top_n=10)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Clientes que mais consomem suporte")
                st.dataframe(top_clientes, hide_index=True, use_container_width=True)
            with c2:
                st.markdown("#### Principais motivos/categorias")
                st.dataframe(top_motivos, hide_index=True, use_container_width=True)

            serie = df_g.copy()
            serie["data"] = pd.to_datetime(serie["data_atendimento"], errors="coerce").dt.date
            por_dia = serie.groupby("data").size().reset_index(name="total")
            st.markdown("#### Volume de atendimentos por dia")
            st.line_chart(por_dia.set_index("data")["total"])