-- =================================================================================
-- PROJETO: WikiSuporte / Oráculo ERP (Psy)
-- AUTOR: Rafael Duarte Nascimento
-- DESCRIÇÃO: Script Oficial de Inicialização e Estrutura do Banco de Dados PostgreSQL.
-- VERSÃO: 2.0 (Organizada)
-- =================================================================================

-- =================================================================================
-- 1. EXTENSÕES GLOBAIS
-- =================================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =================================================================================
-- 2. FUNÇÕES E GATILHOS (TRIGGERS)
-- =================================================================================

-- Função para atualizar o campo 'atualizado_em' automaticamente em qualquer tabela.
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

-- =================================================================================
-- 3. ESTRUTURA DE TABELAS
-- =================================================================================

-- ---------------------------------------------------------------------------------
-- Seção 3.1: Infraestrutura e Autenticação
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) UNIQUE NOT NULL,
    email VARCHAR(150) UNIQUE,
    perfil VARCHAR(50) NOT NULL,
    ramal VARCHAR(20),
    password_hash VARCHAR(255),
    ativo BOOLEAN DEFAULT TRUE,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuracoes_robo (
    chave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    descricao TEXT,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 3.2: Dados de Atendimento (GoTo, Multi360)
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS atendimentos_goto (
    id_conversa VARCHAR(255) PRIMARY KEY,
    data_chamada TIMESTAMP,
    duracao_ms BIGINT,
    direcao VARCHAR(50),
    resultado VARCHAR(100),
    telefone_hash VARCHAR(256),
    telefone_origem VARCHAR(50),
    participantes TEXT,
    gravado VARCHAR(20),
    data_importacao TIMESTAMP,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS atendimentos_multi360 (
    protocolo BIGINT PRIMARY KEY,
    origem VARCHAR(100),
    status VARCHAR(100),
    atendente VARCHAR(150),
    departamento VARCHAR(150),
    nome_contato VARCHAR(255),
    telefone_hash VARCHAR(256),
    numero_telefone VARCHAR(50),
    data_inicio TIMESTAMP,
    data_finalizacao TIMESTAMP,
    data_ultima_mensagem TIMESTAMP,
    avaliacao INTEGER,
    data_importacao TIMESTAMP,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

-- ---------------------------------------------------------------------------------
-- Seção 3.3: Dados do Fornecedor (Tecnuv)
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chamados_tecnuv (
    nr_chamado INTEGER PRIMARY KEY,
    cliente_nome VARCHAR(255),
    ticket_vinculado VARCHAR(50),
    versao_sistema VARCHAR(50),
    assunto_html TEXT,
    motivo_abertura_html TEXT,
    atendente_tecnuv VARCHAR(100),
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100),
    setor VARCHAR(100),
    status_atual VARCHAR(100) NOT NULL,
    situacao VARCHAR(100),
    prioridade VARCHAR(50),
    data_abertura TIMESTAMP,
    ultima_alteracao_tecnuv TIMESTAMP,
    assunto_encerramento TEXT,
    data_encerramento TIMESTAMP,
    previsao_conclusao DATE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS releases_tecnuv (
    id_release SERIAL PRIMARY KEY,
    titulo_versao VARCHAR(255) NOT NULL,
    autor_data VARCHAR(255),
    texto_completo TEXT,
    -- ATENÇÃO: A coluna abaixo restringe 1 release a 1 chamado, o que pode não ser o ideal.
    -- A boa prática é usar a tabela 'chamados_corrigidos_releases' como ponte.
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado) ON DELETE SET NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela Ponte: Múltos chamados podem ser corrigidos em múltiplos releases.
CREATE TABLE IF NOT EXISTS chamados_corrigidos_releases (
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    id_release INTEGER NOT NULL REFERENCES releases_tecnuv(id_release) ON DELETE CASCADE,
    PRIMARY KEY (nr_chamado, id_release)
);

-- ---------------------------------------------------------------------------------
-- Seção 3.4: Operação Interna EPSY
-- ---------------------------------------------------------------------------------

DROP TABLE IF EXISTS tickets_epsy CASCADE;
CREATE TABLE tickets_epsy (
    nr_ticket INTEGER PRIMARY KEY,
    cliente_nome VARCHAR(255),
    assunto TEXT,
    data_abertura TIMESTAMP,
    nome_analista_epsy VARCHAR(100),
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    status_atual VARCHAR(100) NOT NULL,
    chamado_vinculado INTEGER,
    tempo_aberto_str VARCHAR(100),
    avaliacao VARCHAR(50),
    data_ultima_interacao TIMESTAMP,
    ultima_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plantoes_epsy (
    id_plantao SERIAL PRIMARY KEY,
    nome_analista_epsy VARCHAR(255) NOT NULL,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    data_hora_entrada TIMESTAMP,
    data_hora_saida TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 3.5: Base de Conhecimento (Motor da IA)
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS base_conhecimento (
    id SERIAL PRIMARY KEY,
    nr_documento INTEGER,
    origem VARCHAR(50) NOT NULL,
    titulo VARCHAR(255) NOT NULL,
    categoria VARCHAR(100),
    subcategoria VARCHAR(100),
    conteudo TEXT NOT NULL,
    caminho_anexo VARCHAR(512),
    motivo_rejeicao TEXT,
    id_analista_autor INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    status VARCHAR(50) DEFAULT 'APROVADO',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_doc_origem UNIQUE (origem, nr_documento)
);

CREATE TABLE IF NOT EXISTS historico_buscas_psy (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    pergunta TEXT NOT NULL,
    resposta_ia TEXT,
    tokens_prompt INTEGER,
    tokens_resposta INTEGER,
    total_tokens INTEGER,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 3.6: CRM e Vínculos (Com LGPD)
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clientes_crm (
    id_cliente SERIAL PRIMARY KEY,
    razao_social VARCHAR(255),
    cnpj_criptografado BYTEA,
    email_criptografado BYTEA,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS clientes_telefones (
    id_telefone SERIAL PRIMARY KEY,
    id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
    numero_criptografado BYTEA,
    origem_dado VARCHAR(50)
);

DROP TABLE IF EXISTS clientes_vinculados_chamado CASCADE;
CREATE TABLE clientes_vinculados_chamado (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    nome_cliente VARCHAR(255) NOT NULL,
    cnpj_cliente VARCHAR(25),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 3.7: Históricos e Auditoria
-- ---------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS historico_transicao_status (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

DROP TABLE IF EXISTS historico_transicao_tickets CASCADE;
CREATE TABLE historico_transicao_tickets (
    id SERIAL PRIMARY KEY,
    nr_ticket INTEGER NOT NULL REFERENCES tickets_epsy(nr_ticket) ON DELETE CASCADE,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_interacoes (
    id_interacao SERIAL PRIMARY KEY,
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    data_interacao TIMESTAMP,
    descricao_texto TEXT,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

DROP TABLE IF EXISTS cobrancas_chamados CASCADE;
CREATE TABLE cobrancas_chamados (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    data_cobranca TIMESTAMP,
    analista_epsy VARCHAR(100),
    cliente_solicitante VARCHAR(255),
    texto_bruto_cobranca TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs_auditoria_sistema (
    id_log SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    acao VARCHAR(100),
    detalhe TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS logs_auditoria_dados_tabelas (
    id_log SERIAL PRIMARY KEY,
    tabela_afetada VARCHAR(100),
    operacao VARCHAR(10),
    usuario_banco VARCHAR(100),
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dados_antigos JSONB,
    dados_novos JSONB,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

-- =================================================================================
-- 4. APLICAÇÃO DE GATILHOS (TRIGGERS)
-- =================================================================================

DROP TRIGGER IF EXISTS trg_atualiza_chamado ON chamados_tecnuv;
CREATE TRIGGER trg_atualiza_chamado BEFORE UPDATE ON chamados_tecnuv FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

DROP TRIGGER IF EXISTS trg_atualiza_ticket ON tickets_epsy;
CREATE TRIGGER trg_atualiza_ticket BEFORE UPDATE ON tickets_epsy FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

DROP TRIGGER IF EXISTS trg_atualiza_conhecimento ON base_conhecimento;
CREATE TRIGGER trg_atualiza_conhecimento BEFORE UPDATE ON base_conhecimento FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

-- =================================================================================
-- 5. ÍNDICES PARA OTIMIZAÇÃO DE CONSULTAS
-- =================================================================================

CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados_tecnuv(status_atual);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets_epsy(status_atual);
CREATE INDEX IF NOT EXISTS idx_base_conhecimento_status ON base_conhecimento(status);
CREATE INDEX IF NOT EXISTS idx_goto_hash ON atendimentos_goto(telefone_hash);
CREATE INDEX IF NOT EXISTS idx_multi360_hash ON atendimentos_multi360(telefone_hash);

-- =================================================================================
-- 6. DADOS INICIAIS E MIGRAÇÕES
-- =================================================================================

-- Configurações padrão do robô de automação.
INSERT INTO configuracoes_robo (chave, valor, descricao) 
VALUES 
    ('robo_ativo', 'false', 'Liga/Desliga a varredura automática'),
    ('intervalo_minutos', '60', 'Tempo de hibernação do robô')
ON CONFLICT (chave) DO NOTHING;

-- Script para vincular analistas a atendimentos antigos do GoTo com base no ramal.
-- Deve ser executado após a carga inicial de usuários e atendimentos.
UPDATE atendimentos_goto ag
SET 
    id_analista_epsy = u.id,
    nome_analista_epsy = u.nome
FROM usuarios u
WHERE 
    -- Procura pelo padrão "RAMAL: RAMAL" nos participantes da chamada.
    ag.participantes LIKE '%' || u.ramal || ': ' || u.ramal || '%'
    -- Garante que o usuário tenha um ramal válido.
    AND u.ramal IS NOT NULL 
    AND u.ramal <> ''
    -- Atualiza apenas registros que ainda não foram vinculados.
    AND ag.id_analista_epsy IS NULL;

-- =================================================================================
-- FIM DO SCRIPT
-- =================================================================================