import streamlit as st
import pandas as pd
import re
from datetime import datetime, date
from sqlalchemy import text

from modules.database import get_connection
from services.auth_guard import require_profile


st.set_page_config(page_title="Releases Tecnuv (Manual)", page_icon="🧩", layout="wide")

# Segurança: apenas dev e coordenador podem acessar
perfil = require_profile(
    ["dev", "coordenador"],
    titulo_bloqueio="⛔ Acesso Negado",
    detalhes="Esta tela é exclusiva para registro e manutenção manual dos releases da Tecnuv.",
)

engine = get_connection()

st.title("🧩 Cadastro Manual de Releases Tecnuv")
st.markdown(
    "Use esta tela para registrar manualmente releases da Tecnuv no banco (`releases_tecnuv`) "
    "e vincular automaticamente os chamados corrigidos com base no conteúdo do arquivo de release."
)

st.markdown("---")

# -----------------------------
# Formulário de cadastro
# -----------------------------
st.subheader("Novo release")

with st.form("form_novo_release", clear_on_submit=True):
    col1, col2 = st.columns([2, 1])

    with col1:
        data_release = st.date_input("Data do Release", value=date.today())
    with col2:
        autor = st.text_input("Autor", placeholder="Ex.: Cristiano Felicidade")

    arquivo_release = st.file_uploader(
        "Arquivo do release (texto ou Word)",
        type=["txt", "md", "doc", "docx"],
        help=(
            "Envie o arquivo contendo as notas de versão. "
            "O sistema irá identificar automaticamente os números de chamados no texto (ex.: (13645))."
        ),
    )

    colb1, colb2 = st.columns([1, 3])
    with colb1:
        salvar = st.form_submit_button("Processar e salvar", type="primary", use_container_width=True)
    with colb2:
        st.caption(
            "Ao salvar, será criado um registro em `releases_tecnuv` e vínculos em "
            "`chamados_corrigidos_releases` para cada número de chamado identificado automaticamente "
            "no conteúdo do arquivo."
        )

    if salvar:
        if not autor.strip():
            st.error("Por favor, informe o **Autor** do release.")
        elif not arquivo_release:
            st.error("Por favor, carregue o **arquivo do release**.")
        else:
            try:
                raw_bytes = arquivo_release.read()
                text_content = ""

                nome_arquivo = arquivo_release.name or ""
                nome_lower = nome_arquivo.lower()

                if nome_lower.endswith((".doc", ".docx")):
                    try:
                        import docx  # type: ignore

                        doc = docx.Document(arquivo_release)
                        text_content = "\n".join(p.text for p in doc.paragraphs)
                    except Exception:
                        # Fallback best-effort: tenta decodificar como texto simples
                        text_content = raw_bytes.decode("utf-8", errors="ignore")
                else:
                    text_content = raw_bytes.decode("utf-8", errors="ignore")

                text_content = text_content or ""

                if not text_content.strip():
                    st.error("Não foi possível ler conteúdo textual do arquivo enviado.")
                else:
                    # Primeira linha não vazia como título/versão sugeridos
                    first_line = next(
                        (ln.strip() for ln in text_content.splitlines() if ln.strip()),
                        "Release sem título",
                    )
                    titulo = first_line[:255]
                    versao = first_line[:100]

                    # Extrai chamados no padrão (12345)
                    chamados_nums = []
                    for match in re.findall(r"\((\d{4,6})\)", text_content):
                        try:
                            chamados_nums.append(int(match))
                        except ValueError:
                            continue
                    chamados_nums = sorted(set(chamados_nums))

                    with engine.begin() as conn:
                        id_rel = conn.execute(
                            text(
                                """
                                INSERT INTO releases_tecnuv
                                    (versao, data_lancamento, titulo, autor, notas_atualizacao, link_download, data_extracao, nr_chamado)
                                VALUES
                                    (:versao, :data_lancamento, :titulo, :autor, :notas, :link_download, :data_extracao, NULL)
                                RETURNING id_release
                                """
                            ),
                            {
                                "versao": versao,
                                "data_lancamento": data_release,
                                "titulo": titulo,
                                "autor": autor.strip(),
                                "notas": text_content,
                                "link_download": "",
                                "data_extracao": datetime.now(),
                            },
                        ).scalar_one()

                        if chamados_nums:
                            for nr in chamados_nums:
                                conn.execute(
                                    text(
                                        """
                                        INSERT INTO chamados_corrigidos_releases (nr_chamado, id_release)
                                        VALUES (:nr, :rel)
                                        ON CONFLICT (nr_chamado, id_release) DO NOTHING
                                        """
                                    ),
                                    {"nr": nr, "rel": id_rel},
                                )

                    if chamados_nums:
                        st.success(
                            f"Release registrado com sucesso (ID={id_rel}). "
                            f"Foram identificados e vinculados {len(chamados_nums)} chamado(s): "
                            f"{', '.join(str(n) for n in chamados_nums)}."
                        )
                    else:
                        st.success(
                            f"Release registrado com sucesso (ID={id_rel}), "
                            "mas nenhum número de chamado foi identificado automaticamente no texto."
                        )
            except Exception as e:
                st.error(f"Erro ao processar/salvar o release no banco de dados: {e}")

st.markdown("---")

# -----------------------------
# Lista de releases recentes
# -----------------------------
st.subheader("Releases cadastrados recentemente")

try:
    with engine.connect() as conn:
        df_rel = pd.read_sql(
            """
            SELECT
                r.id_release,
                r.versao,
                r.data_lancamento,
                r.titulo,
                r.autor,
                LEFT(r.notas_atualizacao, 200) AS resumo_texto,
                COALESCE(cr.qtd_chamados, 0) AS qtd_chamados
            FROM releases_tecnuv r
            LEFT JOIN (
                SELECT id_release, COUNT(*) AS qtd_chamados
                FROM chamados_corrigidos_releases
                GROUP BY id_release
            ) cr ON cr.id_release = r.id_release
            ORDER BY r.data_lancamento DESC, r.id_release DESC
            LIMIT 20
            """,
            conn,
        )
    if df_rel.empty:
        st.info("Nenhum release cadastrado ainda na tabela `releases_tecnuv`.")
    else:
        df_rel.rename(
            columns={
                "id_release": "ID",
                "versao": "Versão",
                "data_lancamento": "Data de Lançamento",
                "titulo": "Título",
                "autor": "Autor",
                "resumo_texto": "Resumo",
                "qtd_chamados": "Chamados Corrigidos (qtd.)",
            },
            inplace=True,
        )
        st.dataframe(df_rel, hide_index=True, use_container_width=True)
except Exception as e:
    st.error(f"Erro ao carregar a lista de releases: {e}")

