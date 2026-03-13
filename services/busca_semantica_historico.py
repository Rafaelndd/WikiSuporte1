"""
Registro e consulta semântica de buscas (histórico Psy / Wiki / Manual).
Agrupa perguntas parecidas no mesmo tópico para ranking e avisos ao usuário.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

# Similaridade mínima (cosseno) para considerar o mesmo assunto
SIMILARIDADE_MIN = 0.82
# Máximo de caracteres no rótulo do tópico
LABEL_MAX = 280


def _limpar_prefixo(pergunta: str) -> str:
    s = (pergunta or "").strip()
    s = re.sub(r"^\[(WIKI|MANUAL)\]\s*", "", s, flags=re.I)
    return s.strip() or pergunta or ""


def _emb_to_sql(emb: List[float]) -> str:
    return "[" + ",".join(str(round(x, 8)) for x in emb) + "]"


def encontrar_topico_similiar(
    conn: Any, embedding_sql: str, origem_tag: str
) -> Optional[Tuple[int, float]]:
    """Retorna (id_topico, similaridade) se houver vizinho acima do limiar."""
    row = conn.execute(
        text(
            """
            SELECT id, 1 - (embedding <=> CAST(:emb AS vector)) AS sim
            FROM busca_topicos
            WHERE origem_tag = :tag AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT 1
            """
        ),
        {"emb": embedding_sql, "tag": origem_tag},
    ).fetchone()
    if not row:
        return None
    tid, sim = int(row[0]), float(row[1])
    if sim >= SIMILARIDADE_MIN:
        return (tid, sim)
    return None


def registrar_busca_com_topico(
    engine: Any,
    usuario_id: Optional[int],
    pergunta: str,
    resposta_ia: str,
    origem_tag: str = "ASSISTENTE",
    tokens_prompt: int = 0,
    tokens_resposta: int = 0,
    total_tokens: int = 0,
) -> Optional[int]:
    """
    Gera embedding, associa a um tópico existente ou cria novo, insere em historico_buscas_psy.
    Retorna id_topico ou None se embedding falhar (ainda insere histórico sem tópico).
    """
    from services.embedding_service import generate_embedding

    clean = _limpar_prefixo(pergunta)[:4000]
    emb = generate_embedding(clean) if clean else None
    topic_id: Optional[int] = None

    with engine.begin() as conn:
        if emb and len(emb) >= 64:
            emb_sql = _emb_to_sql(emb)
            found = encontrar_topico_similiar(conn, emb_sql, origem_tag)
            if found:
                topic_id = found[0]
                conn.execute(
                    text(
                        "UPDATE busca_topicos SET total_buscas = total_buscas + 1, atualizado_em = CURRENT_TIMESTAMP WHERE id = :id"
                    ),
                    {"id": topic_id},
                )
            else:
                label = clean[:LABEL_MAX] if len(clean) > 80 else clean or pergunta[:LABEL_MAX]
                r = conn.execute(
                    text(
                        """
                        INSERT INTO busca_topicos (label, embedding, origem_tag, total_buscas)
                        VALUES (:label, CAST(:emb AS vector), :tag, 1)
                        RETURNING id
                        """
                    ),
                    {"label": label, "emb": emb_sql, "tag": origem_tag},
                ).fetchone()
                topic_id = int(r[0]) if r else None

        conn.execute(
            text(
                """
                INSERT INTO historico_buscas_psy
                (usuario_id, pergunta, resposta_ia, tokens_prompt, tokens_resposta, total_tokens, id_topico)
                VALUES (:u, :p, :r, :tp, :tr, :tt, :tid)
                """
            ),
            {
                "u": usuario_id,
                "p": pergunta.strip()[:2000],
                "r": (resposta_ia or "")[:65535],
                "tp": tokens_prompt,
                "tr": tokens_resposta,
                "tt": total_tokens,
                "tid": topic_id,
            },
        )
    return topic_id


def listar_buscas_mesmo_assunto(
    engine: Any,
    pergunta: str,
    usuario_id: Optional[int],
    origem_tag: str = "ASSISTENTE",
    limite: int = 8,
) -> List[Dict[str, Any]]:
    """
    Para o Assistente: avisar quem já buscou assunto semelhante (mesmo tópico).
    """
    from services.embedding_service import generate_embedding

    clean = _limpar_prefixo(pergunta)[:4000]
    emb = generate_embedding(clean) if clean else None
    if not emb or len(emb) < 64:
        return []

    emb_sql = _emb_to_sql(emb)
    out: List[Dict[str, Any]] = []
    with engine.connect() as conn:
        found = encontrar_topico_similiar(conn, emb_sql, origem_tag)
        if not found:
            return []
        tid = found[0]
        rows = conn.execute(
            text(
                """
                SELECT h.pergunta, u.nome, h.criado_em,
                       to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') AS quando
                FROM historico_buscas_psy h
                LEFT JOIN usuarios u ON h.usuario_id = u.id
                WHERE h.id_topico = :tid
                ORDER BY h.criado_em DESC
                LIMIT :lim
                """
            ),
            {"tid": tid, "lim": limite},
        ).fetchall()
        for r in rows:
            out.append(
                {
                    "pergunta": r[0],
                    "nome": r[1] or "Equipe",
                    "criado_em": r[2],
                    "quando": r[3],
                    "outro": usuario_id is not None and r[1] and True,
                }
            )
    return out


def ranking_topicos_agregado(
    engine: Any, origem_tag: Optional[str] = None, limite: int = 10
) -> List[Tuple[str, int]]:
    """Assunto canônico + total de buscas (sem duplicar variações de texto)."""
    with engine.connect() as conn:
        if origem_tag:
            q = text(
                """
                SELECT label, total_buscas
                FROM busca_topicos
                WHERE origem_tag = :tag AND total_buscas > 0
                ORDER BY total_buscas DESC, atualizado_em DESC
                LIMIT :lim
                """
            )
            rows = conn.execute(q, {"tag": origem_tag, "lim": limite}).fetchall()
        else:
            q = text(
                """
                SELECT label, total_buscas
                FROM busca_topicos
                WHERE total_buscas > 0
                ORDER BY total_buscas DESC, atualizado_em DESC
                LIMIT :lim
                """
            )
            rows = conn.execute(q, {"lim": limite}).fetchall()
    return [(r[0], int(r[1])) for r in rows]


def historico_por_topico_recente(engine: Any, limite_topicos: int = 20) -> List[Dict[str, Any]]:
    """Última busca por tópico (evita 15 linhas duplicadas do mesmo assunto)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ON (COALESCE(h.id_topico, -h.id))
                    h.id_topico,
                    t.label AS assunto_canonico,
                    h.pergunta,
                    h.resposta_ia,
                    u.nome,
                    to_char(h.criado_em, 'DD/MM/YYYY HH24:MI') AS quando,
                    h.criado_em
                FROM historico_buscas_psy h
                LEFT JOIN busca_topicos t ON t.id = h.id_topico
                LEFT JOIN usuarios u ON u.id = h.usuario_id
                ORDER BY COALESCE(h.id_topico, -h.id), h.criado_em DESC
                """
            )
        ).fetchall()
    # DISTINCT ON (topico) já pega o mais recente por tópico; ordenar global por data
    lst = []
    for r in rows:
        lst.append(
            {
                "id_topico": r[0],
                "assunto": r[1] or r[2],
                "pergunta": r[2],
                "resposta_ia": r[3],
                "nome": r[4] or "Equipe",
                "quando": r[5],
                "criado_em": r[6],
            }
        )
    lst.sort(key=lambda x: x["criado_em"] or "", reverse=True)
    return lst[:limite_topicos]
