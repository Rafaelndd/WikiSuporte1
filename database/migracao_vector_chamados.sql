-- =================================================================================
-- Migração: Suporte a vetores (pgvector) para classificação semântica de chamados
-- e base de conhecimento.
-- Execute: psql -U usuario -d banco -f database/migracao_vector_chamados.sql
-- Requer: CREATE EXTENSION vector; (pgvector instalado no PostgreSQL)
-- =================================================================================

-- Extensão pgvector (se disponível)
CREATE EXTENSION IF NOT EXISTS vector;

-- Dimensão 768 = Gemini text-embedding-004 (reutiliza camada IA do projeto)
-- Para OpenAI 1536, altere para vector(1536) e configure EMBEDDING_MODEL=openai
-- ---------------------------------------------------------------------------------
-- Chamados: embedding e categoria IA
-- ---------------------------------------------------------------------------------
ALTER TABLE chamados_tecnuv
ADD COLUMN IF NOT EXISTS embedding vector(768);

ALTER TABLE chamados_tecnuv
ADD COLUMN IF NOT EXISTS categoria_ia TEXT;

-- Índice vetorial para busca por similaridade (cosine)
CREATE INDEX IF NOT EXISTS idx_chamados_tecnuv_embedding
ON chamados_tecnuv
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- ---------------------------------------------------------------------------------
-- Categorias de classificação (descrições para gerar embeddings)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias_chamados (
    id SERIAL PRIMARY KEY,
    nome TEXT UNIQUE NOT NULL,
    descricao TEXT,
    embedding vector(768)
);

INSERT INTO categorias_chamados (nome, descricao)
VALUES
    ('Erro', 'falha, bug, problema no sistema, algo que não funciona'),
    ('Melhoria', 'sugestão, melhoria, nova funcionalidade'),
    ('Adequação Fiscal', 'nota fiscal, imposto, tributação, legislação fiscal')
ON CONFLICT (nome) DO NOTHING;

-- Índice para categorias (opcional, poucos registros)
CREATE INDEX IF NOT EXISTS idx_categorias_chamados_embedding
ON categorias_chamados
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 1);

-- ---------------------------------------------------------------------------------
-- Base de conhecimento: tabela de chunks vetorizados (RAG)
-- Compatível com services/vector_db.py (dimensão 768 = Gemini)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS base_conhecimento_embeddings (
    id BIGSERIAL PRIMARY KEY,
    id_conhecimento INTEGER NOT NULL REFERENCES base_conhecimento(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    texto_chunk TEXT NOT NULL,
    embedding vector(768),
    titulo VARCHAR(255),
    origem VARCHAR(50),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_conhecimento, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_base_conhecimento_embeddings_embedding
ON base_conhecimento_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
