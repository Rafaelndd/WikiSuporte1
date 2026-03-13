-- Tópicos semânticos para agregar buscas parecidas (certificado digital, instalação, etc.)
-- e ranking único por assunto. Requer: CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS busca_topicos (
    id SERIAL PRIMARY KEY,
    label VARCHAR(500) NOT NULL,
    embedding vector(768),
    origem_tag VARCHAR(32) NOT NULL DEFAULT 'ASSISTENTE',
    total_buscas INTEGER NOT NULL DEFAULT 0,
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_busca_topicos_origem ON busca_topicos(origem_tag);
-- Índice vetorial (opcional, após popular tópicos): CREATE INDEX ON busca_topicos USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

ALTER TABLE historico_buscas_psy
    ADD COLUMN IF NOT EXISTS id_topico INTEGER REFERENCES busca_topicos(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_historico_id_topico ON historico_buscas_psy(id_topico);
