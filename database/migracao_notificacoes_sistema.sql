-- Sistema de notificações e bloqueios de versão (idempotente)

CREATE TABLE IF NOT EXISTS notificacoes_sistema (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL, -- comunicado, aviso, erro_critico, versao_bloqueada
    titulo VARCHAR(100),
    mensagem TEXT NOT NULL,
    autor VARCHAR(50),
    data_criacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    data_expiracao TIMESTAMPTZ,
    ativo BOOLEAN DEFAULT TRUE,
    target_role VARCHAR(20) DEFAULT 'todos' -- todos, tecnico, supervisor, coordenador
);

CREATE TABLE IF NOT EXISTS bloqueio_versoes (
    id SERIAL PRIMARY KEY,
    modulo_nome VARCHAR(100) NOT NULL,
    versao_problematica VARCHAR(50) NOT NULL,
    motivo TEXT,
    data_bloqueio TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    resolvido BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_notificacoes_ativas
    ON notificacoes_sistema (ativo, data_expiracao, data_criacao);

CREATE INDEX IF NOT EXISTS idx_notificacoes_tipo
    ON notificacoes_sistema (tipo, ativo);

CREATE INDEX IF NOT EXISTS idx_bloqueio_versoes_resolvido
    ON bloqueio_versoes (resolvido, data_bloqueio);
