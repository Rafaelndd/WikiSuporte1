-- =================================================================================
-- WikiSuporte - Script único de provisionamento de banco (estrutura completa)
-- Script físico único com todo SQL inline, sem comandos de include (\i).
-- Princípios de boas práticas: ordem determinística, seções por módulo e fail-fast.
-- =================================================================================
\set ON_ERROR_STOP on
\set ECHO all

BEGIN;

-- =========================================
-- INICIO BLOCO: database\init_database.sql
-- =========================================
-- =================================================================================
-- PROJETO: WikiSuporte / Oráculo ERP (Psy)
-- AUTOR: Rafael Duarte Nascimento
-- DESCRIÇÃO: Script Oficial de Inicialização e Estrutura do Banco de Dados PostgreSQL.
-- VERSÃO: 3.0 (Revisada e Organizada para PostgreSQL 18+)
-- DATA DA REVISÃO: 12 de março de 2026
--
-- NOTAS DA REVISÃO:
--  - Reorganizado para garantir a ordem correta de criação de dependências.
--  - Removidos comandos `DROP TABLE ... CASCADE` para prevenir perda de dados acidental.
--  - Estrutura consolidada em seções lógicas para maior clareza e manutenção.
--  - Adicionados comentários técnicos e explicações sobre as boas práticas aplicadas.
-- =================================================================================

-- =================================================================================
-- 1. CONFIGURAÇÕES E EXTENSÕES GLOBAIS
-- =================================================================================
-- Define o conjunto de caracteres padrão para a conexão, evitando problemas com acentuação.
SET client_encoding = 'UTF8';
-- Garante que as strings sigam o comportamento padrão do SQL, melhorando a portabilidade.
SET standard_conforming_strings = on;

-- Habilita a geração de UUIDs (Identificadores Únicos Universais).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Fornece funções de criptografia, essenciais para senhas e dados sensíveis (LGPD).
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =================================================================================
-- 2. DEFINIÇÃO DE TABELAS (ESTRUTURA BASE)
-- =================================================================================
-- Todas as tabelas são criadas com `IF NOT EXISTS` para garantir que o script 
-- possa ser executado várias vezes sem erros (idempotência).

-- ---------------------------------------------------------------------------------
-- Seção 2.1: Infraestrutura e Autenticação
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(150) UNIQUE NOT NULL,
    username VARCHAR(150),
    email VARCHAR(150) UNIQUE,
    perfil VARCHAR(50) NOT NULL,
    ramal VARCHAR(20),
    password_hash VARCHAR(255),
    ativo BOOLEAN DEFAULT TRUE,
    em_ferias BOOLEAN DEFAULT FALSE,
    em_atendimento_externo BOOLEAN DEFAULT FALSE,
    caminho_foto_perfil VARCHAR(500) DEFAULT '',
    data_criacao TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    xp_total INTEGER DEFAULT 0,
    medalha_atual VARCHAR(100) DEFAULT 'Iniciante 🌱'
);

CREATE TABLE IF NOT EXISTS configuracoes_robo (
    chave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    descricao TEXT,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 2.2: Dados de Atendimento (Origens Externas)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS atendimentos_goto (
    id_conversa VARCHAR(255) PRIMARY KEY,
    data_chamada TIMESTAMP WITH TIME ZONE,
    duracao_ms BIGINT,
    direcao VARCHAR(50),
    resultado VARCHAR(100),
    telefone_hash VARCHAR(256),
    telefone_origem VARCHAR(50),
    participantes TEXT,
    gravado VARCHAR(20),
    data_importacao TIMESTAMP WITH TIME ZONE,
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
    data_inicio TIMESTAMP WITH TIME ZONE,
    data_finalizacao TIMESTAMP WITH TIME ZONE,
    data_ultima_mensagem TIMESTAMP WITH TIME ZONE,
    avaliacao INTEGER,
    data_importacao TIMESTAMP WITH TIME ZONE,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

-- ---------------------------------------------------------------------------------
-- Seção 2.3: Dados do Fornecedor (Tecnuv) e Ciclos de Vida
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
    data_abertura TIMESTAMP WITH TIME ZONE,
    ultima_alteracao_tecnuv TIMESTAMP WITH TIME ZONE,
    assunto_encerramento TEXT,
    data_encerramento TIMESTAMP WITH TIME ZONE,
    previsao_conclusao DATE,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS releases_tecnuv (
    id_release SERIAL PRIMARY KEY,
    titulo_versao VARCHAR(255) NOT NULL,
    autor_data VARCHAR(255),
    texto_completo TEXT,
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado) ON DELETE SET NULL,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chamados_corrigidos_releases (
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    id_release INTEGER NOT NULL REFERENCES releases_tecnuv(id_release) ON DELETE CASCADE,
    PRIMARY KEY (nr_chamado, id_release)
);

-- ---------------------------------------------------------------------------------
-- Seção 2.4: Operação Interna EPSY
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets_epsy (
    nr_ticket INTEGER PRIMARY KEY,
    cliente_nome VARCHAR(255),
    assunto TEXT,
    data_abertura TIMESTAMP WITH TIME ZONE,
    nome_analista_epsy VARCHAR(100),
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    status_atual VARCHAR(100) NOT NULL,
    chamado_vinculado INTEGER,
    tempo_aberto_str VARCHAR(100),
    avaliacao VARCHAR(50),
    data_ultima_interacao TIMESTAMP WITH TIME ZONE,
    ultima_mensagem TEXT,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plantoes_epsy (
    id_plantao SERIAL PRIMARY KEY,
    nome_analista_epsy VARCHAR(255) NOT NULL,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    data_hora_entrada TIMESTAMP WITH TIME ZONE,
    data_hora_saida TIMESTAMP WITH TIME ZONE,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 2.5: Base de Conhecimento (Motor da IA e Gamificação)
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
    data_ocorrido DATE DEFAULT CURRENT_DATE,
    qtd_upvotes INTEGER DEFAULT 0,
    qtd_visualizacoes INTEGER DEFAULT 0,
    qtd_tentativas INTEGER DEFAULT 1,
    modalidade_contribuicao VARCHAR(32) DEFAULT 'EVENTO_ATUAL',
    pontos_contribuicao INTEGER,
    data_avaliacao TIMESTAMP WITH TIME ZONE,
    id_avaliador INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_doc_origem UNIQUE (origem, nr_documento)
);

CREATE TABLE IF NOT EXISTS base_conhecimento_votos (
    id SERIAL PRIMARY KEY,
    id_conhecimento INTEGER REFERENCES base_conhecimento(id) ON DELETE CASCADE,
    id_analista_votante INTEGER REFERENCES usuarios(id),
    data_voto TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_conhecimento, id_analista_votante)
);

CREATE TABLE IF NOT EXISTS contribution_scoring_rules (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pontos_evento_passado INTEGER NOT NULL DEFAULT 90,
    multiplicador_diario_apos_qtd INTEGER NOT NULL DEFAULT 3,
    multiplicador_diario_valor INTEGER NOT NULL DEFAULT 2,
    bonus_semanal_meta_qtd INTEGER NOT NULL DEFAULT 15,
    bonus_semanal_meta_pontos INTEGER NOT NULL DEFAULT 1000,
    penalidade_sem_7_dias INTEGER NOT NULL DEFAULT 200,
    minimo_semanal_sem_penalidade INTEGER NOT NULL DEFAULT 5,
    penalidade_semana_insuficiente INTEGER NOT NULL DEFAULT 100,
    janela_carencia_dias INTEGER NOT NULL DEFAULT 7,
    max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100,
    atualizado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO contribution_scoring_rules (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS user_xp_events (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo_evento VARCHAR(64) NOT NULL,
    pontos INTEGER NOT NULL,
    id_base_conhecimento INTEGER REFERENCES base_conhecimento(id) ON DELETE SET NULL,
    event_key VARCHAR(256) NOT NULL,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_xp_events_event_key UNIQUE (event_key)
);

CREATE INDEX IF NOT EXISTS idx_user_xp_events_usuario ON user_xp_events(usuario_id);

CREATE TABLE IF NOT EXISTS historico_buscas_psy (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    pergunta TEXT NOT NULL,
    resposta_ia TEXT,
    tokens_prompt INTEGER,
    tokens_resposta INTEGER,
    total_tokens INTEGER,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 2.6: CRM e Vínculos (Com tratamento para LGPD)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clientes_crm (
    id_cliente SERIAL PRIMARY KEY,
    razao_social VARCHAR(255),
    cnpj VARCHAR(18) UNIQUE,
    cnpj_criptografado BYTEA,
    email_criptografado BYTEA,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS clientes_telefones (
    id_telefone SERIAL PRIMARY KEY,
    id_cliente INTEGER REFERENCES clientes_crm(id_cliente) ON DELETE CASCADE,
    numero VARCHAR(50),
    numero_criptografado BYTEA,
    telefone_hash VARCHAR(256),
    origem_dado VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS clientes_vinculados_chamado (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    nome_cliente VARCHAR(255) NOT NULL,
    cnpj_cliente VARCHAR(25),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------------
-- Seção 2.7: Históricos e Auditoria
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_transicao_status (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS historico_transicao_tickets (
    id SERIAL PRIMARY KEY,
    nr_ticket INTEGER NOT NULL REFERENCES tickets_epsy(nr_ticket) ON DELETE CASCADE,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_interacoes (
    id_interacao SERIAL PRIMARY KEY,
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    data_interacao TIMESTAMP WITH TIME ZONE,
    descricao_texto TEXT,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS cobrancas_chamados (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    data_cobranca TIMESTAMP WITH TIME ZONE,
    analista_epsy VARCHAR(100),
    cliente_solicitante VARCHAR(255),
    texto_bruto_cobranca TEXT,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs_auditoria_sistema (
    id_log SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    acao VARCHAR(100),
    detalhe TEXT,
    nome_analista_epsy VARCHAR(100),
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs_auditoria_dados_tabelas (
    id_log SERIAL PRIMARY KEY,
    tabela_afetada VARCHAR(100),
    operacao VARCHAR(10),
    usuario_banco VARCHAR(100),
    data_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    dados_antigos JSONB,
    dados_novos JSONB,
    id_analista_epsy INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    nome_analista_epsy VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS log_auditoria_usuarios (
    id SERIAL PRIMARY KEY,
    data_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    operacao VARCHAR(10) NOT NULL,
    db_user VARCHAR(50) DEFAULT current_user,
    app_user_id INTEGER,
    app_name TEXT DEFAULT current_setting('application_name', true),
    dados_anteriores JSONB,
    dados_novos JSONB
);

-- ---------------------------------------------------------------------------------
-- Seção 2.8: Ciclos de Homologação (Nova Arquitetura)
-- ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chamados (
    id_chamado VARCHAR(50) PRIMARY KEY,
    assunto TEXT NOT NULL,
    modulo_sistema VARCHAR(100),
    data_primeiro_registro TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS releases (
    id_release SERIAL PRIMARY KEY,
    versao_release VARCHAR(50) UNIQUE NOT NULL,
    data_liberacao TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    autor VARCHAR(255),
    nome_arquivo VARCHAR(255),
    texto_completo TEXT,
    caminho_arquivo VARCHAR(512)
);

CREATE TABLE IF NOT EXISTS ciclos_homologacao (
    id_ciclo SERIAL PRIMARY KEY,
    id_chamado VARCHAR(50) NOT NULL REFERENCES chamados(id_chamado) ON DELETE CASCADE,
    id_release INTEGER NOT NULL REFERENCES releases(id_release) ON DELETE CASCADE,
    status_teste VARCHAR(20) DEFAULT 'Aguardando' CHECK (status_teste IN ('Aguardando', 'Aprovado', 'Reprovado')),
    motivo_reprovacao TEXT,
    data_teste TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uk_chamado_release UNIQUE (id_chamado, id_release)
);

-- =================================================================================
-- 3. DOCUMENTAÇÃO DO ESQUEMA (COMMENTS)
-- =================================================================================
-- Comentários são metadados importantes para a autodocumentação do banco de dados.
COMMENT ON TABLE chamados IS 'Entidade central para chamados de correção/evolução, independente do ciclo de release.';
COMMENT ON TABLE releases IS 'Representa os pacotes de liberação (versões) do sistema, com seu conteúdo e metadados.';
COMMENT ON TABLE ciclos_homologacao IS 'Tabela de ligação (N:N) que audita a qualidade e o retrabalho, vinculando chamados a releases e registrando o resultado dos testes.';

COMMENT ON COLUMN releases.autor IS 'Autor do release (pode ser preenchido manualmente ou via automação).';
COMMENT ON COLUMN releases.nome_arquivo IS 'Nome original do arquivo de release que foi enviado.';
COMMENT ON COLUMN releases.texto_completo IS 'Conteúdo textual completo extraído do documento de release.';
COMMENT ON COLUMN releases.caminho_arquivo IS 'Caminho relativo ao projeto onde o arquivo físico do release foi armazenado.';

-- =================================================================================
-- 4. FUNÇÕES E PROCEDIMENTOS ARMAZENADOS
-- =================================================================================
-- Funções são definidas com `CREATE OR REPLACE` para permitir atualizações futuras.

-- Função genérica para atualizar o campo 'atualizado_em' em qualquer tabela.
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

-- Função para criptografar a senha do usuário antes de salvar, usando bcrypt.
CREATE OR REPLACE FUNCTION trg_func_hash_senha()
RETURNS TRIGGER AS $$
BEGIN
    -- Se o campo de senha estiver vazio/nulo, não faz nada.
    IF NEW.password_hash IS NULL OR NEW.password_hash = '' THEN
        RETURN NEW;
    END IF;

    -- Proteção contra "Duplo Hash": Só aplica a criptografia se a string NÃO começar com o padrão do bcrypt ($2a$, $2b$, $2y$).
    IF NEW.password_hash NOT LIKE '$2%' THEN
        NEW.password_hash = crypt(NEW.password_hash, gen_salt('bf'));
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Função de auditoria para a tabela de usuários.
CREATE OR REPLACE FUNCTION trg_audita_usuarios()
RETURNS TRIGGER AS $$
DECLARE
    v_app_user_id INTEGER;
    v_old_data JSONB;
    v_new_data JSONB;
BEGIN
    -- Captura o ID do usuário da aplicação, se definido na sessão.
    BEGIN
        v_app_user_id := current_setting('myapp.user_id', true)::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        v_app_user_id := NULL; 
    END;

    -- Constrói os objetos JSON com os dados antigos e novos, removendo o hash da senha por segurança.
    IF (TG_OP = 'UPDATE') THEN
        v_old_data := to_jsonb(OLD) - 'password_hash';
        v_new_data := to_jsonb(NEW) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_anteriores, dados_novos)
        VALUES ('UPDATE', v_app_user_id, v_old_data, v_new_data);
        RETURN NEW;
        
    ELSIF (TG_OP = 'DELETE') THEN
        v_old_data := to_jsonb(OLD) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_anteriores)
        VALUES ('DELETE', v_app_user_id, v_old_data);
        RETURN OLD;
        
    ELSIF (TG_OP = 'INSERT') THEN
        v_new_data := to_jsonb(NEW) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_novos)
        VALUES ('INSERT', v_app_user_id, v_new_data);
        RETURN NEW;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Recálculo de XP: soma contribuições aprovadas (pontos_contribuicao ou legado), upvotes e user_xp_events.
CREATE OR REPLACE FUNCTION recalcular_xp_total_usuario(p_user_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_contrib BIGINT;
    v_ev BIGINT;
    v_xp BIGINT;
    v_medalha VARCHAR(100);
BEGIN
    SELECT
        COALESCE(SUM(
            CASE
                WHEN bc.pontos_contribuicao IS NOT NULL THEN bc.pontos_contribuicao::bigint
                ELSE (
                    CASE
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 7) THEN 100
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 14) THEN 50
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 21) THEN 25
                        ELSE 0
                    END
                )::bigint
            END
        ), 0)::bigint
        + (COALESCE(SUM(bc.qtd_upvotes), 0)::bigint * 20)
    INTO v_contrib
    FROM base_conhecimento bc
    WHERE bc.id_analista_autor = p_user_id AND bc.status = 'APROVADO';

    SELECT COALESCE(SUM(ux.pontos::bigint), 0) INTO v_ev
    FROM user_xp_events ux
    WHERE ux.usuario_id = p_user_id;

    v_xp := GREATEST(0, COALESCE(v_contrib, 0) + COALESCE(v_ev, 0));

    v_medalha := CASE
        WHEN v_xp >= 1000000 THEN 'Expert'
        WHEN v_xp >= 950000  THEN 'Lenda do Suporte'
        WHEN v_xp >= 850000  THEN 'Referência Técnica'
        WHEN v_xp >= 700000  THEN 'Analista Mestre'
        WHEN v_xp >= 550000  THEN 'Analista Pleno'
        WHEN v_xp >= 400000  THEN 'Analista Jr'
        WHEN v_xp >= 250000  THEN 'Especialista Sênior'
        WHEN v_xp >= 150000  THEN 'Especialista N2'
        WHEN v_xp >= 100000  THEN 'Especialista N1'
        WHEN v_xp >= 75000   THEN 'Contribuidor Pleno'
        WHEN v_xp >= 50000   THEN 'Contribuidor Ativo'
        WHEN v_xp >= 20000   THEN 'Contribuidor Jr'
        WHEN v_xp >= 10000   THEN 'Novato Consistente'
        WHEN v_xp >= 5000    THEN 'Novato Proativo'
        WHEN v_xp >= 1000    THEN 'Novato Aspirante'
        ELSE 'Estagiário'
    END;

    UPDATE usuarios
    SET xp_total = v_xp::integer,
        medalha_atual = v_medalha
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION atualizar_xp_usuario()
RETURNS TRIGGER AS $$
DECLARE
    v_id_autor INTEGER;
BEGIN
    IF (TG_TABLE_NAME = 'base_conhecimento') THEN
        v_id_autor := NEW.id_analista_autor;
    ELSIF (TG_TABLE_NAME = 'base_conhecimento_votos') THEN
        SELECT id_analista_autor INTO v_id_autor FROM base_conhecimento
        WHERE id = COALESCE(NEW.id_conhecimento, OLD.id_conhecimento);
    END IF;

    IF v_id_autor IS NOT NULL THEN
        PERFORM recalcular_xp_total_usuario(v_id_autor);
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_dispara_recalc_xp_por_evento()
RETURNS TRIGGER AS $$
DECLARE
    v_uid INTEGER;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_uid := OLD.usuario_id;
    ELSE
        v_uid := NEW.usuario_id;
    END IF;
    IF v_uid IS NOT NULL THEN
        PERFORM recalcular_xp_total_usuario(v_uid);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- =================================================================================
-- 5. APLICAÇÃO DE GATILHOS (TRIGGERS)
-- =================================================================================
-- O padrão `DROP TRIGGER IF EXISTS` seguido por `CREATE TRIGGER` garante que o 
-- trigger seja sempre a versão mais recente definida neste script.

-- Gatilhos para atualizar o campo 'atualizado_em' automaticamente.
DROP TRIGGER IF EXISTS trg_atualiza_chamado ON chamados_tecnuv;
CREATE TRIGGER trg_atualiza_chamado BEFORE UPDATE ON chamados_tecnuv 
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

DROP TRIGGER IF EXISTS trg_atualiza_ticket ON tickets_epsy;
CREATE TRIGGER trg_atualiza_ticket BEFORE UPDATE ON tickets_epsy 
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

DROP TRIGGER IF EXISTS trg_atualiza_conhecimento ON base_conhecimento;
CREATE TRIGGER trg_atualiza_conhecimento BEFORE UPDATE ON base_conhecimento 
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

-- Gatilho de segurança para criptografar a senha do usuário.
DROP TRIGGER IF EXISTS trg_protege_senha_usuario ON usuarios;
CREATE TRIGGER trg_protege_senha_usuario
BEFORE INSERT OR UPDATE OF password_hash ON usuarios
FOR EACH ROW EXECUTE FUNCTION trg_func_hash_senha();

-- Gatilho de auditoria para operações na tabela de usuários.
DROP TRIGGER IF EXISTS trg_log_operacoes_usuarios ON usuarios;
CREATE TRIGGER trg_log_operacoes_usuarios
AFTER INSERT OR UPDATE OR DELETE ON usuarios
FOR EACH ROW EXECUTE FUNCTION trg_audita_usuarios();

-- Gatilhos de gamificação para recalcular XP e medalhas.
DROP TRIGGER IF EXISTS trg_atualizar_xp_base ON base_conhecimento;
CREATE TRIGGER trg_atualizar_xp_base
AFTER INSERT OR UPDATE ON base_conhecimento
FOR EACH ROW EXECUTE FUNCTION atualizar_xp_usuario();

DROP TRIGGER IF EXISTS trg_atualizar_xp_votos ON base_conhecimento_votos;
CREATE TRIGGER trg_atualizar_xp_votos
AFTER INSERT OR UPDATE OR DELETE ON base_conhecimento_votos
FOR EACH ROW EXECUTE FUNCTION atualizar_xp_usuario();

DROP TRIGGER IF EXISTS trg_user_xp_events_recalc ON user_xp_events;
CREATE TRIGGER trg_user_xp_events_recalc
AFTER INSERT OR UPDATE OR DELETE ON user_xp_events
FOR EACH ROW EXECUTE FUNCTION trg_dispara_recalc_xp_por_evento();

-- =================================================================================
-- 6. ÍNDICES PARA OTIMIZAÇÃO DE CONSULTAS
-- =================================================================================
-- Índices são cruciais para o desempenho de consultas (SELECTs). `IF NOT EXISTS` previne erros em execuções repetidas.

-- Índices em colunas de status para acelerar filtros comuns.
CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados_tecnuv(status_atual);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets_epsy(status_atual);
CREATE INDEX IF NOT EXISTS idx_base_conhecimento_status ON base_conhecimento(status);

-- Índices em campos de hash para acelerar o cruzamento de dados de telefonia.
CREATE INDEX IF NOT EXISTS idx_goto_hash ON atendimentos_goto(telefone_hash);
CREATE INDEX IF NOT EXISTS idx_multi360_hash ON atendimentos_multi360(telefone_hash);
CREATE INDEX IF NOT EXISTS idx_clientes_telefones_hash ON clientes_telefones(telefone_hash);

-- Índice no CNPJ para garantir buscas rápidas de clientes.
CREATE INDEX IF NOT EXISTS idx_clientes_crm_cnpj ON clientes_crm(cnpj);

-- Índices para a nova arquitetura de ciclos de homologação.
CREATE INDEX IF NOT EXISTS idx_ciclos_status ON ciclos_homologacao(status_teste);
CREATE INDEX IF NOT EXISTS idx_ciclos_id_chamado ON ciclos_homologacao(id_chamado);
CREATE INDEX IF NOT EXISTS idx_ciclos_id_release ON ciclos_homologacao(id_release);
CREATE INDEX IF NOT EXISTS idx_chamados_modulo ON chamados(modulo_sistema);

-- =================================================================================
-- 7. DADOS INICIAIS E MIGRAÇÕES
-- =================================================================================

-- Carga inicial de configurações padrão do robô.
-- `ON CONFLICT (chave) DO NOTHING` evita duplicatas e erros se os dados já existirem.
INSERT INTO configuracoes_robo (chave, valor, descricao) 
VALUES 
    ('robo_ativo', 'false', 'Controla se a varredura automática de dados está ativa (true/false).'),
    ('intervalo_minutos', '60', 'Intervalo em minutos entre cada execução do robô.')
ON CONFLICT (chave) DO NOTHING;

-- Script de migração para vincular atendimentos antigos do GoTo a analistas com base no ramal.
-- Este bloco pode ser executado manualmente após a carga inicial de dados.
-- É seguro executá-lo múltiplas vezes, pois a condição `ag.id_analista_epsy IS NULL` previne reprocessamento.
UPDATE atendimentos_goto ag
SET 
    id_analista_epsy = u.id,
    nome_analista_epsy = u.nome
FROM usuarios u
WHERE 
    -- Procura pelo padrão "RAMAL: RAMAL" que identifica o participante na gravação.
    ag.participantes LIKE '%' || u.ramal || ': ' || u.ramal || '%'
    AND u.ramal IS NOT NULL 
    AND u.ramal <> ''
    AND ag.id_analista_epsy IS NULL;

-- Bloco anônimo para recalcular o XP e a medalha de todos os usuários existentes.
-- Útil para ser executado uma vez após a implementação do sistema de gamificação
-- ou para corrigir inconsistências.
DO $$ 
DECLARE 
    r RECORD;
    xp_total_calc BIGINT;
    patente_calc TEXT;
BEGIN
    RAISE NOTICE 'Iniciando recálculo de XP e patentes para todos os contribuidores...';
    -- Loop por todos os usuários que já contribuíram com conhecimento.
    FOR r IN (SELECT DISTINCT id_analista_autor FROM base_conhecimento WHERE status = 'APROVADO' AND id_analista_autor IS NOT NULL) 
    LOOP
        -- 1. Calcula o XP Total (Agilidade + Upvotes) para o usuário do loop.
        SELECT 
            COALESCE(SUM(
                CASE 
                    WHEN (bc.criado_em::date - bc.data_ocorrido::date <= 7) THEN 100
                    WHEN (bc.criado_em::date - bc.data_ocorrido::date <= 14) THEN 50
                    WHEN (bc.criado_em::date - bc.data_ocorrido::date <= 21) THEN 25
                    ELSE 0 
                END
            ), 0) + (COALESCE(SUM(bc.qtd_upvotes), 0) * 20)
        INTO xp_total_calc
        FROM base_conhecimento bc
        WHERE bc.id_analista_autor = r.id_analista_autor AND bc.status = 'APROVADO';

        -- 2. Define o nome da patente com base no XP calculado.
        patente_calc := CASE 
            WHEN xp_total_calc >= 1000000 THEN 'Expert'
            WHEN xp_total_calc >= 950000  THEN 'Lenda do Suporte'
            WHEN xp_total_calc >= 850000  THEN 'Referência Técnica'
            WHEN xp_total_calc >= 700000  THEN 'Analista Mestre'
            WHEN xp_total_calc >= 550000  THEN 'Analista Pleno'
            WHEN xp_total_calc >= 400000  THEN 'Analista Jr'
            WHEN xp_total_calc >= 250000  THEN 'Especialista Sênior'
            WHEN xp_total_calc >= 150000  THEN 'Especialista N2'
            WHEN xp_total_calc >= 100000  THEN 'Especialista N1'
            WHEN xp_total_calc >= 75000   THEN 'Contribuidor Pleno'
            WHEN xp_total_calc >= 50000   THEN 'Contribuidor Ativo'
            WHEN xp_total_calc >= 20000   THEN 'Contribuidor Jr'
            WHEN xp_total_calc >= 10000   THEN 'Novato Consistente'
            WHEN xp_total_calc >= 5000    THEN 'Novato Proativo'
            WHEN xp_total_calc >= 1000    THEN 'Novato Aspirante'
            ELSE 'Estagiário'
        END;

        -- 3. Atualiza o cadastro do analista com os valores recalculados.
        UPDATE usuarios 
        SET xp_total = xp_total_calc, 
            medalha_atual = patente_calc 
        WHERE id = r.id_analista_autor;
    END LOOP;
    RAISE NOTICE 'Recálculo concluído.';
END $$;

-- =================================================================================
-- FIM DO SCRIPT
-- =================================================================================
-- =========================================
-- FIM BLOCO: database\init_database.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migrations\20260403_usuarios_modelo_gestao.sql
-- =========================================
-- WikiSuporte — migração: campos para gestão de usuários (fase 1)
-- Executar contra a base já existente (idempotente).
-- Não altera password_hash nem nomes de login: preenche `username` a partir de `nome`
-- quando vazio, mantendo compatibilidade com streamlit-authenticator / wiki_authenticator.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS username VARCHAR(150);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_ferias BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_atendimento_externo BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS caminho_foto_perfil VARCHAR(500) DEFAULT '';

COMMENT ON COLUMN usuarios.username IS 'Login curto (minúsculas recomendado); autenticação aceita também nome.';
COMMENT ON COLUMN usuarios.em_ferias IS 'Indicador operacional; default false.';
COMMENT ON COLUMN usuarios.em_atendimento_externo IS 'Indicador operacional; default false.';
COMMENT ON COLUMN usuarios.caminho_foto_perfil IS 'Caminho ou URL da foto; vazio se não houver.';

-- Retrocompatibilidade: quem só tinha `nome` como identificador continua a autenticar pelo nome;
-- `username` espelha o nome normalizado para o novo modelo.
UPDATE usuarios
SET username = lower(trim(nome))
WHERE username IS NULL OR btrim(username) = '';
-- =========================================
-- FIM BLOCO: database\migrations\20260403_usuarios_modelo_gestao.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migrations\20260403_contribution_xp_aprovacao.sql
-- =========================================
-- WikiSuporte: XP na aprovação (motores Python + consistência no PostgreSQL).
-- Executar em produção após backup. Idempotente (IF NOT EXISTS / CREATE OR REPLACE).

-- Colunas em base_conhecimento
ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS modalidade_contribuicao VARCHAR(32) DEFAULT 'EVENTO_ATUAL';
ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS pontos_contribuicao INTEGER;
ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS data_avaliacao TIMESTAMPTZ;
ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS id_avaliador INTEGER REFERENCES usuarios(id) ON DELETE SET NULL;
ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS qtd_tentativas INTEGER DEFAULT 1;

-- Configuração singleton de pontuação
CREATE TABLE IF NOT EXISTS contribution_scoring_rules (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pontos_evento_passado INTEGER NOT NULL DEFAULT 90,
    multiplicador_diario_apos_qtd INTEGER NOT NULL DEFAULT 3,
    multiplicador_diario_valor INTEGER NOT NULL DEFAULT 2,
    bonus_semanal_meta_qtd INTEGER NOT NULL DEFAULT 15,
    bonus_semanal_meta_pontos INTEGER NOT NULL DEFAULT 1000,
    janela_carencia_dias INTEGER NOT NULL DEFAULT 7,
    max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO contribution_scoring_rules (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

-- Eventos de XP (bônus semanal, penalidades futuras, etc.)
CREATE TABLE IF NOT EXISTS user_xp_events (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo_evento VARCHAR(64) NOT NULL,
    pontos INTEGER NOT NULL,
    id_base_conhecimento INTEGER REFERENCES base_conhecimento(id) ON DELETE SET NULL,
    event_key VARCHAR(256) NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_xp_events_event_key UNIQUE (event_key)
);

CREATE INDEX IF NOT EXISTS idx_user_xp_events_usuario ON user_xp_events(usuario_id);

-- Backfill: aprovações antigas sem data_avaliacao
UPDATE base_conhecimento
SET data_avaliacao = COALESCE(data_avaliacao, criado_em)
WHERE status = 'APROVADO' AND data_avaliacao IS NULL;

-- Recálculo centralizado (contribuições aprovadas + upvotes + eventos)
CREATE OR REPLACE FUNCTION recalcular_xp_total_usuario(p_user_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_contrib BIGINT;
    v_ev BIGINT;
    v_xp BIGINT;
    v_medalha VARCHAR(100);
BEGIN
    SELECT
        COALESCE(SUM(
            CASE
                WHEN bc.pontos_contribuicao IS NOT NULL THEN bc.pontos_contribuicao::bigint
                ELSE (
                    CASE
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 7) THEN 100
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 14) THEN 50
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 21) THEN 25
                        ELSE 0
                    END
                )::bigint
            END
        ), 0)::bigint
        + (COALESCE(SUM(bc.qtd_upvotes), 0)::bigint * 20)
    INTO v_contrib
    FROM base_conhecimento bc
    WHERE bc.id_analista_autor = p_user_id AND bc.status = 'APROVADO';

    SELECT COALESCE(SUM(ux.pontos::bigint), 0) INTO v_ev
    FROM user_xp_events ux
    WHERE ux.usuario_id = p_user_id;

    v_xp := GREATEST(0, COALESCE(v_contrib, 0) + COALESCE(v_ev, 0));

    v_medalha := CASE
        WHEN v_xp >= 1000000 THEN 'Expert'
        WHEN v_xp >= 950000  THEN 'Lenda do Suporte'
        WHEN v_xp >= 850000  THEN 'Referência Técnica'
        WHEN v_xp >= 700000  THEN 'Analista Mestre'
        WHEN v_xp >= 550000  THEN 'Analista Pleno'
        WHEN v_xp >= 400000  THEN 'Analista Jr'
        WHEN v_xp >= 250000  THEN 'Especialista Sênior'
        WHEN v_xp >= 150000  THEN 'Especialista N2'
        WHEN v_xp >= 100000  THEN 'Especialista N1'
        WHEN v_xp >= 75000   THEN 'Contribuidor Pleno'
        WHEN v_xp >= 50000   THEN 'Contribuidor Ativo'
        WHEN v_xp >= 20000   THEN 'Contribuidor Jr'
        WHEN v_xp >= 10000   THEN 'Novato Consistente'
        WHEN v_xp >= 5000    THEN 'Novato Proativo'
        WHEN v_xp >= 1000    THEN 'Novato Aspirante'
        ELSE 'Estagiário'
    END;

    UPDATE usuarios
    SET xp_total = v_xp::integer,
        medalha_atual = v_medalha
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION atualizar_xp_usuario()
RETURNS TRIGGER AS $$
DECLARE
    v_id_autor INTEGER;
BEGIN
    IF (TG_TABLE_NAME = 'base_conhecimento') THEN
        v_id_autor := NEW.id_analista_autor;
    ELSIF (TG_TABLE_NAME = 'base_conhecimento_votos') THEN
        SELECT id_analista_autor INTO v_id_autor FROM base_conhecimento
        WHERE id = COALESCE(NEW.id_conhecimento, OLD.id_conhecimento);
    END IF;

    IF v_id_autor IS NOT NULL THEN
        PERFORM recalcular_xp_total_usuario(v_id_autor);
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_dispara_recalc_xp_por_evento()
RETURNS TRIGGER AS $$
DECLARE
    v_uid INTEGER;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_uid := OLD.usuario_id;
    ELSE
        v_uid := NEW.usuario_id;
    END IF;
    IF v_uid IS NOT NULL THEN
        PERFORM recalcular_xp_total_usuario(v_uid);
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_xp_events_recalc ON user_xp_events;
CREATE TRIGGER trg_user_xp_events_recalc
AFTER INSERT OR UPDATE OR DELETE ON user_xp_events
FOR EACH ROW EXECUTE FUNCTION trg_dispara_recalc_xp_por_evento();
-- =========================================
-- FIM BLOCO: database\migrations\20260403_contribution_xp_aprovacao.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migrations\20260404_contribution_scoring_penalidades.sql
-- =========================================
-- Penalidades de contribuição (regras §11) — colunas em contribution_scoring_rules.
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS penalidade_sem_7_dias INTEGER NOT NULL DEFAULT 200;
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS minimo_semanal_sem_penalidade INTEGER NOT NULL DEFAULT 5;
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS penalidade_semana_insuficiente INTEGER NOT NULL DEFAULT 100;
-- =========================================
-- FIM BLOCO: database\migrations\20260404_contribution_scoring_penalidades.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migrations\20260405_xp_guardrails_e_carencia.sql
-- =========================================
-- Ajustes de regras XP (v1.0.23+):
-- 1) Evento passado = 90 pontos
-- 2) XP total nunca negativo
-- 3) Atualiza configuração singleton já existente

ALTER TABLE contribution_scoring_rules
    ALTER COLUMN pontos_evento_passado SET DEFAULT 90;

ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS janela_carencia_dias INTEGER NOT NULL DEFAULT 7;

ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100;

UPDATE contribution_scoring_rules
SET pontos_evento_passado = 90,
    janela_carencia_dias = COALESCE(janela_carencia_dias, 7),
    max_desconto_semanal_xp = COALESCE(max_desconto_semanal_xp, 100),
    atualizado_em = CURRENT_TIMESTAMP
WHERE id = 1;

CREATE OR REPLACE FUNCTION recalcular_xp_total_usuario(p_user_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_contrib BIGINT;
    v_ev BIGINT;
    v_xp BIGINT;
    v_medalha VARCHAR(100);
BEGIN
    SELECT
        COALESCE(SUM(
            CASE
                WHEN bc.pontos_contribuicao IS NOT NULL THEN bc.pontos_contribuicao::bigint
                ELSE (
                    CASE
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 7) THEN 100
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 14) THEN 50
                        WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido::timestamp)) <= 21) THEN 25
                        ELSE 0
                    END
                )::bigint
            END
        ), 0)::bigint
        + (COALESCE(SUM(bc.qtd_upvotes), 0)::bigint * 20)
    INTO v_contrib
    FROM base_conhecimento bc
    WHERE bc.id_analista_autor = p_user_id AND bc.status = 'APROVADO';

    SELECT COALESCE(SUM(ux.pontos::bigint), 0) INTO v_ev
    FROM user_xp_events ux
    WHERE ux.usuario_id = p_user_id;

    v_xp := GREATEST(0, COALESCE(v_contrib, 0) + COALESCE(v_ev, 0));

    v_medalha := CASE
        WHEN v_xp >= 1000000 THEN 'Expert'
        WHEN v_xp >= 950000  THEN 'Lenda do Suporte'
        WHEN v_xp >= 850000  THEN 'Referência Técnica'
        WHEN v_xp >= 700000  THEN 'Analista Mestre'
        WHEN v_xp >= 550000  THEN 'Analista Pleno'
        WHEN v_xp >= 400000  THEN 'Analista Jr'
        WHEN v_xp >= 250000  THEN 'Especialista Sênior'
        WHEN v_xp >= 150000  THEN 'Especialista N2'
        WHEN v_xp >= 100000  THEN 'Especialista N1'
        WHEN v_xp >= 75000   THEN 'Contribuidor Pleno'
        WHEN v_xp >= 50000   THEN 'Contribuidor Ativo'
        WHEN v_xp >= 20000   THEN 'Contribuidor Jr'
        WHEN v_xp >= 10000   THEN 'Novato Consistente'
        WHEN v_xp >= 5000    THEN 'Novato Proativo'
        WHEN v_xp >= 1000    THEN 'Novato Aspirante'
        ELSE 'Estagiário'
    END;

    UPDATE usuarios
    SET xp_total = v_xp::integer,
        medalha_atual = v_medalha
    WHERE id = p_user_id;
END;
$$ LANGUAGE plpgsql;

UPDATE usuarios
SET xp_total = 0
WHERE COALESCE(xp_total, 0) < 0;
-- =========================================
-- FIM BLOCO: database\migrations\20260405_xp_guardrails_e_carencia.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_atendimentos_registrados.sql
-- =========================================
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
    telefone_id INTEGER,
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
-- =========================================
-- FIM BLOCO: database\migracao_atendimentos_registrados.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_busca_semantica_topicos.sql
-- =========================================
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
-- =========================================
-- FIM BLOCO: database\migracao_busca_semantica_topicos.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_ciclos_homologacao.sql
-- =========================================
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
-- =========================================
-- FIM BLOCO: database\migracao_ciclos_homologacao.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_clientes_telefones_hash.sql
-- =========================================
-- Adiciona colunas para vínculo cliente-telefone com Goto/Multi360
-- clientes_crm.cnpj e clientes_telefones.numero/telefone_hash para cruzar com atendimentos

ALTER TABLE clientes_crm ADD COLUMN IF NOT EXISTS cnpj VARCHAR(18);
ALTER TABLE clientes_telefones ADD COLUMN IF NOT EXISTS numero VARCHAR(50);
ALTER TABLE clientes_telefones ADD COLUMN IF NOT EXISTS telefone_hash VARCHAR(256);

CREATE INDEX IF NOT EXISTS idx_clientes_telefones_hash ON clientes_telefones(telefone_hash);
CREATE INDEX IF NOT EXISTS idx_clientes_telefones_numero ON clientes_telefones(numero);
CREATE INDEX IF NOT EXISTS idx_clientes_crm_cnpj ON clientes_crm(cnpj);

-- Permite armazenar cliente identificado nos atendimentos
ALTER TABLE atendimentos_goto ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(255);
ALTER TABLE atendimentos_multi360 ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(255);
-- =========================================
-- FIM BLOCO: database\migracao_clientes_telefones_hash.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_contribuicoes_status.sql
-- =========================================
-- WikiSuporte: status OBSOLETO + qtd_tentativas em base_conhecimento
-- Execute uma vez no PostgreSQL.

ALTER TABLE base_conhecimento
  ADD COLUMN IF NOT EXISTS qtd_tentativas INTEGER DEFAULT 1;

COMMENT ON COLUMN base_conhecimento.status IS
  'PENDENTE | APROVADO | REJEITADO | OBSOLETO (visível na base; autor deve atualizar; após edição volta PENDENTE)';

-- Opcional: normalizar registros antigos que sumiam da listagem
UPDATE base_conhecimento
SET status = 'OBSOLETO',
    motivo_rejeicao = COALESCE(NULLIF(TRIM(motivo_rejeicao), ''), '[Migrado] Marcado para revisão.')
WHERE origem = 'CONHECIMENTO_SUPORTE' AND status = 'REVISAO_PENDENTE';
-- =========================================
-- FIM BLOCO: database\migracao_contribuicoes_status.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_goto_agent_calls.sql
-- =========================================
-- Migração: Tabela para relatório GoTo "Agent Calls" (chamadas atendidas por agente)
-- Fonte: CSV agent-calls_YYYYMMDD_YYYYMMDD.csv exportado do GoTo Connect
-- Uso: importação via zip ou arquivo único na aba Importação; Dashboard usa para contagem de Atendidas

CREATE TABLE IF NOT EXISTS goto_agent_calls (
    contact_id VARCHAR(255) PRIMARY KEY,
    queue_name VARCHAR(255),
    contact_creation_time TIMESTAMP WITH TIME ZONE,
    contact_resolution_time TIMESTAMP WITH TIME ZONE,
    time_in_queue_millis BIGINT,
    talk_time_millis BIGINT,
    wrap_time_millis BIGINT,
    handle_time_millis BIGINT,
    contact_resolution VARCHAR(100),
    contact_type VARCHAR(100),
    contact_participant_value VARCHAR(255),
    agent_name VARCHAR(255),
    telefone_hash VARCHAR(256),
    telefone_origem VARCHAR(50),
    data_importacao TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_goto_agent_calls_creation ON goto_agent_calls(contact_creation_time);
CREATE INDEX IF NOT EXISTS idx_goto_agent_calls_agent ON goto_agent_calls(agent_name);
CREATE INDEX IF NOT EXISTS idx_goto_agent_calls_hash ON goto_agent_calls(telefone_hash);

COMMENT ON TABLE goto_agent_calls IS 'Chamadas atendidas (Contact Resolution=COMPLETED) do relatório Agent Calls do GoTo Connect.';
-- =========================================
-- FIM BLOCO: database\migracao_goto_agent_calls.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_helpdesk_release_head.sql
-- =========================================
-- Cabeçalho do release mais recente no Helpdesk (primeiro link da Home).
-- O bot compara com a última sincronização; se igual, não reabre modais antigos.
CREATE TABLE IF NOT EXISTS helpdesk_release_head (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    titulo_link TEXT,
    versao_norm VARCHAR(32),
    atualizado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO helpdesk_release_head (id, titulo_link, versao_norm)
VALUES (1, '', '')
ON CONFLICT (id) DO NOTHING;
COMMENT ON TABLE helpdesk_release_head IS 'Último 1º release da Home Tecnuv já processado; versão atual do produto para dashboard.';
-- =========================================
-- FIM BLOCO: database\migracao_helpdesk_release_head.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_notificacoes_representante.sql
-- =========================================
-- Notificações in-app: pendente representante, release, cobrança 7 dias
CREATE TABLE IF NOT EXISTS notificacoes_wikisuporte (
    id SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    titulo VARCHAR(280) NOT NULL,
    mensagem TEXT,
    nr_chamado INTEGER,
    tipo VARCHAR(64) NOT NULL,
    lida BOOLEAN NOT NULL DEFAULT false,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notif_user_lida ON notificacoes_wikisuporte(id_usuario, lida);
CREATE INDEX IF NOT EXISTS idx_notif_nr ON notificacoes_wikisuporte(nr_chamado);
CREATE INDEX IF NOT EXISTS idx_notif_tipo_criado ON notificacoes_wikisuporte(tipo, criado_em);

-- Controle de reenvio (cobrança 7 dias)
ALTER TABLE chamados_tecnuv ADD COLUMN IF NOT EXISTS ultima_notif_repr_7d TIMESTAMPTZ;
ALTER TABLE chamados_tecnuv ADD COLUMN IF NOT EXISTS ultima_notif_repr_release TIMESTAMPTZ;

COMMENT ON TABLE notificacoes_wikisuporte IS 'Alertas WikiSuporte: representante, release, cobrança';
-- =========================================
-- FIM BLOCO: database\migracao_notificacoes_representante.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_notificacoes_sistema.sql
-- =========================================
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
-- =========================================
-- FIM BLOCO: database\migracao_notificacoes_sistema.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_release_itens.sql
-- =========================================
-- Itens de release: um registro por linha de nota + número de chamado (ex.: bullet + (13645))
CREATE TABLE IF NOT EXISTS release_itens (
    id_item SERIAL PRIMARY KEY,
    id_release INTEGER NOT NULL REFERENCES releases(id_release) ON DELETE CASCADE,
    nr_chamado INTEGER NOT NULL,
    linha_nota TEXT,
    versao VARCHAR(80),
    titulo_release TEXT,
    data_liberacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    autor VARCHAR(255),
    origem VARCHAR(32) DEFAULT 'manual',
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_release, nr_chamado, linha_nota)
);

CREATE INDEX IF NOT EXISTS idx_release_itens_nr ON release_itens(nr_chamado);
CREATE INDEX IF NOT EXISTS idx_release_itens_release ON release_itens(id_release);

COMMENT ON TABLE release_itens IS 'Uma linha por chamado citado no release; reincidência = COUNT(DISTINCT id_release) por nr_chamado > 1';
COMMENT ON TABLE releases_tecnuv IS 'Legado: releases raspados (modelo antigo); preferir releases + release_itens + ciclos_homologacao';
COMMENT ON TABLE chamados_corrigidos_releases IS 'Legado N:N chamado x release_tecnuv; homologação usa releases + ciclos_homologacao';
-- =========================================
-- FIM BLOCO: database\migracao_release_itens.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_release_itens_embedding.sql
-- =========================================
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
-- =========================================
-- FIM BLOCO: database\migracao_release_itens_embedding.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_releases_dados.sql
-- =========================================
-- =================================================================================
-- PROJETO: WikiSuporte - Dados completos dos releases
-- DESCRIÇÃO: Adiciona colunas para armazenar arquivo, autor, texto completo
-- =================================================================================

ALTER TABLE releases ADD COLUMN IF NOT EXISTS autor VARCHAR(255);
ALTER TABLE releases ADD COLUMN IF NOT EXISTS nome_arquivo VARCHAR(255);
ALTER TABLE releases ADD COLUMN IF NOT EXISTS texto_completo TEXT;
ALTER TABLE releases ADD COLUMN IF NOT EXISTS caminho_arquivo VARCHAR(512);

COMMENT ON COLUMN releases.autor IS 'Autor do release (cadastro manual ou Processamento Automático)';
COMMENT ON COLUMN releases.nome_arquivo IS 'Nome original do arquivo enviado';
COMMENT ON COLUMN releases.texto_completo IS 'Conteúdo textual completo do release';
COMMENT ON COLUMN releases.caminho_arquivo IS 'Caminho relativo ao projeto onde o arquivo foi salvo';
-- =========================================
-- FIM BLOCO: database\migracao_releases_dados.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_status_atual_normalizado.sql
-- =========================================
-- Opcional: gravar status_atual sempre em minúsculas no banco (alinhado ao Helpdesk).
-- O Dashboard já normaliza na leitura; execute só se quiser persistir um único casing.
-- UPDATE chamados_tecnuv SET status_atual = LOWER(TRIM(status_atual)) WHERE status_atual IS NOT NULL;
-- =========================================
-- FIM BLOCO: database\migracao_status_atual_normalizado.sql
-- =========================================

-- =========================================
-- INICIO BLOCO: database\migracao_vector_chamados.sql
-- =========================================
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
-- =========================================
-- FIM BLOCO: database\migracao_vector_chamados.sql
-- =========================================
COMMIT;

-- Fim do script de provisionamento único.

