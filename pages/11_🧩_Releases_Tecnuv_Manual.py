"""
Page 11: Cadastro Manual de Releases e Auditoria de Ciclos de Homologação.
Utiliza as tabelas chamados, releases e ciclos_homologacao para rastrear
o ciclo de vida completo dos chamados através de múltiplas releases.
"""
import io
import re
from datetime import date

import pandas as pd
import streamlit as st

from modules.database import get_connection
from services.auth_guard import require_profile
from services.db_homologacao import (
    get_ciclos_aguardando,
    processar_release_completo,
    salvar_arquivo_release,
    update_ciclo_status,
)

st.set_page_config(page_title="Releases Tecnuv (Manual)", page_icon="🧩", layout="wide")

perfil = require_profile(
    ["dev", "coordenador"],
    titulo_bloqueio="⛔ Acesso Negado",
    detalhes="Esta tela é exclusiva para registro e manutenção manual dos releases da Tecnuv.",
)

st.title("🧩 Cadastro Manual de Releases Tecnuv")
st.markdown(
    "Registre releases no banco (`releases`, `chamados`, `ciclos_homologacao`) e "
    "vincule os chamados corrigidos. A equipe de suporte pode atualizar o status de "
    "homologação (Aprovado/Reprovado) na seção de Auditoria abaixo."
)
st.markdown("---")

# -----------------------------
# 1. Formulário de cadastro
# -----------------------------
st.subheader("📤 Novo release")

with st.form("form_novo_release", clear_on_submit=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        data_release = st.date_input("Data do Release", value=date.today())
    with col2:
        autor = st.text_input("Autor", placeholder="Ex.: Cristiano Felicidade")

    arquivo_release = st.file_uploader(
        "Arquivo do release (texto, Word, RTF ou PDF)",
        type=["txt", "md", "doc", "docx", "rtf", "pdf"],
        help=(
            "O sistema identifica números de chamados no formato (13645) e cria ciclos "
            "de homologação com status 'Aguardando'."
        ),
    )

    colb1, colb2 = st.columns([1, 3])
    with colb1:
        salvar = st.form_submit_button("Processar e salvar", type="primary", use_container_width=True)
    with colb2:
        st.caption(
            "Será criado o release, o arquivo será anexado em `releases_tecnuv/` e "
            "os chamados/ciclos registrados com status 'Aguardando'."
        )

    if salvar:
        if not autor.strip():
            st.error("Informe o **Autor** do release.")
        elif not arquivo_release:
            st.error("Carregue o **arquivo do release**.")
        else:
            try:
                raw_bytes = arquivo_release.read()
                text_content = ""
                nome_arquivo = arquivo_release.name or ""
                nome_lower = nome_arquivo.lower()

                if nome_lower.endswith((".doc", ".docx")):
                    try:
                        import docx  # type: ignore
                        doc = docx.Document(io.BytesIO(raw_bytes))
                        text_content = "\n".join(p.text for p in doc.paragraphs)
                    except Exception:
                        text_content = raw_bytes.decode("utf-8", errors="ignore")
                elif nome_lower.endswith(".rtf"):
                    try:
                        from striprtf.striprtf import rtf_to_text  # type: ignore
                        text_content = rtf_to_text(raw_bytes.decode("latin-1", errors="ignore"))
                    except Exception:
                        s = raw_bytes.decode("latin-1", errors="ignore")
                        s = re.sub(r"{\\.*?}|{.*?}", " ", s)
                        s = re.sub(r"\\[a-zA-Z]+\d*", " ", s)
                        text_content = re.sub(r"\s+", " ", s).replace("\n ", "\n").strip()
                elif nome_lower.endswith(".pdf"):
                    try:
                        from pypdf import PdfReader  # type: ignore
                        reader = PdfReader(io.BytesIO(raw_bytes))
                        text_content = "\n".join((p.extract_text() or "") for p in reader.pages)
                    except Exception:
                        text_content = raw_bytes.decode("utf-8", errors="ignore")
                else:
                    text_content = raw_bytes.decode("utf-8", errors="ignore")

                text_content = (text_content or "").strip()
                if not text_content:
                    st.error("Não foi possível extrair texto do arquivo.")
                else:
                    first_line = next(
                        (ln.strip() for ln in text_content.splitlines() if ln.strip()),
                        "Release sem título",
                    )
                    versao = first_line[:50].strip()

                    # Salva o arquivo em disco e obtém o caminho
                    caminho = salvar_arquivo_release(
                        raw_bytes, nome_arquivo, versao
                    )

                    # ETL: release + chamados + ciclos (com anexo)
                    qtd_vinculados, qtd_ciclos = processar_release_completo(
                        versao=versao,
                        texto_completo=text_content,
                        autor=autor.strip(),
                        nome_arquivo=nome_arquivo,
                        caminho_arquivo=caminho,
                    )

                    st.success(
                        f"Release **{versao}** registrado e arquivo anexado em `{caminho}`. "
                        f"{qtd_vinculados} chamado(s) vinculado(s), {qtd_ciclos} novo(s) ciclo(s)."
                    )
                    if qtd_vinculados > 0:
                        chamados_assunto = {}
                        for line in text_content.splitlines():
                            clean = line.strip()
                            if not clean:
                                continue
                            for match in re.findall(r"\((\d{4,6})\)", clean):
                                if match not in chamados_assunto:
                                    chamados_assunto[match] = clean
                        df_prev = pd.DataFrame({
                            "Chamado": list(chamados_assunto.keys()),
                            "Assunto": [v[:150] for v in chamados_assunto.values()],
                        })
                        st.dataframe(df_prev, hide_index=True, use_container_width=True)
            except Exception as e:
                st.error(f"Erro ao processar release: {e}")

st.markdown("---")

# -----------------------------
# 2. Auditoria de Ciclos (status Aguardando)
# -----------------------------
st.subheader("✅ Auditoria de Ciclos de Homologação")
st.caption("Altere o status dos ciclos em 'Aguardando'. Se 'Reprovado', informe o motivo.")

try:
    df_aud = get_ciclos_aguardando()
    if df_aud.empty:
        st.info("Nenhum ciclo com status 'Aguardando' no momento.")
    else:
        # Colunas exibidas (editáveis: status_teste e motivo_reprovacao)
        colunas_exibir = ["id_ciclo", "id_chamado", "assunto", "modulo_sistema", "versao_release", "status_teste", "motivo_reprovacao"]
        df_edit = df_aud[colunas_exibir].copy()
        df_edit.columns = ["ID Ciclo", "Chamado", "Assunto", "Módulo", "Versão", "Status", "Motivo Reprovação"]

        edited = st.data_editor(
            df_edit,
            key="editor_ciclos",
            use_container_width=True,
            column_config={
                "ID Ciclo": st.column_config.NumberColumn(format="%d"),
                "Chamado": st.column_config.TextColumn(disabled=True),
                "Assunto": st.column_config.TextColumn(disabled=True),
                "Módulo": st.column_config.TextColumn(disabled=True),
                "Versão": st.column_config.TextColumn(disabled=True),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Aguardando", "Aprovado", "Reprovado"],
                    required=True,
                ),
                "Motivo Reprovação": st.column_config.TextColumn(
                    "Motivo (obrigatório se Reprovado)",
                    help="Preencha quando o status for Reprovado",
                ),
            },
            hide_index=True,
        )

        if st.button("💾 Salvar alterações de status"):
            erros = []
            for idx, row in edited.iterrows():
                id_ciclo = int(row["ID Ciclo"])
                status = str(row["Status"] or "").strip()
                motivo = str(row["Motivo Reprovação"] or "").strip()
                if status == "Reprovado" and not motivo:
                    erros.append(f"Ciclo {id_ciclo}: motivo obrigatório quando Reprovado.")
                    continue
                if status in ("Aprovado", "Reprovado"):
                    if update_ciclo_status(id_ciclo, status, motivo or None):
                        pass  # sucesso
                    else:
                        erros.append(f"Ciclo {id_ciclo}: falha ao atualizar.")
            if erros:
                for e in erros:
                    st.error(e)
            else:
                st.success("Alterações salvas com sucesso.")
                st.rerun()
except Exception as e:
    st.error(f"Erro ao carregar ciclos: {e}")

st.markdown("---")

# -----------------------------
# 3. Releases recentes
# -----------------------------
st.subheader("📋 Releases cadastrados recentemente")

try:
    engine = get_connection()
    df_rel = pd.read_sql(
        """
        SELECT
            r.id_release,
            r.versao_release AS versao,
            r.data_liberacao AS data_lancamento,
            COALESCE(cr.qtd_chamados, 0) AS qtd_chamados
        FROM releases r
        LEFT JOIN (
            SELECT id_release, COUNT(*) AS qtd_chamados
            FROM ciclos_homologacao
            GROUP BY id_release
        ) cr ON cr.id_release = r.id_release
        ORDER BY r.data_liberacao DESC, r.id_release DESC
        LIMIT 20
        """,
        engine,
    )
    if df_rel.empty:
        st.info("Nenhum release cadastrado na tabela `releases`.")
    else:
        df_rel.rename(
            columns={
                "id_release": "ID",
                "versao": "Versão",
                "data_lancamento": "Data",
                "qtd_chamados": "Ciclos",
            },
            inplace=True,
        )
        st.dataframe(df_rel, hide_index=True, use_container_width=True)
except Exception as e:
    st.error(f"Erro ao carregar releases: {e}")
