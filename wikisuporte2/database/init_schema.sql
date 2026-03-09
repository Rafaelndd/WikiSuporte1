-- ============================================================
-- WikiSuporte 2.0 — Schema Completo do Banco de Dados
-- PostgreSQL 16+
-- ============================================================

-- Extensões
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- MÓDULO: USUÁRIOS / RBAC
-- ============================================================

CREATE TABLE IF NOT EXISTS setores (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL UNIQUE,
    descricao TEXT,
    setor_pai_id INTEGER REFERENCES setores(id) ON DELETE SET NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(50) NOT NULL UNIQUE,   -- ceo, gestor, analista, viewer
    descricao TEXT,
    nivel INTEGER NOT NULL DEFAULT 0,   -- maior = mais permissões
    ativo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    email VARCHAR(200) NOT NULL UNIQUE,
    senha_hash VARCHAR(255) NOT NULL,
    role_id INTEGER REFERENCES roles(id) ON DELETE SET NULL,
    setor_id INTEGER REFERENCES setores(id) ON DELETE SET NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW(),
    ultimo_login TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permissoes (
    id SERIAL PRIMARY KEY,
    modulo VARCHAR(100) NOT NULL,       -- tarefas, crm, suporte, dashboards
    acao VARCHAR(50) NOT NULL,          -- ler, criar, editar, deletar
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS role_permissoes (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permissao_id INTEGER NOT NULL REFERENCES permissoes(id) ON DELETE CASCADE,
    UNIQUE (role_id, permissao_id)
);

-- ============================================================
-- MÓDULO: TAREFAS (ClickUp-like)
-- ============================================================

CREATE TABLE IF NOT EXISTS espacos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) NOT NULL,
    descricao TEXT,
    cor VARCHAR(10),
    icone VARCHAR(50),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pastas (
    id SERIAL PRIMARY KEY,
    espaco_id INTEGER NOT NULL REFERENCES espacos(id) ON DELETE CASCADE,
    nome VARCHAR(150) NOT NULL,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS listas (
    id SERIAL PRIMARY KEY,
    pasta_id INTEGER NOT NULL REFERENCES pastas(id) ON DELETE CASCADE,
    nome VARCHAR(150) NOT NULL,
    descricao TEXT,
    cor VARCHAR(10),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS status_config (
    id SERIAL PRIMARY KEY,
    espaco_id INTEGER NOT NULL REFERENCES espacos(id) ON DELETE CASCADE,
    nome VARCHAR(100) NOT NULL,
    cor VARCHAR(10),
    ordem INTEGER NOT NULL DEFAULT 0,
    tipo VARCHAR(50) DEFAULT 'personalizado'
        CHECK (tipo IN ('nao_iniciado', 'ativo', 'concluido', 'cancelado', 'personalizado'))
);

CREATE TABLE IF NOT EXISTS tarefas (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(300) NOT NULL,
    descricao TEXT,
    status_id INTEGER REFERENCES status_config(id) ON DELETE SET NULL,
    prioridade VARCHAR(20) NOT NULL DEFAULT 'normal'
        CHECK (prioridade IN ('urgente', 'alta', 'normal', 'baixa')),
    data_inicio TIMESTAMP,
    data_vencimento TIMESTAMP,
    concluida BOOLEAN NOT NULL DEFAULT FALSE,
    tarefa_pai_id INTEGER REFERENCES tarefas(id) ON DELETE SET NULL,
    recorrente BOOLEAN NOT NULL DEFAULT FALSE,
    intervalo_recorrencia VARCHAR(50),
    criado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tarefa_responsaveis (
    id SERIAL PRIMARY KEY,
    tarefa_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    UNIQUE (tarefa_id, usuario_id)
);

CREATE TABLE IF NOT EXISTS tarefa_listas (
    id SERIAL PRIMARY KEY,
    tarefa_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    lista_id INTEGER NOT NULL REFERENCES listas(id) ON DELETE CASCADE,
    UNIQUE (tarefa_id, lista_id)
);

CREATE TABLE IF NOT EXISTS tarefa_dependencias (
    id SERIAL PRIMARY KEY,
    tarefa_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    depende_de_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    UNIQUE (tarefa_id, depende_de_id)
);

CREATE TABLE IF NOT EXISTS checklists (
    id SERIAL PRIMARY KEY,
    tarefa_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    titulo VARCHAR(200) NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS checklist_itens (
    id SERIAL PRIMARY KEY,
    checklist_id INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
    descricao VARCHAR(300) NOT NULL,
    concluido BOOLEAN NOT NULL DEFAULT FALSE,
    ordem INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tarefa_comentarios (
    id SERIAL PRIMARY KEY,
    tarefa_id INTEGER NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    conteudo TEXT NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS automacoes (
    id SERIAL PRIMARY KEY,
    espaco_id INTEGER NOT NULL REFERENCES espacos(id) ON DELETE CASCADE,
    nome VARCHAR(150) NOT NULL,
    gatilho VARCHAR(100) NOT NULL,
    condicao TEXT,
    acao TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- MÓDULO: CRM / TÉCNICO CONSULTOR
-- ============================================================

CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    razao_social VARCHAR(200) NOT NULL,
    nome_fantasia VARCHAR(200),
    cnpj VARCHAR(20) UNIQUE,
    email VARCHAR(200),
    telefone VARCHAR(30),
    cidade VARCHAR(100),
    estado CHAR(2),
    observacoes TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prospecções (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    analista_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'prospectando'
        CHECK (status IN ('prospectando', 'em_negociacao', 'convertido', 'perdido')),
    descricao TEXT,
    data_contato TIMESTAMP,
    proximo_contato TIMESTAMP,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    descricao TEXT,
    tipo VARCHAR(50),                   -- modulo, treinamento, servico
    preco NUMERIC(12, 2),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedidos_venda (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
    analista_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL DEFAULT 'rascunho'
        CHECK (status IN ('rascunho', 'enviado', 'aprovado', 'cancelado')),
    valor_total NUMERIC(12, 2),
    observacoes TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pedido_itens (
    id SERIAL PRIMARY KEY,
    pedido_id INTEGER NOT NULL REFERENCES pedidos_venda(id) ON DELETE CASCADE,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    quantidade INTEGER NOT NULL DEFAULT 1,
    preco_unitario NUMERIC(12, 2),
    desconto NUMERIC(5, 2) DEFAULT 0
);

-- ============================================================
-- MÓDULO: SUPORTE
-- ============================================================

CREATE TABLE IF NOT EXISTS atendimentos (
    id SERIAL PRIMARY KEY,
    analista_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    cliente_nome VARCHAR(200),
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    tipo VARCHAR(30) NOT NULL DEFAULT 'telefone'
        CHECK (tipo IN ('telefone', 'email', 'chat', 'presencial')),
    duracao_minutos INTEGER,
    descricao TEXT,
    resolucao TEXT,
    data_atendimento TIMESTAMP NOT NULL DEFAULT NOW(),
    importado BOOLEAN NOT NULL DEFAULT FALSE,
    fonte VARCHAR(50),                  -- multi360, goto, manual
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chamados (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(300) NOT NULL,
    descricao TEXT,
    cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    analista_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'aberto'
        CHECK (status IN ('aberto', 'em_andamento', 'aguardando_cliente', 'resolvido', 'fechado')),
    prioridade VARCHAR(20) NOT NULL DEFAULT 'normal',
    categoria VARCHAR(100),
    data_abertura TIMESTAMP NOT NULL DEFAULT NOW(),
    data_fechamento TIMESTAMP,
    sla_horas INTEGER,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plantoes (
    id SERIAL PRIMARY KEY,
    analista_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    data_inicio TIMESTAMP NOT NULL,
    data_fim TIMESTAMP,
    tipo VARCHAR(50),                   -- diurno, noturno, fim_de_semana
    observacoes TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS importacoes (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    tipo VARCHAR(50) NOT NULL,          -- multi360_csv, goto_api, chamados_bot
    nome_arquivo VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'processando', 'concluido', 'erro')),
    total_registros INTEGER DEFAULT 0,
    registros_importados INTEGER DEFAULT 0,
    registros_erro INTEGER DEFAULT 0,
    log_erros TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    concluido_em TIMESTAMP
);

-- ============================================================
-- MÓDULO: AUDITORIA
-- ============================================================

CREATE TABLE IF NOT EXISTS auditoria (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    metodo VARCHAR(10) NOT NULL,
    endpoint VARCHAR(300) NOT NULL,
    status_code INTEGER,
    ip_origem VARCHAR(50),
    dados_entrada TEXT,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES DE PERFORMANCE
-- ============================================================

-- Usuários
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);
CREATE INDEX IF NOT EXISTS idx_usuarios_role_id ON usuarios(role_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_setor_id ON usuarios(setor_id);

-- Tarefas
CREATE INDEX IF NOT EXISTS idx_tarefas_status_id ON tarefas(status_id);
CREATE INDEX IF NOT EXISTS idx_tarefas_tarefa_pai_id ON tarefas(tarefa_pai_id);
CREATE INDEX IF NOT EXISTS idx_tarefas_criado_por_id ON tarefas(criado_por_id);
CREATE INDEX IF NOT EXISTS idx_tarefa_responsaveis_tarefa_id ON tarefa_responsaveis(tarefa_id);
CREATE INDEX IF NOT EXISTS idx_tarefa_responsaveis_usuario_id ON tarefa_responsaveis(usuario_id);
CREATE INDEX IF NOT EXISTS idx_tarefa_listas_lista_id ON tarefa_listas(lista_id);
CREATE INDEX IF NOT EXISTS idx_tarefa_comentarios_tarefa_id ON tarefa_comentarios(tarefa_id);

-- CRM
CREATE INDEX IF NOT EXISTS idx_clientes_cnpj ON clientes(cnpj);
CREATE INDEX IF NOT EXISTS idx_prospecções_cliente_id ON prospecções(cliente_id);
CREATE INDEX IF NOT EXISTS idx_prospecções_analista_id ON prospecções(analista_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_venda_analista_id ON pedidos_venda(analista_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_venda_cliente_id ON pedidos_venda(cliente_id);

-- Suporte
CREATE INDEX IF NOT EXISTS idx_atendimentos_analista_id ON atendimentos(analista_id);
CREATE INDEX IF NOT EXISTS idx_atendimentos_data ON atendimentos(data_atendimento);
CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados(status);
CREATE INDEX IF NOT EXISTS idx_chamados_analista_id ON chamados(analista_id);
CREATE INDEX IF NOT EXISTS idx_plantoes_analista_id ON plantoes(analista_id);

-- Auditoria
CREATE INDEX IF NOT EXISTS idx_auditoria_usuario_id ON auditoria(usuario_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_criado_em ON auditoria(criado_em);
