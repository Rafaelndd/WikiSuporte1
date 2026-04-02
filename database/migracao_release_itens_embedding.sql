-- Embeddings dos itens de release para busca semântica (assunto da linha de nota).
-- Requer: CREATE EXTENSION IF NOT EXISTS vector;
-- Dimensão 768 = Gemini (padrão do projeto). Para EMBEDDING_MODEL=openai (1536),
-- altere o tipo da coluna após migrar: ALTER TABLE release_itens ALTER COLUMN embedding TYPE vector(1536);

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE release_itens ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE INDEX IF NOT EXISTS idx_release_itens_embedding
    ON release_itens
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

COMMENT ON COLUMN release_itens.embedding IS 'Embedding do texto limpo de linha_nota (busca semântica no app)';
