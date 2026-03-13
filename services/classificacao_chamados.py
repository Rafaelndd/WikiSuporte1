"""
Classificação semântica de chamados (Erro / Melhoria / Adequação Fiscal) via pgvector.
Requer: migracao_vector_chamados.sql aplicada e EMBEDDING_MODEL/GEMINI ou OPENAI no .env.
"""
import logging
from typing import Optional, Tuple

from sqlalchemy import text

from modules.database import get_connection
from services.embedding_service import (
    _texto_chamado,
    generate_embedding,
    get_embedding_dim,
)

logger = logging.getLogger(__name__)


def _engine():
    return get_connection()


def _popular_embeddings_categorias():
    """Preenche embedding das categorias na primeira vez."""
    engine = _engine()
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT id, nome, descricao FROM categorias_chamados WHERE embedding IS NULL"
            )
        ).fetchall()
    if not r:
        return
    for id_cat, nome, descricao in r:
        texto = f"{nome} {descricao or ''}".strip()
        emb = generate_embedding(texto)
        if not emb:
            continue
        emb_str = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
        with _engine().begin() as conn:
            conn.execute(
                text(
                    "UPDATE categorias_chamados SET embedding = :emb::vector WHERE id = :id"
                ),
                {"emb": emb_str, "id": id_cat},
            )
    logger.info("Embeddings das categorias preenchidos.")


def classificar_chamado(nr_chamado: int) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Para um chamado: gera embedding do assunto+motivo, salva, classifica por similaridade
    e atualiza categoria_ia.
    Retorna (sucesso, categoria, distância).
    """
    engine = _engine()
    # 1. Buscar chamado
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT nr_chamado, assunto_html, motivo_abertura_html
                FROM chamados_tecnuv WHERE nr_chamado = :nr
                """
            ),
            {"nr": nr_chamado},
        ).fetchone()
    if not row:
        return False, None, None

    texto = _texto_chamado(row[1], row[2])
    if not texto or texto == "Sem descrição":
        return False, None, None

    # 2. Gerar embedding
    emb = generate_embedding(texto)
    if not emb:
        logger.warning("Chamado %s: embedding não gerado.", nr_chamado)
        return False, None, None

    emb_str = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
    dim = get_embedding_dim()

    # 3. Salvar embedding no chamado
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE chamados_tecnuv
                    SET embedding = :emb::vector
                    WHERE nr_chamado = :nr
                    """
                ),
                {"emb": emb_str, "nr": nr_chamado},
            )
    except Exception as e:
        if "vector(" in str(e) and "does not match" in str(e).lower():
            logger.warning("Dimensão do embedding incompatível com a coluna. Execute a migração correta.")
        else:
            logger.exception("Erro ao salvar embedding do chamado %s: %s", nr_chamado, e)
        return False, None, None

    # 4. Garantir que categorias têm embedding
    _popular_embeddings_categorias()

    # 5. Classificação vetorial: categoria mais próxima (cosine distance)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT nome, (embedding <=> :emb::vector) AS dist
                FROM categorias_chamados
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :emb::vector
                LIMIT 1
                """
            ),
            {"emb": emb_str},
        ).fetchone()
    if not result:
        return False, None, None

    categoria, distancia = result[0], float(result[1])

    # 6. Atualizar chamado com categoria
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE chamados_tecnuv SET categoria_ia = :cat WHERE nr_chamado = :nr"
            ),
            {"cat": categoria, "nr": nr_chamado},
        )

    logger.info(
        "Chamado %s classificado: %s (distância %.4f)",
        nr_chamado,
        categoria,
        distancia,
    )
    return True, categoria, distancia
