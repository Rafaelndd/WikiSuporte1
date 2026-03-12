-- =================================================================================
-- PROJETO: WikiSuporte - Ciclos de Homologação
-- DESCRIÇÃO: Nova arquitetura para rastrear o ciclo de vida completo dos chamados
--            através de múltiplas releases, medindo retrabalho e qualidade.
-- =================================================================================

-- ---------------------------------------------------------------------------------
-- 1. Tabela de Domínio: Chamados (a essência do problema/funcionalidade)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chamados (
    id_chamado VARCHAR(50) PRIMARY KEY,
    assunto TEXT NOT NULL,
    modulo_sistema VARCHAR(100),
    data_primeiro_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- 2. Tabela de Domínio: Releases (pacote semanal de liberação)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS releases (
    id_release SERIAL PRIMARY KEY,
    versao_release VARCHAR(50) UNIQUE NOT NULL,
    data_liberacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- 3. Tabela Relacional: Ciclos de Homologação (qualidade e retrabalho auditados)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ciclos_homologacao (
    id_ciclo SERIAL PRIMARY KEY,
    id_chamado VARCHAR(50) NOT NULL REFERENCES chamados(id_chamado) ON DELETE CASCADE,
    id_release INTEGER NOT NULL REFERENCES releases(id_release) ON DELETE CASCADE,
    status_teste VARCHAR(20) DEFAULT 'Aguardando',
    motivo_reprovacao TEXT,
    data_teste TIMESTAMP,
    CONSTRAINT uk_chamado_release UNIQUE (id_chamado, id_release),
    CONSTRAINT chk_status_teste CHECK (status_teste IN ('Aguardando', 'Aprovado', 'Reprovado'))
);

-- ---------------------------------------------------------------------------------
-- 4. Índices para otimização
-- ---------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ciclos_status ON ciclos_homologacao(status_teste);
CREATE INDEX IF NOT EXISTS idx_ciclos_id_chamado ON ciclos_homologacao(id_chamado);
CREATE INDEX IF NOT EXISTS idx_ciclos_id_release ON ciclos_homologacao(id_release);
CREATE INDEX IF NOT EXISTS idx_chamados_modulo ON chamados(modulo_sistema);

-- ---------------------------------------------------------------------------------
-- 5. Comentários para documentação
-- ---------------------------------------------------------------------------------
COMMENT ON TABLE chamados IS 'Chamados de correção/evolução, independente do ciclo de release';
COMMENT ON TABLE releases IS 'Pacotes de liberação (versões) do sistema';
COMMENT ON TABLE ciclos_homologacao IS 'Vínculo N:N entre chamados e releases, com status de homologação';
