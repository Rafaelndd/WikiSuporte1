-- Migração: registro diário de atendimentos + normalização mínima de clientes
-- Execução idempotente (pode rodar mais de uma vez).

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE IF EXISTS clientes_crm
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE IF EXISTS clientes_telefones
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS data_cadastro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE IF EXISTS clientes_vinculados_chamado
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS clientes_alias (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
    nome_variacao VARCHAR(255) NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE IF EXISTS clientes_alias
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE IF NOT EXISTS clientes_contatos (
    id SERIAL PRIMARY KEY,
    id_cliente INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
    nome_contato VARCHAR(255),
    nome_fantasia VARCHAR(255),
    telefone_chave VARCHAR(50),
    email_chave VARCHAR(255),
    observacoes TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE IF EXISTS clientes_contatos
    ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS nome_contato VARCHAR(255),
    ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_crm_cnpj_not_null
    ON clientes_crm(cnpj)
    WHERE cnpj IS NOT NULL AND cnpj <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_cliente_telefone
    ON clientes_telefones(id_cliente, numero)
    WHERE numero IS NOT NULL AND numero <> '';

CREATE UNIQUE INDEX IF NOT EXISTS ux_clientes_alias_cliente_nome
    ON clientes_alias(cliente_id, lower(nome_variacao));

CREATE TABLE IF NOT EXISTS atendimentos_registrados (
    id_atendimento BIGSERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista VARCHAR(150),
    cliente_id INTEGER NOT NULL REFERENCES clientes_crm(id_cliente) ON DELETE RESTRICT,
    contato_id INTEGER REFERENCES clientes_contatos(id) ON DELETE SET NULL,
    telefone_id INTEGER REFERENCES clientes_telefones(id_telefone) ON DELETE SET NULL,
    setor VARCHAR(40) NOT NULL CHECK (setor IN ('Suporte Geral', 'TEF')),
    categoria VARCHAR(255) NOT NULL,
    criticidade VARCHAR(20) NOT NULL CHECK (criticidade IN ('Baixa', 'Média', 'Alta', 'Crítica')),
    canal VARCHAR(100) NOT NULL,
    protocolo VARCHAR(120),
    data_atendimento TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duracao_min INTEGER,
    motivo TEXT NOT NULL,
    solucao TEXT,
    resolvido BOOLEAN NOT NULL DEFAULT FALSE,
    abriu_chamado BOOLEAN NOT NULL DEFAULT FALSE,
    nr_chamado VARCHAR(50),
    origem_registro VARCHAR(30) NOT NULL DEFAULT 'MANUAL',
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS atendimento_anexos (
    id_anexo BIGSERIAL PRIMARY KEY,
    atendimento_id BIGINT NOT NULL REFERENCES atendimentos_registrados(id_atendimento) ON DELETE CASCADE,
    nome_arquivo VARCHAR(512) NOT NULL,
    caminho_arquivo VARCHAR(1200) NOT NULL,
    mime_type VARCHAR(255),
    tamanho_bytes BIGINT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS atendimentos_embeddings (
    id BIGSERIAL PRIMARY KEY,
    atendimento_id BIGINT UNIQUE NOT NULL REFERENCES atendimentos_registrados(id_atendimento) ON DELETE CASCADE,
    resumo_busca TEXT NOT NULL,
    embedding vector(768),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_atendimentos_data ON atendimentos_registrados(data_atendimento);
CREATE INDEX IF NOT EXISTS idx_atendimentos_cliente ON atendimentos_registrados(cliente_id);
CREATE INDEX IF NOT EXISTS idx_atendimentos_usuario ON atendimentos_registrados(usuario_id);
CREATE INDEX IF NOT EXISTS idx_atendimentos_setor ON atendimentos_registrados(setor);
CREATE INDEX IF NOT EXISTS idx_atendimentos_canal ON atendimentos_registrados(canal);
CREATE INDEX IF NOT EXISTS idx_atend_embeddings_vec
    ON atendimentos_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
