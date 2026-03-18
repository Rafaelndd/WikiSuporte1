-- WikiSuporte | Otimizacao de indices PostgreSQL
-- Execute em janela de manutencao. Preferencialmente com usuario com privilegios de DDL.
-- Recomendado: rodar no psql com autocommit (CREATE INDEX CONCURRENTLY nao pode ficar dentro de transacao).

-- 1) Habilita trigram para acelerar ILIKE/LIKE em texto livre
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2) Base de conhecimento: filtros mais usados
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bc_origem_status_criado
ON base_conhecimento (origem, status, criado_em DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bc_autor_origem_criado
ON base_conhecimento (id_analista_autor, origem, criado_em DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bc_origem_categoria_status
ON base_conhecimento (origem, categoria, status);

-- 3) Busca textual rapida (ILIKE / LIKE por titulo e conteudo)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bc_titulo_trgm
ON base_conhecimento USING GIN (titulo gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bc_conteudo_trgm
ON base_conhecimento USING GIN (conteudo gin_trgm_ops);

-- 4) Historico de buscas: ultimos registros e agrupamento por pergunta
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hist_criado_desc
ON historico_buscas_psy (criado_em DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_hist_lower_pergunta
ON historico_buscas_psy (lower(pergunta));

-- 5) Tabela de votos: existe/insere/remove por usuario e item
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_votos_conhecimento_analista
ON base_conhecimento_votos (id_conhecimento, id_analista_votante);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_votos_analista
ON base_conhecimento_votos (id_analista_votante);

-- 6) Atualiza estatisticas para o otimizador
ANALYZE base_conhecimento;
ANALYZE historico_buscas_psy;
ANALYZE base_conhecimento_votos;
