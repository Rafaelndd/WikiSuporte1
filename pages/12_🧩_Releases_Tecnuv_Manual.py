"""
Cadastro manual de releases quando a coleta automática não estiver disponível.
"""
import io
import logging
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from services.auth_guard import require_login
from services.db_homologacao import (
    buscar_release_itens_semantico,
    obter_ultimo_release_salvo,
    processar_release_completo,
    salvar_arquivo_release,
)

# Limites para evitar sobrescrita de lote e conteúdo excessivo em processamentos manuais
MAX_BYTES_ARQUIVO_RELEASE = 10_000_000  # 10 MB
MAX_TAMANHO_TEXTO_RELEASE = 2_000_000
MAX_CHAMADOS_POR_RELEASE = 2_000

st.set_page_config(page_title="WikiSuporte — Releases (cadastro manual)", page_icon="🧩", layout="wide")

require_login()

st.title("Cadastro manual de releases")

ultimo_release = obter_ultimo_release_salvo()
if ultimo_release:
    st.info(f"📌 **Release atual = Versão {ultimo_release}**")

st.markdown(
    "Use quando o **arquivo de release** não tiver sido obtido automaticamente. "
    "O sistema lê o texto, identifica **chamados** no formato **(12345)** e registra tudo para "
    "acompanhamento e **busca por número de chamado ou por assunto**."
)
st.markdown("---")

with st.expander("Como funciona"):
    st.markdown(
        "- Envie o arquivo do release (**texto, Word ou PDF**).\n"
        "- Informe **data** e **autor**.\n"
        "- Chamados devem aparecer **entre parênteses**, por exemplo `(13645)`.\n"
        "- Depois do envio, use a busca abaixo para ver **em qual versão** cada item aparece."
    )

st.subheader("Novo release")

with st.form("form_novo_release", clear_on_submit=True):
    col1, col2 = st.columns([2, 1])
    with col1:
        data_release = st.date_input("Data do release", value=date.today())
    with col2:
        autor = st.text_input("Autor", placeholder="Ex.: Nome do responsável")

    arquivo_release = st.file_uploader(
        "Arquivo do release",
        type=["txt", "md", "doc", "docx", "rtf", "pdf"],
        help="O texto será lido para localizar números de chamado entre parênteses.",
    )

    colb1, colb2 = st.columns([1, 3])
    with colb1:
        salvar = st.form_submit_button("Processar e salvar", type="primary", use_container_width="stretch")
    with colb2:
        st.caption(
            "Será criado o registro do release, o arquivo será guardado com segurança e "
            "cada chamado encontrado entrará no fluxo de acompanhamento."
        )

    if salvar:
        if not autor.strip():
            st.error("Informe o **autor** do release.")
        elif not arquivo_release:
            st.error("Selecione o **arquivo do release**.")
        else:
            try:
                raw_bytes = arquivo_release.read()
                if len(raw_bytes) > MAX_BYTES_ARQUIVO_RELEASE:
                    st.error(f"⚠️ O arquivo excede {MAX_BYTES_ARQUIVO_RELEASE / 1024 / 1024:.0f} MB.")
                    st.stop()
                text_content = ""
                nome_arquivo = arquivo_release.name or ""
                nome_lower = nome_arquivo.lower()
                # Alguns releases chegam salvos como .doc/.txt mas o conteúdo real é RTF
                # (ex.: e-mails que renomeiam o anexo) — detecta pela assinatura, não só pela extensão.
                eh_rtf_pelo_conteudo = raw_bytes.lstrip()[:6] == b"{\\rtf1"

                if eh_rtf_pelo_conteudo or nome_lower.endswith(".rtf"):
                    try:
                        from striprtf.striprtf import rtf_to_text  # type: ignore

                        text_content = rtf_to_text(raw_bytes.decode("cp1252", errors="ignore"))
                    except Exception:
                        s = raw_bytes.decode("cp1252", errors="ignore")
                        s = re.sub(r"{\\.*?}|{.*?}", " ", s)
                        s = re.sub(r"\\[a-zA-Z]+\d*", " ", s)
                        text_content = re.sub(r"\s+", " ", s).replace("\n ", "\n").strip()
                elif nome_lower.endswith((".doc", ".docx")):
                    try:
                        import docx  # type: ignore

                        doc = docx.Document(io.BytesIO(raw_bytes))
                        text_content = "\n".join(p.text for p in doc.paragraphs)
                    except Exception:
                        text_content = raw_bytes.decode("utf-8", errors="ignore")
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
                    st.error("Não foi possível ler o conteúdo do arquivo. Tente outro formato.")
                else:
                    if len(text_content) > MAX_TAMANHO_TEXTO_RELEASE:
                        st.error(f"⚠️ O texto extraído supera o limite de {MAX_TAMANHO_TEXTO_RELEASE} caracteres.")
                        st.stop()

                    if len(re.findall(r"\((\d{4,6})\)", text_content)) > MAX_CHAMADOS_POR_RELEASE:
                        st.error(f"⚠️ Muitos chamados encontrados no texto. Limite por envio: {MAX_CHAMADOS_POR_RELEASE}.")
                        st.stop()

                    first_line = next(
                        (ln.strip() for ln in text_content.splitlines() if ln.strip()),
                        "Release sem título",
                    )
                    versao = first_line[:50].strip()

                    caminho = salvar_arquivo_release(raw_bytes, nome_arquivo, versao)

                    processar_release_completo(
                        versao=versao,
                        texto_completo=text_content,
                        autor=autor.strip(),
                        nome_arquivo=nome_arquivo,
                        caminho_arquivo=caminho,
                        origem="manual",
                        data_liberacao=datetime.combine(data_release, datetime.min.time()),
                        limite_itens=MAX_CHAMADOS_POR_RELEASE,
                    )

                    st.success("Release salvo com sucesso!")
            except Exception:
                logging.exception("cadastro manual release")
                st.error("Não foi possível concluir o cadastro. Tente novamente ou fale com o suporte.")

st.markdown("---")

st.subheader("Buscar chamado ou assunto nos releases")
st.markdown(
    "Digite um **número de chamado**, um **tema** (ex.: NF-e, SPED) ou **os dois** para combinar. "
    "O resultado mostra **em qual versão** do release cada ocorrência aparece."
)
bc1, bc2, bc3 = st.columns([2, 1, 1])
with bc1:
    q_release = st.text_input(
        "Palavras ou tema",
        key="busca_release_assunto",
        placeholder="Ex.: nota fiscal, cadastro, erro ao salvar",
    )
with bc2:
    nr_release_filtro = st.text_input(
        "Nº do chamado (opcional)",
        key="busca_release_nr",
        placeholder="Somente números",
    )
with bc3:
    st.write("")
    st.write("")
    executar_busca_release = st.button("Buscar", type="primary", key="btn_busca_release")

if executar_busca_release:
    nr_parse: int | None = None
    nr_bruto = (nr_release_filtro or "").strip()
    if nr_bruto:
        # Tolera formatação extra (ex.: "nº 12345", "12.345", espaços) e considera só os dígitos.
        nr_digitos = re.sub(r"\D", "", nr_bruto)
        if nr_digitos:
            nr_parse = int(nr_digitos)
        else:
            st.error("O número do chamado deve conter dígitos.")
            nr_parse = -1
    # Padroniza o termo de busca: remove espaços nas bordas e colapsa espaços duplos.
    # A comparação no banco já é case-insensitive, então maiúsculas/minúsculas não importam.
    termo_busca = re.sub(r"\s+", " ", (q_release or "").strip())
    if nr_parse != -1:
        if not termo_busca and nr_parse is None:
            st.warning("Informe o **tema** ou o **número do chamado** (ou ambos).")
        else:
            try:
                df_br = buscar_release_itens_semantico(
                    termo_busca,
                    nr_chamado=nr_parse,
                    limite=50,
                )
                if df_br.empty:
                    st.info("Nenhum resultado para essa busca. Confira o número ou tente outras palavras.")
                else:
                    df_show = df_br.drop(columns=["id_item"], errors="ignore").rename(
                        columns={
                            "nr_chamado": "Chamado",
                            "linha_nota": "Descrição no release",
                            "versao_release": "Versão",
                            "data_liberacao": "Data do release",
                            "score_semantico": "Relevância",
                        }
                    )
                    if "Relevância" in df_show.columns and df_show["Relevância"].notna().any():
                        df_show = df_show.copy()
                        rel = df_show["Relevância"]
                        df_show["Relevância"] = rel.apply(
                            lambda x: f"{int(float(x) * 100)}%" if pd.notna(x) and x == x else "—"
                        )
                    st.dataframe(df_show, hide_index=True, use_container_width=True)
            except Exception:
                st.error("A busca não pôde ser concluída. Tente novamente.")
