from __future__ import annotations

import io
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st
from sqlalchemy import text

from modules.database import get_connection
from services.atendimentos_service import (
    CANAIS_PADRAO,
    CRITICIDADES,
    CATEGORIAS_INICIAIS,
    adicionar_categoria_atendimento,
    atualizar_atendimento,
    buscar_cliente_por_cnpj,
    buscar_correspondencias_cliente,
    consultar_atendimentos,
    ensure_schema,
    excluir_atendimento,
    listar_categorias_atendimento,
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
    df_export = df.copy()
    for col in df_export.columns:
        serie = df_export[col]
        if pd.api.types.is_datetime64tz_dtype(serie):
            df_export[col] = serie.dt.tz_localize(None)
        elif col == "data_atendimento":
            dt = pd.to_datetime(serie, errors="coerce")
            if getattr(dt.dt, "tz", None) is not None:
                dt = dt.dt.tz_localize(None)
            df_export[col] = dt
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Atendimentos")
    return out.getvalue()


def _formatar_cnpj(cnpj: Any) -> str:
    s = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
    if len(s) != 14:
        return str(cnpj or "")
    return f"{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}"


def _formatar_telefone(numero: Any) -> str:
    s = "".join(ch for ch in str(numero or "") if ch.isdigit())
    if len(s) == 11:
        return f"({s[:2]}) {s[2:7]}-{s[7:]}"
    if len(s) == 10:
        return f"({s[:2]}) {s[2:6]}-{s[6:]}"
    return str(numero or "")


def _formatar_telefone_input_br(numero: Any) -> str:
    s = "".join(ch for ch in str(numero or "") if ch.isdigit())[:11]
    if not s:
        return ""
    if len(s) <= 2:
        return f"({s}"
    ddd = s[:2]
    resto = s[2:]
    if len(resto) <= 4:
        return f"({ddd}) {resto}"
    if len(resto) <= 8:
        return f"({ddd}) {resto[:4]}-{resto[4:]}"
    return f"({ddd}) {resto[0]} {resto[1:5]}-{resto[5:9]}"


def _mascarar_telefone_campo(campo_key: str) -> None:
    st.session_state[campo_key] = _formatar_telefone_input_br(st.session_state.get(campo_key, ""))


def _fmt_bool(valor: Any, positivo: str = "Sim", negativo: str = "Não") -> str:
    return positivo if bool(valor) else negativo


def _preparar_df_usuario(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    base = df.copy()
    base["data_atendimento"] = pd.to_datetime(base["data_atendimento"], errors="coerce")
    out = pd.DataFrame(
        {
            "Data/Hora": base["data_atendimento"].dt.strftime("%d/%m/%Y %H:%M"),
            "Analista": base["analista"].fillna("-"),
            "Cliente": base["cliente"].fillna("-"),
            "CNPJ": base["cnpj"].apply(_formatar_cnpj),
            "Contato": base["contato"].replace("", "-").fillna("-"),
            "Telefone": base["telefone"].apply(_formatar_telefone),
            "Setor": base["setor"].fillna("-"),
            "Categoria": base["categoria"].fillna("-"),
            "Criticidade": base["criticidade"].fillna("-"),
            "Canal": base["canal"].fillna("-"),
            "Protocolo": base["protocolo"].replace("", "-").fillna("-"),
            "Duração (min)": base["duracao_min"].fillna(0).astype(int),
            "Motivo do contato": base["motivo"].fillna("-"),
            "Solução aplicada": base["solucao"].replace("", "-").fillna("-"),
            "Status": base["resolvido"].apply(lambda x: _fmt_bool(x, "Resolvido", "Pendente")),
            "Chamado aberto": base["abriu_chamado"].apply(_fmt_bool),
            "Nº do chamado": base["nr_chamado"].replace("", "-").fillna("-"),
        }
    )
    if "score_semantico" in base.columns and base["score_semantico"].notna().any():
        out["Aderência da busca"] = (
            (base["score_semantico"].fillna(0).clip(lower=0, upper=1) * 100).round(0).astype(int).astype(str) + "%"
        )
    return out


def _render_kpi_cards(cards: list[tuple[str, str]]) -> None:
    if not cards:
        return
    cols = st.columns(len(cards))
    for col, (label, value) in zip(cols, cards):
        col.metric(label, value)


def _to_pdf_bytes(
    df: pd.DataFrame,
    report_type: str = "Relatório de Atendimentos",
    periodo: str = "",
    emitido_por: str = "",
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Table, TableStyle
    except Exception as e:
        raise RuntimeError(
            "Biblioteca 'reportlab' não encontrada para gerar PDF. "
            "Instale com: pip install reportlab"
        ) from e

    data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    sistema_nome = "WikiSuporte"
    arquivo = io.BytesIO()
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(arquivo, pagesize=landscape(A4))

    # Colunas amigáveis para usuário final (sem IDs técnicos)
    cols = [
        "Data/Hora",
        "Analista",
        "Cliente",
        "Categoria",
        "Criticidade",
        "Canal",
        "Status",
        "Chamado aberto",
    ]
    pdf_df = df[[col for col in cols if col in df.columns]].copy()

    # Limita tamanho textual para caber na página
    for col in pdf_df.columns:
        pdf_df[col] = pdf_df[col].astype(str).str.slice(0, 48)

    rows_per_page = 24
    total_rows = len(pdf_df)
    total_pages = max(1, (total_rows + rows_per_page - 1) // rows_per_page)

    # Larguras de coluna em milímetros (proporção visual)
    col_width_map = {
        "Data/Hora": 34,
        "Analista": 32,
        "Cliente": 68,
        "Categoria": 52,
        "Criticidade": 24,
        "Canal": 32,
        "Status": 22,
        "Chamado aberto": 26,
    }
    col_widths = [col_width_map.get(col, 25) * mm for col in pdf_df.columns]

    for page_idx in range(total_pages):
        y_top = page_h - 12 * mm
        x_left = 12 * mm

        # Cabeçalho institucional
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x_left, y_top, sistema_nome)
        c.setFont("Helvetica", 10)
        c.drawString(x_left, y_top - 6 * mm, report_type)
        c.drawString(x_left, y_top - 11 * mm, f"Data da geração: {data_geracao}")
        c.drawString(x_left, y_top - 16 * mm, f"Total de registros: {total_rows}")
        if periodo:
            c.drawString(x_left, y_top - 21 * mm, f"Período: {periodo}")
        if emitido_por:
            c.drawString(x_left, y_top - 26 * mm, f"Emitido por: {emitido_por}")

        # Rodapé com paginação
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - 12 * mm, 8 * mm, f"Página {page_idx + 1} de {total_pages}")

        ini = page_idx * rows_per_page
        fim = ini + rows_per_page
        page_df = pdf_df.iloc[ini:fim]

        data = [list(page_df.columns)] + page_df.values.tolist()
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.HexColor("#eef2f7")]),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )

        tw, th = table.wrapOn(c, page_w - 24 * mm, page_h - 54 * mm)
        table.drawOn(c, x_left, page_h - 46 * mm - th)
        c.showPage()

    c.save()
    arquivo.seek(0)
    return arquivo.getvalue()


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, float) and pd.isna(value):
            return default
        if pd.isna(value):  # type: ignore[arg-type]
            return default
        return int(value)
    except Exception:
        return default


with tab_lancar:
    st.subheader("Novo Atendimento")
    if "p8_uploader_nonce" not in st.session_state:
        st.session_state["p8_uploader_nonce"] = 0
    if "p8_form_nonce" not in st.session_state:
        st.session_state["p8_form_nonce"] = 0
    if st.session_state.get("p8_reset_pending"):
        st.session_state["p8_uploader_nonce"] = st.session_state.get("p8_uploader_nonce", 0) + 1
        st.session_state["p8_form_nonce"] = st.session_state.get("p8_form_nonce", 0) + 1
        st.session_state["p8_reset_pending"] = False
    p8n = st.session_state["p8_form_nonce"]
    if st.session_state.get("p8_last_saved_id"):
        msg_saved = str(st.session_state.get("p8_last_saved_msg") or "Atendimento registrado com sucesso.")
        st.toast("✅ Atendimento registrado com sucesso!", icon="✅")
        st.success(f"Atendimento #{st.session_state['p8_last_saved_id']}: {msg_saved}")
        st.balloons()
        st.session_state.pop("p8_last_saved_id", None)
        st.session_state.pop("p8_last_saved_msg", None)

    def _reset_form_p8() -> None:
        st.session_state["p8_reset_pending"] = True

    categorias = listar_categorias_atendimento() or list(CATEGORIAS_INICIAIS)
    if perfil == "dev":
        with st.expander("⚙️ Gerenciar categorias de atendimento (DEV)"):
            nova_categoria = st.text_input("Nova categoria", key="p8_nova_categoria_dev")
            if st.button("Adicionar categoria", key="p8_add_categoria_dev", use_container_width=True):
                ok_cat, msg_cat = adicionar_categoria_atendimento(nova_categoria, perfil)
                if ok_cat:
                    st.success(msg_cat)
                    st.rerun()
                else:
                    st.error(msg_cat)

    st.caption("Digite CNPJ e Telefone. Se o CNPJ existir, o cliente será identificado automaticamente.")
    razao_key = f"p8_razao_social_{p8n}"
    cnpj_key = f"p8_cnpj_{p8n}"
    telefone_key = f"p8_telefone_{p8n}"
    cliente_por_cnpj = buscar_cliente_por_cnpj(st.session_state.get(cnpj_key, ""))
    if cliente_por_cnpj:
        st.session_state[razao_key] = str(cliente_por_cnpj.get("razao_social") or "")
    c_ident1, c_ident2, c_ident3 = st.columns(3)
    razao_social = c_ident1.text_input(
        "Razão Social *",
        key=razao_key,
        placeholder="Ex.: Posto Mahl",
        disabled=bool(cliente_por_cnpj),
    )
    cnpj_in = c_ident2.text_input("CNPJ", key=cnpj_key, placeholder="00.000.000/0000-00")
    telefone = c_ident3.text_input(
        "Telefone/Celular",
        key=telefone_key,
        placeholder="(48) 9 9999-8888",
        help="Formato brasileiro. Ex.: (48) 9 9999-8888",
        on_change=_mascarar_telefone_campo,
        args=(telefone_key,),
    )

    df_matches = buscar_correspondencias_cliente(cnpj=cnpj_in, telefone=telefone, limite=8)
    cliente_id_escolhido = None
    razao_social_payload = razao_social
    if cliente_por_cnpj:
        cliente_id_escolhido = int(cliente_por_cnpj["id_cliente"])
        razao_social_payload = str(cliente_por_cnpj["razao_social"] or "")
        st.success(f"Cliente identificado automaticamente pelo CNPJ: {razao_social_payload}")
    if not cliente_por_cnpj and not df_matches.empty:
        st.markdown("**Correspondências exatas encontradas:**")
        opcoes_match = {
            f"{r['razao_social']} | CNPJ: {r['cnpj'] or 'não informado'} | TEL: {r['telefone'] or '-'} | via {r['origem_match']}": int(r["id_cliente"])
            for _, r in df_matches.iterrows()
        }
        escolha_match = st.selectbox(
            "Selecione a opção correta (mouse/teclado) ou deixe em branco para cadastrar novo",
            ["-- Cadastrar novo cliente/informação --"] + list(opcoes_match.keys()),
            key=f"p8_match_cliente_{p8n}",
        )
        if escolha_match != "-- Cadastrar novo cliente/informação --":
            cliente_id_escolhido = opcoes_match[escolha_match]
            if not cliente_por_cnpj:
                escolhido = next((r for _, r in df_matches.iterrows() if int(r["id_cliente"]) == cliente_id_escolhido), None)
                if escolhido is not None:
                    razao_social_payload = str(escolhido["razao_social"] or razao_social_payload)
            st.success("Cadastro existente selecionado. Os dados novos (telefone/CNPJ ausentes) serão incorporados se necessário.")
    elif not cliente_por_cnpj:
        if cnpj_in.strip() or telefone.strip():
            st.info("Nenhuma correspondência exata. Ao salvar, o cadastro será criado/atualizado automaticamente.")

    with st.form("form_atendimento", clear_on_submit=False):
        st.markdown("#### 👤 Dados de contato")
        c1, c2 = st.columns(2)
        contato_nome = c1.text_input("Contato", key=f"p8_contato_nome_{p8n}")
        email_contato = c2.text_input("E-mail do contato", key=f"p8_email_contato_{p8n}")

        st.markdown("#### 🗂️ Tipificação")
        t1, t2, t3 = st.columns(3)
        setor = t1.selectbox("Setor *", ["Suporte Geral", "TEF"], key=f"p8_setor_{p8n}")
        categoria = t2.selectbox("Categoria *", categorias, key=f"p8_categoria_{p8n}")
        criticidade = t3.selectbox("Criticidade *", CRITICIDADES, key=f"p8_criticidade_{p8n}")

        st.markdown("#### 📞 Canal")
        cc1, cc2, cc3 = st.columns(3)
        canal = cc1.selectbox("Canal *", CANAIS_PADRAO, key=f"p8_canal_{p8n}")
        protocolo = cc2.text_input(
            "Protocolo",
            key=f"p8_protocolo_{p8n}",
            help="Obrigatório somente quando o canal for Chat Multi360.",
        )
        duracao_min = cc3.number_input("Duração (min)", min_value=0, step=1, value=0, key=f"p8_duracao_min_{p8n}")
        if canal == "Chat Multi360":
            st.caption("Para canal Multi360, o protocolo é obrigatório.")

        st.markdown("#### 📝 Detalhes")
        motivo = st.text_area("Motivo / Assunto *", height=120, key=f"p8_motivo_{p8n}")
        solucao = st.text_area("Solução", height=120, key=f"p8_solucao_{p8n}")
        d1, d2, d3 = st.columns(3)
        resolvido = d1.checkbox("Resolvido?", key=f"p8_resolvido_{p8n}")
        abriu_chamado = d2.checkbox("Precisou abrir chamado?", key=f"p8_abriu_chamado_{p8n}")
        nr_chamado = d3.text_input("Nº do chamado (quando houver)", key=f"p8_nr_chamado_{p8n}")
        data_atendimento = st.date_input("Data do atendimento", value=date.today(), key=f"p8_data_atendimento_{p8n}")

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
                "razao_social": razao_social_payload,
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
                st.session_state["p8_last_saved_id"] = novo_id
                st.session_state["p8_last_saved_msg"] = msg
                _reset_form_p8()
                st.rerun()
            else:
                st.error(msg)

with tab_consulta:
    st.subheader("Consulta e Busca Semântica")
    hoje = date.today()
    ini_default = hoje - timedelta(days=30)

    with st.container(border=True):
        with st.form("filtro_consulta_atendimentos", clear_on_submit=False):
            f1, f2, f3, f4, f5 = st.columns([1, 1, 1.2, 1.2, 1.1])
            data_ini = f1.date_input("Data inicial", value=ini_default, key="f_data_ini")
            data_fim = f2.date_input("Data final", value=hoje, key="f_data_fim")
            setor_f = f3.selectbox("Setor", ["Todos", "Suporte Geral", "TEF"], key="f_setor")
            canal_f = f4.selectbox("Canal", ["Todos"] + CANAIS_PADRAO, key="f_canal")
            protocolo_f = f5.text_input("Nº protocolo", key="f_protocolo")

            busca_sem = st.text_input(
                "Busca semântica por assunto/motivo/solução",
                key="f_semantica",
                placeholder="Ex.: problema TEF em fechamento no mês passado",
            )

            cli_termo = st.text_input("Filtrar cliente por nome/CNPJ/alias", key="f_cli_termo")
            cli_df = listar_clientes(cli_termo, limite=50)
            cli_opts: Dict[str, Optional[int]] = {"Todos": None}
            for _, r in cli_df.iterrows():
                label = f"{r['razao_social']} ({r['cnpj'] or 'sem CNPJ'})"
                cli_opts[label] = int(r["id_cliente"])
            cliente_lbl = st.selectbox("Cliente", list(cli_opts.keys()), key="f_cliente")
            cliente_id = cli_opts[cliente_lbl]

            analistas_df = _carregar_analistas_ativos()
            analista_id = None
            if perfil in ("coordenador", "dev", "supervisor") and not analistas_df.empty:
                dic_analistas: Dict[str, Optional[int]] = {"Todos": None}
                for _, r in analistas_df.iterrows():
                    dic_analistas[f"{r['nome']} ({r['perfil_norm']})"] = int(r["id"])
                analista_lbl = st.selectbox("Analista", list(dic_analistas.keys()), key="f_analista")
                analista_id = dic_analistas[analista_lbl]

            b1, b2 = st.columns([2, 1])
            buscar = b1.form_submit_button("Buscar", type="primary", use_container_width=True)
            limpar = b2.form_submit_button("Limpar filtros", use_container_width=True)

    if limpar:
        for k in [
            "f_data_ini",
            "f_data_fim",
            "f_setor",
            "f_canal",
            "f_protocolo",
            "f_semantica",
            "f_cli_termo",
            "f_cliente",
            "f_analista",
            "df_consulta_atend",
            "consulta_realizada_p8",
        ]:
            st.session_state.pop(k, None)
        st.rerun()

    # Consulta só roda quando o usuário clica em Buscar (garante uso do termo digitado)
    if buscar:
        if data_ini > data_fim:
            st.error("A data inicial não pode ser maior que a data final.")
        else:
            df = consultar_atendimentos(
                usuario_id=usuario_id,
                perfil=perfil,
                data_ini=data_ini,
                data_fim=data_fim,
                cliente_id=cliente_id,
                setor=setor_f,
                canal=canal_f,
                protocolo=(protocolo_f or "").strip(),
                analista_id=analista_id,
                busca_semantica=(busca_sem or "").strip(),
                limite=1000,
            )
            st.session_state["df_consulta_atend"] = df
            st.session_state["consulta_realizada_p8"] = True

    df_result = st.session_state.get("df_consulta_atend")
    if df_result is None:
        st.info("Defina os filtros (período, setor, canal, cliente, etc.) e clique em **Buscar** para listar os atendimentos.")
    elif df_result.empty:
        st.warning("Nenhum atendimento encontrado para os filtros e o termo de busca informados. Ajuste o período, o termo ou os filtros e clique em **Buscar** novamente.")
    else:
        m = metricas_resumo(df_result)
        perc_resolvidos = float(df_result["resolvido"].fillna(False).mean() * 100) if "resolvido" in df_result else 0.0
        media_duracao = float(df_result["duracao_min"].fillna(0).mean()) if "duracao_min" in df_result else 0.0
        qtd_chamados = int(df_result["abriu_chamado"].fillna(False).sum()) if "abriu_chamado" in df_result else 0
        _render_kpi_cards(
            [
                ("Total", str(m["total"])),
                ("Resolvidos", f"{perc_resolvidos:.1f}%"),
                ("Tempo médio", f"{media_duracao:.0f} min"),
                ("Com chamado", str(qtd_chamados)),
                ("No mês", str(m["mes"])),
            ]
        )

        st.markdown("#### Resultados para usuário final")
        df_view = _preparar_df_usuario(df_result)
        st.dataframe(df_view, hide_index=True, use_container_width=True)
        try:
            periodo_txt = f"{data_ini.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}"
            pdf_bytes = _to_pdf_bytes(
                df_view,
                report_type="Relatório de Atendimentos",
                periodo=periodo_txt,
                emitido_por=nome_usuario,
            )
            exp1, exp2, exp3 = st.columns(3)
            exp1.download_button(
                "📥 Exportar Excel",
                data=_to_excel_bytes(df_view),
                file_name=f"atendimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            exp2.download_button(
                "📥 Exportar CSV",
                data=df_view.to_csv(index=False).encode("utf-8"),
                file_name=f"atendimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            exp3.download_button(
                "📄 Exportar PDF",
                data=pdf_bytes,
                file_name=f"atendimentos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Falha ao gerar PDF: {e}")

        st.markdown("### ✏️ Editar atendimento")
        edf = df_result[["id_atendimento", "data_atendimento", "cliente", "setor", "categoria", "canal", "motivo"]].copy()
        choices = []
        id_por_label: Dict[str, int] = {}
        for r in edf.itertuples(index=False):
            dt = pd.to_datetime(r.data_atendimento, errors="coerce")
            dt_txt = dt.strftime("%d/%m/%Y %H:%M") if pd.notna(dt) else "-"
            label = f"{dt_txt} | {r.cliente} | {r.categoria} ({r.canal})"
            if label in id_por_label:
                label = f"{label} | ref {int(r.id_atendimento)}"
            id_por_label[label] = int(r.id_atendimento)
            choices.append(label)
        escolha = st.selectbox("Selecione o atendimento", choices, key="ed_sel")
        id_editar = id_por_label[escolha]
        row = df_result[df_result["id_atendimento"] == id_editar].iloc[0]
        autor_id = _safe_int(row.get("usuario_id"), 0)
        usuario_logado_id = _safe_int(usuario_id, 0)
        pode_alterar = autor_id != 0 and autor_id == usuario_logado_id
        if not pode_alterar:
            st.info("Apenas o autor do atendimento pode alterar ou excluir este registro.")
        else:
            categorias_edicao = listar_categorias_atendimento() or list(CATEGORIAS_INICIAIS)
            categoria_atual = str(row["categoria"] or "").strip()
            if categoria_atual and categoria_atual not in categorias_edicao:
                categorias_edicao = [categoria_atual] + categorias_edicao
            with st.form("form_editar_atendimento"):
                e1, e2, e3 = st.columns(3)
                setor_e = e1.selectbox("Setor", ["Suporte Geral", "TEF"], index=0 if row["setor"] == "Suporte Geral" else 1)
                categoria_e = e2.selectbox(
                    "Categoria",
                    categorias_edicao,
                    index=categorias_edicao.index(categoria_atual) if categoria_atual in categorias_edicao else 0,
                )
                criticidade_e = e3.selectbox(
                    "Criticidade",
                    CRITICIDADES,
                    index=CRITICIDADES.index(str(row["criticidade"])) if str(row["criticidade"]) in CRITICIDADES else 1,
                )
                ec1, ec2, ec3 = st.columns(3)
                canal_e = ec1.selectbox("Canal", CANAIS_PADRAO, index=CANAIS_PADRAO.index(str(row["canal"])) if str(row["canal"]) in CANAIS_PADRAO else 0)
                protocolo_e = ec2.text_input("Protocolo", value=str(row["protocolo"] or ""))
                duracao_base = _safe_int(row["duracao_min"], 0) if "duracao_min" in row.index else 0
                duracao_e = ec3.number_input("Duração (min)", min_value=0, step=1, value=duracao_base)
                motivo_e = st.text_area("Motivo", value=str(row["motivo"] or ""), height=100)
                solucao_e = st.text_area("Solução", value=str(row["solucao"] or ""), height=100)
                eb1, eb2, eb3 = st.columns(3)
                resolvido_e = eb1.checkbox("Resolvido", value=bool(row["resolvido"]))
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
                            "duracao_min": _safe_int(duracao_e, 0),
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

            col_exc1, col_exc2 = st.columns([1, 2])
            confirma_exc = col_exc1.checkbox("Confirmo exclusão", key=f"p8_conf_excluir_{id_editar}")
            if col_exc2.button(
                "🗑️ Excluir atendimento",
                key=f"p8_btn_excluir_{id_editar}",
                use_container_width=True,
                disabled=not confirma_exc,
            ):
                ok_exc, msg_exc = excluir_atendimento(id_editar, usuario_logado_id)
                if ok_exc:
                    st.success(msg_exc)
                    st.session_state.pop("df_consulta_atend", None)
                    st.rerun()
                else:
                    st.error(msg_exc)

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
        st.caption("Indicadores de performance, volume e qualidade para acompanhamento diário.")
        g1, g2, g3 = st.columns([1, 1, 1.2])
        periodo = g1.selectbox("Período", ["30 dias", "90 dias", "180 dias", "365 dias", "Personalizado"], index=1)
        setor_g = g2.selectbox("Setor", ["Todos", "Suporte Geral", "TEF"], key="g_setor")
        canal_g = g3.selectbox("Canal", ["Todos"] + CANAIS_PADRAO, key="g_canal")
        ini_g = date.today() - timedelta(days=90)
        fim_g = date.today()
        if periodo == "30 dias":
            ini_g = date.today() - timedelta(days=30)
        elif periodo == "180 dias":
            ini_g = date.today() - timedelta(days=180)
        elif periodo == "365 dias":
            ini_g = date.today() - timedelta(days=365)
        elif periodo == "Personalizado":
            p1, p2 = st.columns(2)
            ini_g = p1.date_input("Data inicial da gestão", value=date.today() - timedelta(days=90), key="g_data_ini")
            fim_g = p2.date_input("Data final da gestão", value=date.today(), key="g_data_fim")
        df_g = consultar_atendimentos(
            usuario_id=usuario_id,
            perfil=perfil,
            data_ini=ini_g,
            data_fim=fim_g,
            cliente_id=None,
            setor=setor_g,
            canal=canal_g,
            analista_id=None,
            busca_semantica="",
            limite=10000,
        )
        if df_g.empty:
            st.info("Sem registros para consolidar.")
        else:
            m = metricas_resumo(df_g)
            perc_resolvidos = float(df_g["resolvido"].fillna(False).mean() * 100) if "resolvido" in df_g else 0.0
            media_duracao = float(df_g["duracao_min"].fillna(0).mean()) if "duracao_min" in df_g else 0.0
            clientes_unicos = int(df_g["cliente"].nunique()) if "cliente" in df_g else 0
            analistas_ativos = int(df_g["analista"].nunique()) if "analista" in df_g else 0
            _render_kpi_cards(
                [
                    ("Total geral", str(m["total"])),
                    ("Resolvidos", f"{perc_resolvidos:.1f}%"),
                    ("Tempo médio", f"{media_duracao:.0f} min"),
                    ("Clientes únicos", str(clientes_unicos)),
                    ("Analistas ativos", str(analistas_ativos)),
                ]
            )

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
            c3, c4 = st.columns(2)
            with c3:
                st.markdown("#### Distribuição por canal")
                por_canal = (
                    df_g.groupby("canal", dropna=False)
                    .size()
                    .reset_index(name="total")
                    .sort_values("total", ascending=False)
                    .head(10)
                )
                st.bar_chart(por_canal.set_index("canal")["total"])
            with c4:
                st.markdown("#### Distribuição por criticidade")
                por_criticidade = (
                    df_g.groupby("criticidade", dropna=False)
                    .size()
                    .reset_index(name="total")
                    .sort_values("total", ascending=False)
                )
                st.bar_chart(por_criticidade.set_index("criticidade")["total"])

            st.markdown("#### Qualidade operacional")
            qual = pd.DataFrame(
                [
                    {"Indicador": "Taxa de resolução", "Valor": f"{perc_resolvidos:.1f}%"},
                    {"Indicador": "Tempo médio por atendimento", "Valor": f"{media_duracao:.0f} min"},
                    {"Indicador": "Atendimentos no período", "Valor": str(m["total"])},
                    {"Indicador": "Atendimentos com chamado aberto", "Valor": str(int(df_g['abriu_chamado'].fillna(False).sum()))},
                ]
            )
            st.dataframe(qual, hide_index=True, use_container_width=True)