"""
Módulo de acesso a dados para Ciclos de Homologação.
Gerencia chamados, releases e ciclos de teste (aprovação/reprovação).
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection

# Pasta para salvar arquivos de releases (relativa à raiz do projeto)
PASTA_RELEASES = "releases_tecnuv"


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
            linhas_por_chamado.append((match, clean[:4000]))

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
                    conn.execute(
                        text(
                            """
                            INSERT INTO release_itens
                            (id_release, nr_chamado, linha_nota, versao, titulo_release, autor, origem)
                            VALUES (:idr, :nr, :linha, :ver, :tit, :autor, :orig)
                            ON CONFLICT (id_release, nr_chamado, linha_nota) DO NOTHING
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
