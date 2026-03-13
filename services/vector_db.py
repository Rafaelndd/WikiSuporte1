"""
Serviço: Banco Vetorial (pgvector) para RAG com Gemini.
- Utiliza a extensão pgvector no PostgreSQL existente para buscas por similaridade
  em manuais e wikis (base_conhecimento).
- Chunking de textos longos para não ultrapassar limite de contexto do Gemini.
Uso: criar_extensao_e_tabela(), indexar_base_conhecimento(), buscar_similares().
Não modifica arquivos originais do projeto.
Requisito: instalar extensão no Postgres: CREATE EXTENSION IF NOT EXISTS vector;
          e opcionalmente: pip install pgvector
"""
import os
import re
from typing import List, Optional, Tuple

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

try:
    from modules.database import get_connection
except ImportError:
    get_connection = None

# Dimensão padrão do embedding para Gemini.
# `gemini-embedding-001` aceita `output_dimensionality=768`, o que mantém
# compatibilidade com a estrutura vetorial usada no projeto.
EMBEDDING_DIM = 768
# Tabela de chunks vetorizados
TABELA_EMBEDDINGS = "base_conhecimento_embeddings"
# Tamanho aproximado de chunk em caracteres (≈ 300–600 tokens)
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150


def _engine():
    if get_connection is None:
        raise RuntimeError("modules.database.get_connection não disponível.")
    return get_connection()


def criar_extensao_e_tabela(dimensao: int = EMBEDDING_DIM) -> bool:
    """
    Cria a extensão pgvector e a tabela de embeddings no PostgreSQL.
    Execute uma vez (ex.: script de migração ou primeiro uso).
    Retorna True se conseguiu criar ou a tabela já existir.
    """
    engine = _engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception:
        pass  # Extensão pode já existir ou não estar instalada

    # Tabela: id do conhecimento, índice do chunk, texto do chunk, vetor
    sql_create = f"""
        CREATE TABLE IF NOT EXISTS {TABELA_EMBEDDINGS} (
            id BIGSERIAL PRIMARY KEY,
            id_conhecimento INTEGER NOT NULL REFERENCES base_conhecimento(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            texto_chunk TEXT NOT NULL,
            embedding vector({dimensao}),
            titulo VARCHAR(255),
            origem VARCHAR(50),
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id_conhecimento, chunk_index)
        );
        CREATE INDEX IF NOT EXISTS idx_{TABELA_EMBEDDINGS}_embedding
        ON {TABELA_EMBEDDINGS} USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """
    try:
        with engine.connect() as conn:
            for stmt in sql_create.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.commit()
        return True
    except Exception as e:
        # ivfflat pode falhar se não houver dados; criar índice depois
        try:
            with engine.connect() as conn:
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS {TABELA_EMBEDDINGS} (
                        id BIGSERIAL PRIMARY KEY,
                        id_conhecimento INTEGER NOT NULL REFERENCES base_conhecimento(id) ON DELETE CASCADE,
                        chunk_index INTEGER NOT NULL,
                        texto_chunk TEXT NOT NULL,
                        embedding vector({dimensao}),
                        titulo VARCHAR(255),
                        origem VARCHAR(50),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(id_conhecimento, chunk_index)
                    )
                """))
                conn.commit()
        except Exception:
            pass
        return False


def _chunk_texto(texto: str, tamanho: int = CHUNK_SIZE, sobreposicao: int = CHUNK_OVERLAP) -> List[str]:
    """Divide o texto em chunks por tamanho, com sobreposição, respeitando parágrafos quando possível."""
    if not texto or len(texto) <= tamanho:
        return [texto] if texto else []
    chunks = []
    inicio = 0
    while inicio < len(texto):
        fim = inicio + tamanho
        if fim < len(texto):
            # Tenta quebrar em fim de parágrafo ou linha
            trecho = texto[inicio:fim]
            for sep in ("\n\n", "\n", ". "):
                idx = trecho.rfind(sep)
                if idx != -1:
                    fim = inicio + idx + len(sep)
                    break
        chunks.append(texto[inicio:fim].strip())
        inicio = fim - sobreposicao
        if inicio >= len(texto):
            break
    return chunks


def gerar_embedding_gemini(texto: str) -> Optional[List[float]]:
    """
    Gera embedding usando a API do Gemini (via google-genai).
    Configure GEMINI_API_KEY no .env.
    Retorna lista de floats ou None em caso de falha.
    """
    try:
        from google import genai
        from google.genai import types
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None

        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(
            model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            contents=texto,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBEDDING_DIM,
            ),
        )
        embeddings = getattr(result, "embeddings", None) or []
        if embeddings and getattr(embeddings[0], "values", None):
            return list(embeddings[0].values)
    except Exception as e:
        print(f"[vector_db] Falha ao gerar embedding Gemini: {e}")
    return None


def _embedding_placeholder(texto: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Placeholder quando a API de embedding não está disponível (não usar em produção para RAG)."""
    import hashlib
    h = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    # Gera vetor determinístico de dimensão fixa (apenas para testes)
    return [((int(h[i : i + 2], 16) / 255.0) - 0.5) for i in range(0, min(dim * 2, len(h) - 1), 2)][:dim]


def indexar_documento(
    id_conhecimento: int,
    titulo: str,
    origem: str,
    conteudo: str,
    usar_gemini: bool = True,
) -> int:
    """
    Quebra o conteúdo em chunks, gera embeddings e insere na tabela de vetores.
    Retorna o número de chunks indexados.
    """
    criar_extensao_e_tabela()
    chunks = _chunk_texto(conteudo)
    if not chunks:
        return 0
    engine = _engine()
    # Remove chunks antigos deste documento
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {TABELA_EMBEDDINGS} WHERE id_conhecimento = :id"),
            {"id": id_conhecimento}
        )
    count = 0
    for i, chunk in enumerate(chunks):
        emb = gerar_embedding_gemini(chunk) if usar_gemini else None
        if emb is None:
            emb = _embedding_placeholder(chunk)
        # Formato pgvector: lista como string '[0.1, 0.2, ...]'
        emb_str = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
        with engine.begin() as conn:
            conn.execute(
                text(f"""
                    INSERT INTO {TABELA_EMBEDDINGS}
                    (id_conhecimento, chunk_index, texto_chunk, embedding, titulo, origem)
                    VALUES (:id_c, :idx, :txt, CAST(:emb AS vector), :tit, :orig)
                    ON CONFLICT (id_conhecimento, chunk_index) DO UPDATE
                    SET texto_chunk = EXCLUDED.texto_chunk, embedding = EXCLUDED.embedding
                """),
                {
                    "id_c": id_conhecimento,
                    "idx": i,
                    "txt": chunk[:10000],
                    "emb": emb_str,
                    "tit": titulo[:255],
                    "orig": origem[:50],
                }
            )
        count += 1
    return count


def indexar_base_conhecimento(origens: Optional[List[str]] = None, limite: int = 500) -> int:
    """
    Percorre base_conhecimento (status APROVADO) e indexa em vetores.
    origens: ex. ['WIKI_HELPDESK', 'MANUAL_HELPDESK'] ou None para todas.
    Retorna total de chunks indexados.
    """
    engine = _engine()
    with engine.connect() as conn:
        q = """
            SELECT id, titulo, origem, conteudo
            FROM base_conhecimento
            WHERE status = 'APROVADO' AND conteudo IS NOT NULL AND LENGTH(TRIM(conteudo)) > 0
        """
        params = {}
        if origens:
            q += " AND origem = ANY(:origens)"
            params["origens"] = origens
        q += " ORDER BY id LIMIT :lim"
        params["lim"] = limite
        rows = conn.execute(text(q), params).fetchall()
    total = 0
    for row in rows:
        total += indexar_documento(row[0], row[1], row[2], row[3] or "", usar_gemini=True)
    return total


def buscar_similares(
    query: str,
    top_k: int = 5,
    origens: Optional[List[str]] = None,
    usar_embedding_query: bool = True,
) -> List[dict]:
    """
    Busca os chunks mais similares à query (para montar contexto RAG para o Gemini).
    Se usar_embedding_query=True, gera embedding da query; senão usa busca full-text como fallback.
    Retorna lista de { id_conhecimento, titulo, origem, texto_chunk, similaridade }.
    """
    criar_extensao_e_tabela()
    engine = _engine()
    filtro_origem = ""
    params = {"top_k": top_k}
    if origens:
        filtro_origem = " AND origem = ANY(:origens)"
        params["origens"] = origens

    if usar_embedding_query:
        emb = gerar_embedding_gemini(query)
        if emb is None:
            emb = _embedding_placeholder(query)
        emb_str = "[" + ",".join(str(round(x, 6)) for x in emb) + "]"
        params["query_emb"] = emb_str
        sql = f"""
            SELECT id_conhecimento, titulo, origem, texto_chunk,
                   1 - (embedding <=> CAST(:query_emb AS vector)) as similaridade
            FROM {TABELA_EMBEDDINGS}
            WHERE embedding IS NOT NULL {filtro_origem}
            ORDER BY embedding <=> CAST(:query_emb AS vector)
            LIMIT :top_k
        """
    else:
        # Fallback: busca por texto (LIKE) sem vetor
        params["like"] = f"%{query[:100]}%"
        sql = f"""
            SELECT id_conhecimento, titulo, origem, texto_chunk, 0.5::float as similaridade
            FROM {TABELA_EMBEDDINGS}
            WHERE texto_chunk ILIKE :like
        """ + (filtro_origem if origens else "") + """
            LIMIT :top_k
        """
        if origens:
            params["origens"] = origens
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
    except Exception:
        return []
    return [
        {
            "id_conhecimento": r[0],
            "titulo": r[1],
            "origem": r[2],
            "texto_chunk": r[3],
            "similaridade": float(r[4]) if r[4] is not None else 0.0,
        }
        for r in rows
    ]


def montar_contexto_rag(query: str, top_k: int = 5, origens: Optional[List[str]] = None) -> str:
    """
    Retorna uma única string de contexto para enviar ao Gemini (RAG).
    Concatena os textos dos chunks mais similares.
    """
    resultados = buscar_similares(query, top_k=top_k, origens=origens)
    partes = []
    for r in resultados:
        partes.append(f"[{r['titulo']}]\n{r['texto_chunk']}")
    return "\n\n---\n\n".join(partes) if partes else ""
