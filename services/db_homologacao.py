"""
Módulo de acesso a dados para Ciclos de Homologação.
Gerencia chamados, releases e ciclos de teste (aprovação/reprovação).
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection
from modules.html_texto import limpar_html_bruto

# Pasta para salvar arquivos de releases (relativa à raiz do projeto)
PASTA_RELEASES = "releases_tecnuv"


def _emb_to_sql(emb: List[float]) -> str:
    return "[" + ",".join(str(round(x, 8)) for x in emb) + "]"


def _assunto_release_sem_html(linha_bruta: str) -> str:
    """Texto plano para assunto / linha de release (não persiste tags HTML)."""
    s = limpar_html_bruto((linha_bruta or "").strip())
    if not s:
        s = re.sub(r"<[^>]+>", " ", str(linha_bruta or ""))
        s = re.sub(r"\s+", " ", s).strip()
    return s[:8000]


def _try_set_embedding_release_item_conn(conn, id_item: int, texto_plano: str) -> None:
    """Preenche coluna embedding quando API e dimensão coincidem com o banco."""
    t = (texto_plano or "").strip()
    if not t:
        return
    try:
        from services.embedding_service import generate_embedding, get_embedding_dim
    except Exception:
        return
    emb = generate_embedding(t[:4000])
    if not emb:
        return
    if len(emb) != get_embedding_dim():
        return
    try:
        conn.execute(
            text(
                "UPDATE release_itens SET embedding = CAST(:e AS vector) WHERE id_item = :id"
            ),
            {"e": _emb_to_sql(emb), "id": id_item},
        )
    except Exception:
        pass


def _sanitizar_nome_arquivo(nome: str) -> str:
    """Remove caracteres inválidos para nome de arquivo."""
    nome = re.sub(r'[<>:"/\\|?*]', "_", nome)
    return nome.strip() or "release"


def ensure_release(
    versao_release: str,
    autor: Optional[str] = None,
    nome_arquivo: Optional[str] = None,
    texto_completo: Optional[str] = None,
    caminho_arquivo: Optional[str] = None,
) -> int:
    """
    Garante que a versão existe em releases. Cria ou atualiza com dados opcionais.
    Retorna o id_release.
    """
    engine = get_connection()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO releases (versao_release, autor, nome_arquivo, texto_completo, caminho_arquivo)
                VALUES (:versao, :autor, :nome_arquivo, :texto_completo, :caminho)
                ON CONFLICT (versao_release) DO UPDATE SET
                    data_liberacao = CURRENT_TIMESTAMP,
                    autor = COALESCE(EXCLUDED.autor, releases.autor),
                    nome_arquivo = COALESCE(EXCLUDED.nome_arquivo, releases.nome_arquivo),
                    texto_completo = COALESCE(EXCLUDED.texto_completo, releases.texto_completo),
                    caminho_arquivo = COALESCE(EXCLUDED.caminho_arquivo, releases.caminho_arquivo)
                RETURNING id_release
                """
            ),
            {
                "versao": versao_release.strip(),
                "autor": (autor or "").strip() or None,
                "nome_arquivo": (nome_arquivo or "").strip()[:255] or None,
                "texto_completo": (texto_completo or "").strip()[:100000] or None,
                "caminho": (caminho_arquivo or "").strip()[:512] or None,
            },
        )
        return result.scalar_one()


def salvar_arquivo_release(
    raw_bytes: bytes,
    nome_arquivo: str,
    versao: str,
    base_dir: Optional[str] = None,
) -> str:
    """
    Salva o arquivo em releases_tecnuv/ e retorna o caminho relativo.
    Se o arquivo já existir, adiciona sufixo numérico.
    """
    base = Path(base_dir or os.getcwd())
    pasta = base / PASTA_RELEASES
    pasta.mkdir(parents=True, exist_ok=True)

    nome_sanitizado = _sanitizar_nome_arquivo(nome_arquivo)
    stem = Path(nome_sanitizado).stem
    ext = Path(nome_sanitizado).suffix or ".txt"
    caminho_rel = f"{PASTA_RELEASES}/{stem}{ext}"
    caminho_abs = pasta / f"{stem}{ext}"

    contador = 1
    while caminho_abs.exists():
        caminho_rel = f"{PASTA_RELEASES}/{stem}_{contador}{ext}"
        caminho_abs = pasta / f"{stem}_{contador}{ext}"
        contador += 1

    caminho_abs.write_bytes(raw_bytes)
    return caminho_rel


def _extrair_versao_do_titulo(texto: str) -> str:
    m = re.search(r"(\d+\.\d+\.\d+)", texto or "")
    return m.group(1) if m else ""


def get_helpdesk_release_head() -> tuple[str, str]:
    """(titulo_link_primeiro_release, versao_norm). Tabela helpdesk_release_head id=1."""
    try:
        engine = get_connection()
        with engine.connect() as c:
            row = c.execute(
                text("SELECT titulo_link, versao_norm FROM helpdesk_release_head WHERE id = 1")
            ).fetchone()
        if row:
            return (str(row[0] or "").strip(), str(row[1] or "").strip())
    except Exception:
        pass
    return ("", "")


def set_helpdesk_release_head(titulo_link: str, versao_norm: str) -> None:
    """Atualiza o 1º release já sincronizado (versão atual para dashboard)."""
    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO helpdesk_release_head (id, titulo_link, versao_norm, atualizado_em)
                VALUES (1, :tit, :ver, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    titulo_link = EXCLUDED.titulo_link,
                    versao_norm = EXCLUDED.versao_norm,
                    atualizado_em = CURRENT_TIMESTAMP
                """
            ),
            {"tit": (titulo_link or "")[:2000], "ver": (versao_norm or "")[:32]},
        )


def processar_release_completo(
    versao: str,
    texto_completo: str,
    autor: Optional[str] = None,
    nome_arquivo: Optional[str] = None,
    caminho_arquivo: Optional[str] = None,
    origem: str = "manual",
) -> tuple[int, int]:
    """
    Processa release: grava um registro em release_itens por linha com (nr_chamado);
    cria chamados + ciclos de homologação.
    Retorna (qtd_itens_chamados, qtd_ciclos_criados).
    """
    versao = versao[:50].strip()
    ver_norm = _extrair_versao_do_titulo(versao) or _extrair_versao_do_titulo(texto_completo[:500]) or versao
    titulo_release = (texto_completo or "").splitlines()[0].strip()[:500] if texto_completo else versao
    id_release = ensure_release(
        versao_release=versao,
        autor=autor or "Processamento Automático",
        texto_completo=texto_completo[:100000],
        nome_arquivo=(nome_arquivo or "").strip()[:255] or None,
        caminho_arquivo=(caminho_arquivo or "").strip()[:512] or None,
    )

    # Uma entrada por linha que contém (nnnnn) — mesmo chamado pode ter linhas diferentes em releases distintos
    linhas_por_chamado: list[tuple[str, str]] = []
    for line in (texto_completo or "").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        for match in re.findall(r"\((\d{4,6})\)", clean):
            linha_limpa = _assunto_release_sem_html(clean[:4000])
            linhas_por_chamado.append((match, linha_limpa))

    modulos_conhecidos = (
        "POSTOGESTOR", "COMERCIAL", "VENDAS", "FISCAL", "PDV", "FINANCEIRO",
        "ESTOQUE", "COMPRAS", "NF-E", "NFE", "SPED", "CONTRABILIDADE",
    )

    criados_ciclo = 0
    vistos_no_release: set[tuple[int, str]] = set()
    engine = get_connection()
    tem_itens = False
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1 FROM release_itens LIMIT 1"))
        tem_itens = True
    except Exception:
        pass

    for id_chamado_str, linha in linhas_por_chamado:
        nr = int(id_chamado_str)
        key = (nr, linha[:500])
        if key in vistos_no_release:
            continue
        vistos_no_release.add(key)
        if tem_itens:
            try:
                with engine.begin() as conn:
                    result = conn.execute(
                        text(
                            """
                            INSERT INTO release_itens
                            (id_release, nr_chamado, linha_nota, versao, titulo_release, autor, origem)
                            VALUES (:idr, :nr, :linha, :ver, :tit, :autor, :orig)
                            ON CONFLICT (id_release, nr_chamado, linha_nota) DO NOTHING
                            RETURNING id_item
                            """
                        ),
                        {
                            "idr": id_release,
                            "nr": nr,
                            "linha": linha[:8000],
                            "ver": ver_norm[:80],
                            "tit": titulo_release,
                            "autor": (autor or "")[:255] or None,
                            "orig": (origem or "manual")[:32],
                        },
                    )
                    row_ins = result.fetchone()
                    if row_ins and row_ins[0]:
                        _try_set_embedding_release_item_conn(conn, int(row_ins[0]), linha)
            except Exception:
                pass
        modulo = None
        for m in modulos_conhecidos:
            if m in linha.upper():
                modulo = m
                break
        ensure_chamado(id_chamado_str, assunto=linha[:2000], modulo_sistema=modulo)
        if create_ciclo(id_chamado_str, id_release):
            criados_ciclo += 1
        try:
            from services.notificacoes_representante import notificar_release_chamado

            notificar_release_chamado(nr, ver_norm)
        except Exception:
            pass

    return len(vistos_no_release), criados_ciclo


def ensure_chamado(id_chamado: str, assunto: str = "", modulo_sistema: Optional[str] = None) -> None:
    """
    Insere o chamado se não existir. Ignora conflito (ON CONFLICT DO NOTHING).
    """
    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO chamados (id_chamado, assunto, modulo_sistema)
                VALUES (:id_chamado, :assunto, :modulo)
                ON CONFLICT (id_chamado) DO NOTHING
                """
            ),
            {
                "id_chamado": str(id_chamado).strip(),
                "assunto": (assunto or "")[:5000],
                "modulo": (modulo_sistema or "").strip() or None,
            },
        )


def create_ciclo(id_chamado: str, id_release: int) -> int:
    """
    Cria ciclo de homologação com status 'Aguardando'.
    Usa ON CONFLICT DO NOTHING para evitar duplicidade.
    Retorna o id_ciclo se criado, ou 0 se já existia.
    """
    engine = get_connection()
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO ciclos_homologacao (id_chamado, id_release, status_teste)
                VALUES (:id_chamado, :id_release, 'Aguardando')
                ON CONFLICT (id_chamado, id_release) DO NOTHING
                RETURNING id_ciclo
                """
            ),
            {"id_chamado": str(id_chamado).strip(), "id_release": id_release},
        )
        row = result.fetchone()
        return row[0] if row else 0


def get_ciclos_aguardando() -> pd.DataFrame:
    """Retorna todos os ciclos com status 'Aguardando' para auditoria."""
    engine = get_connection()
    query = """
        SELECT
            c.id_ciclo,
            c.id_chamado,
            ch.assunto,
            ch.modulo_sistema,
            r.versao_release,
            r.data_liberacao,
            c.status_teste,
            c.motivo_reprovacao,
            c.data_teste
        FROM ciclos_homologacao c
        JOIN chamados ch ON ch.id_chamado = c.id_chamado
        JOIN releases r ON r.id_release = c.id_release
        WHERE c.status_teste = 'Aguardando'
        ORDER BY r.data_liberacao DESC, c.id_ciclo
    """
    return pd.read_sql(query, engine)


def update_ciclo_status(
    id_ciclo: int,
    status_teste: str,
    motivo_reprovacao: Optional[str] = None,
) -> bool:
    """
    Atualiza status e motivo de um ciclo.
    Se status = 'Reprovado', motivo_reprovacao é obrigatório.
    Retorna True se atualizou com sucesso.
    """
    if status_teste not in ("Aguardando", "Aprovado", "Reprovado"):
        return False
    if status_teste == "Reprovado" and not (motivo_reprovacao and str(motivo_reprovacao).strip()):
        return False

    engine = get_connection()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ciclos_homologacao
                SET status_teste = :status, motivo_reprovacao = :motivo, data_teste = :data_teste
                WHERE id_ciclo = :id_ciclo
                """
            ),
            {
                "id_ciclo": id_ciclo,
                "status": status_teste,
                "motivo": (motivo_reprovacao or "").strip() if status_teste == "Reprovado" else None,
                "data_teste": datetime.now(),
            },
        )
    return True


def get_metricas_homologacao(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
) -> dict:
    """
    Retorna as métricas de homologação para o Dashboard:
    - taxa_retrabalho_global
    - ranking_reincidencia (DataFrame)
    - vulnerabilidade_modulo (DataFrame)
    - gargalo_homologacao (int)
    """
    engine = get_connection()

    # Taxa de Retrabalho Global (com filtro opcional de período)
    if data_inicio is not None and data_fim is not None:
        query_taxa = """
            WITH base AS (
                SELECT c.id_ciclo, c.status_teste
                FROM ciclos_homologacao c
                JOIN releases r ON r.id_release = c.id_release
                WHERE COALESCE(c.data_teste, r.data_liberacao) >= :data_inicio
                  AND COALESCE(c.data_teste, r.data_liberacao) <= :data_fim
            ),
            totais AS (
                SELECT
                    COUNT(*) FILTER (WHERE status_teste IN ('Aprovado', 'Reprovado')) AS testados,
                    COUNT(*) FILTER (WHERE status_teste = 'Reprovado') AS reprovados
                FROM base
            )
            SELECT testados, reprovados,
                   CASE WHEN testados > 0 THEN (reprovados::FLOAT / testados) * 100 ELSE 0 END AS taxa
            FROM totais
        """
        df_taxa = pd.read_sql(query_taxa, engine, params={"data_inicio": data_inicio, "data_fim": data_fim})
    else:
        query_taxa = """
            WITH totais AS (
                SELECT
                    COUNT(*) FILTER (WHERE status_teste IN ('Aprovado', 'Reprovado')) AS testados,
                    COUNT(*) FILTER (WHERE status_teste = 'Reprovado') AS reprovados
                FROM ciclos_homologacao
            )
            SELECT testados, reprovados,
                   CASE WHEN testados > 0 THEN (reprovados::FLOAT / testados) * 100 ELSE 0 END AS taxa
            FROM totais
        """
        df_taxa = pd.read_sql(query_taxa, engine)

    taxa_retrabalho = 0.0
    if not df_taxa.empty:
        taxa_retrabalho = float(df_taxa["taxa"].iloc[0] or 0)

    # Ranking de Reincidência (Top Ofensores - chamados mais vezes devolvidos)
    query_ranking = """
        SELECT id_chamado, qtd_ciclos, reprovacoes
        FROM (
            SELECT
                c.id_chamado,
                COUNT(*) AS qtd_ciclos,
                COUNT(*) FILTER (WHERE c.status_teste = 'Reprovado') AS reprovacoes
            FROM ciclos_homologacao c
            GROUP BY c.id_chamado
            HAVING COUNT(*) > 1
        ) sub
        ORDER BY reprovacoes DESC, qtd_ciclos DESC
        LIMIT 20
    """
    df_ranking = pd.read_sql(query_ranking, engine)

    # Vulnerabilidade por Módulo
    query_modulo = """
        SELECT
            COALESCE(ch.modulo_sistema, 'Não informado') AS modulo_sistema,
            COUNT(*) FILTER (WHERE c.status_teste = 'Reprovado') AS reprovacoes
        FROM ciclos_homologacao c
        JOIN chamados ch ON ch.id_chamado = c.id_chamado
        GROUP BY ch.modulo_sistema
        HAVING COUNT(*) FILTER (WHERE c.status_teste = 'Reprovado') > 0
        ORDER BY reprovacoes DESC
    """
    df_modulo = pd.read_sql(query_modulo, engine)

    # Gargalo de Homologação
    query_gargalo = "SELECT COUNT(*) AS total FROM ciclos_homologacao WHERE status_teste = 'Aguardando'"
    gargalo = int(pd.read_sql(query_gargalo, engine)["total"].iloc[0])

    return {
        "taxa_retrabalho_global": taxa_retrabalho,
        "ranking_reincidencia": df_ranking,
        "vulnerabilidade_modulo": df_modulo,
        "gargalo_homologacao": gargalo,
    }


def buscar_release_itens_semantico(
    consulta: str,
    nr_chamado: Optional[int] = None,
    limite: int = 40,
) -> pd.DataFrame:
    """
    Busca em release_itens por similaridade (pgvector + embedding da consulta) ou ILIKE.
    Filtro opcional por número do chamado. Exige migração `migracao_release_itens_embedding.sql`
    para ranking semântico; sem coluna embedding ou sem API, usa texto.
    """
    engine = get_connection()
    consulta = (consulta or "").strip()
    params: dict = {"lim": int(limite)}
    nr_filter: Optional[int] = None
    if nr_chamado is not None:
        try:
            nr_filter = int(nr_chamado)
        except (TypeError, ValueError):
            nr_filter = None

    sql_nr_ri = ""
    if nr_filter is not None:
        params["nr"] = nr_filter
        sql_nr_ri = " AND ri.nr_chamado = :nr "

    if consulta:
        try:
            from services.embedding_service import generate_embedding, get_embedding_dim

            emb = generate_embedding(consulta[:3000])
            dim = get_embedding_dim()
            if emb and len(emb) == dim:
                params_vec = dict(params)
                params_vec["emb"] = _emb_to_sql(emb)
                q = f"""
                SELECT
                    ri.id_item,
                    ri.nr_chamado,
                    ri.linha_nota,
                    r.versao_release,
                    r.data_liberacao,
                    (1 - (ri.embedding <=> CAST(:emb AS vector))) AS score_semantico
                FROM release_itens ri
                JOIN releases r ON r.id_release = ri.id_release
                WHERE ri.embedding IS NOT NULL
                {sql_nr_ri}
                ORDER BY ri.embedding <=> CAST(:emb AS vector)
                LIMIT :lim
                """
                df_vec = pd.read_sql(text(q), engine, params=params_vec)
                if not df_vec.empty:
                    return df_vec
        except Exception:
            pass

        params = dict(params)
        params["pat"] = f"%{consulta[:500]}%"
        q = f"""
        SELECT
            ri.id_item,
            ri.nr_chamado,
            ri.linha_nota,
            r.versao_release,
            r.data_liberacao,
            NULL::DOUBLE PRECISION AS score_semantico
        FROM release_itens ri
        JOIN releases r ON r.id_release = ri.id_release
        WHERE ri.linha_nota ILIKE :pat
        {sql_nr_ri}
        ORDER BY r.data_liberacao DESC NULLS LAST, ri.id_item DESC
        LIMIT :lim
        """
        return pd.read_sql(text(q), engine, params=params)

    if nr_filter is not None:
        q = """
        SELECT
            ri.id_item,
            ri.nr_chamado,
            ri.linha_nota,
            r.versao_release,
            r.data_liberacao,
            NULL::DOUBLE PRECISION AS score_semantico
        FROM release_itens ri
        JOIN releases r ON r.id_release = ri.id_release
        WHERE ri.nr_chamado = :nr
        ORDER BY r.data_liberacao DESC NULLS LAST, ri.id_item DESC
        LIMIT :lim
        """
        return pd.read_sql(text(q), engine, params=params)

    return pd.DataFrame()


def backfill_embeddings_release_itens(limite: int = 200) -> int:
    """Preenche embedding em linhas antigas (sem vetor). Retorna quantos registros atualizados."""
    try:
        from services.embedding_service import generate_embedding, get_embedding_dim
    except Exception:
        return 0

    dim = get_embedding_dim()
    engine = get_connection()
    try:
        with engine.connect() as c:
            rows = c.execute(
                text(
                    """
                    SELECT id_item, linha_nota FROM release_itens
                    WHERE embedding IS NULL
                      AND linha_nota IS NOT NULL
                      AND TRIM(linha_nota) <> ''
                    ORDER BY id_item DESC
                    LIMIT :lim
                    """
                ),
                {"lim": int(limite)},
            ).fetchall()
    except Exception:
        return 0

    atualizados = 0
    for id_item, linha in rows:
        texto = (linha or "")[:4000]
        emb = generate_embedding(texto)
        if not emb or len(emb) != dim:
            continue
        try:
            with engine.begin() as conn:
                res = conn.execute(
                    text(
                        """
                        UPDATE release_itens
                        SET embedding = CAST(:e AS vector)
                        WHERE id_item = :id AND embedding IS NULL
                        """
                    ),
                    {"e": _emb_to_sql(emb), "id": int(id_item)},
                )
                if res.rowcount:
                    atualizados += int(res.rowcount)
        except Exception:
            continue
    return atualizados
