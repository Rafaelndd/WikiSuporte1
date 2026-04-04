"""
Cadastro manual de releases Tecnuv.
Utiliza as tabelas chamados, releases e ciclos_homologacao para rastrear
o ciclo de vida completo dos chamados através de múltiplas releases.
"""
import io
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from modules.database import get_connection
from modules.html_texto import limpar_html_bruto

from services.auth_guard import require_login
from services.db_homologacao import (
    backfill_embeddings_release_itens,
    buscar_release_itens_semantico,
    processar_release_completo,
    salvar_arquivo_release,
)

st.set_page_config(page_title="Releases Tecnuv (Manual)", page_icon="🧩", layout="wide")

perfil = require_login()
pode_gerenciar_release = perfil == "admin"


st.title("🧩 Cadastro Manual de Releases Tecnuv")
st.markdown(
    "Registre releases no banco (`releases`, `chamados`, `ciclos_homologacao`) e "
    "vincule os chamados corrigidos."
)
st.markdown("---")
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "Envie o **arquivo do release** (TXT, MD, Word ou PDF). O sistema procura números **(13645)** e cria ciclos de homologação. "
        "Releases aparecem no Dashboard de Chamados e nos alertas da Home."
    )

if not pode_gerenciar_release:
    st.error("⛔ Acesso Negado")
    st.warning("Esta página é exclusiva para usuários com perfil **admin**.")
else:
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
            salvar = st.form_submit_button("Processar e salvar", type="primary", use_container_width="stretch")
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
                            origem="manual",
                            data_liberacao=datetime.combine(data_release, datetime.min.time()),
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
                                        assunto_exibe = limpar_html_bruto(clean) or clean
                                        chamados_assunto[match] = assunto_exibe
                            df_prev = pd.DataFrame({
                                "Chamado": list(chamados_assunto.keys()),
                                "Assunto": [str(v)[:150] for v in chamados_assunto.values()],
                            })
                            st.dataframe(df_prev, hide_index=True, use_container_width="stretch")
                except Exception as e:
                    st.error(f"Erro ao processar release: {e}")

    st.markdown("---")

    # -----------------------------
    # 2. Busca semântica / filtro por chamado nos itens de release
    # -----------------------------
    st.subheader("🔎 Busca nos releases")
    st.caption(
        "Combina **busca por sentido** (embeddings + pgvector, se a migração "
        "`database/migracao_release_itens_embedding.sql` estiver aplicada e a API configurada) "
        "com **filtro opcional pelo número do chamado**. Sem vetor disponível, usa busca por texto (ILIKE)."
    )
    bc1, bc2, bc3 = st.columns([2, 1, 1])
    with bc1:
        q_release = st.text_input(
            "Assunto ou tema",
            key="busca_release_assunto",
            placeholder="Ex.: NF-e, SPED, cadastro de produto",
        )
    with bc2:
        nr_release_filtro = st.text_input(
            "Nº chamado (opcional)",
            key="busca_release_nr",
            placeholder="Somente dígitos",
        )
    with bc3:
        st.write("")
        st.write("")
        executar_busca_release = st.button("Buscar", type="primary", key="btn_busca_release")

    if executar_busca_release:
        nr_parse: int | None = None
        if nr_release_filtro.strip():
            if nr_release_filtro.strip().isdigit():
                nr_parse = int(nr_release_filtro.strip())
            else:
                st.error("Número do chamado deve conter apenas dígitos.")
                nr_parse = -1
        if nr_parse != -1:
            if not (q_release or "").strip() and nr_parse is None:
                st.warning("Informe o assunto/tema **ou** o número do chamado.")
            else:
                try:
                    df_br = buscar_release_itens_semantico(
                        (q_release or "").strip(),
                        nr_chamado=nr_parse,
                        limite=50,
                    )
                    if df_br.empty:
                        st.info("Nenhum item de release encontrado com esses critérios.")
                    else:
                        df_show = df_br.rename(
                            columns={
                                "id_item": "ID item",
                                "nr_chamado": "Chamado",
                                "linha_nota": "Assunto / linha",
                                "versao_release": "Versão",
                                "data_liberacao": "Data release",
                                "score_semantico": "Score (semântico)",
                            }
                        )
                        st.dataframe(df_show, hide_index=True, use_container_width=True)
                except Exception as ex:
                    st.error(f"Erro na busca: {ex}")

    with st.expander("Manutenção: gerar embeddings para itens antigos"):
        st.markdown(
            "Itens cadastrados antes desta melhoria podem não ter vetor. "
            "Use o lote abaixo após aplicar a migração e configurar `EMBEDDING_MODEL` / chaves de API."
        )
        if st.button("Indexar até 200 itens sem embedding", key="btn_backfill_rel_emb"):
            try:
                n_ok = backfill_embeddings_release_itens(200)
                st.success(f"Registros atualizados com embedding: **{n_ok}**")
            except Exception as ex:
                st.error(f"Falha ao indexar: {ex}")

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
                r.data_liberacao AS data_lancamento
            FROM releases r
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
                },
                inplace=True,
            )
            st.dataframe(df_rel, hide_index=True, use_container_width='stretch')
    except Exception as e:
        st.error(f"Erro ao carregar releases: {e}")
