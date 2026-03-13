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
    email VARCHAR(150) UNIQUE,
    perfil VARCHAR(50) NOT NULL,
    ramal VARCHAR(20),
    password_hash VARCHAR(255),
    ativo BOOLEAN DEFAULT TRUE,
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

-- Função para calcular o XP e a medalha do usuário com base em suas contribuições.
CREATE OR REPLACE FUNCTION atualizar_xp_usuario()
RETURNS TRIGGER AS $$
DECLARE
    v_id_autor INTEGER;
    v_xp_calculado INTEGER;
    v_nova_medalha VARCHAR(100);
BEGIN
    -- Identifica o autor do conteúdo ou do voto para saber quem deve ter o XP atualizado.
    IF (TG_TABLE_NAME = 'base_conhecimento') THEN
        v_id_autor := NEW.id_analista_autor;
    ELSIF (TG_TABLE_NAME = 'base_conhecimento_votos') THEN
        SELECT id_analista_autor INTO v_id_autor FROM base_conhecimento 
        WHERE id = COALESCE(NEW.id_conhecimento, OLD.id_conhecimento);
    END IF;
    
    -- Recalcula o XP total do zero para garantir consistência.
    -- A regra combina um bônus por agilidade (data_ocorrido vs criado_em) e um bônus por qualidade (upvotes).
    SELECT 
        COALESCE(SUM(
            CASE 
                WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido)) <= 7) THEN 100
                WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido)) <= 14) THEN 50
                WHEN (EXTRACT(DAY FROM (bc.criado_em - bc.data_ocorrido)) <= 21) THEN 25
                ELSE 0 
            END
        ), 0) + (COALESCE(SUM(bc.qtd_upvotes), 0) * 20)
    INTO v_xp_calculado
    FROM base_conhecimento bc
    WHERE bc.id_analista_autor = v_id_autor AND bc.status = 'APROVADO';

    -- Determina a nova medalha com base na nova pontuação de XP.
    v_nova_medalha := CASE 
        WHEN v_xp_calculado >= 1000000 THEN 'Expert'
        WHEN v_xp_calculado >= 950000  THEN 'Lenda do Suporte'
        WHEN v_xp_calculado >= 850000  THEN 'Referência Técnica'
        WHEN v_xp_calculado >= 700000  THEN 'Analista Mestre'
        WHEN v_xp_calculado >= 550000  THEN 'Analista Pleno'
        WHEN v_xp_calculado >= 400000  THEN 'Analista Jr'
        WHEN v_xp_calculado >= 250000  THEN 'Especialista Sênior'
        WHEN v_xp_calculado >= 150000  THEN 'Especialista N2'
        WHEN v_xp_calculado >= 100000  THEN 'Especialista N1'
        WHEN v_xp_calculado >= 75000   THEN 'Contribuidor Pleno'
        WHEN v_xp_calculado >= 50000   THEN 'Contribuidor Ativo'
        WHEN v_xp_calculado >= 20000   THEN 'Contribuidor Jr'
        WHEN v_xp_calculado >= 10000   THEN 'Novato Consistente'
        WHEN v_xp_calculado >= 5000    THEN 'Novato Proativo'
        WHEN v_xp_calculado >= 1000    THEN 'Novato Aspirante'
        ELSE 'Estagiário'
    END;

    -- Atualiza a tabela de usuários com os novos valores de XP e medalha.
    UPDATE usuarios 
    SET xp_total = COALESCE(v_xp_calculado, 0), 
        medalha_atual = v_nova_medalha 
    WHERE id = v_id_autor;

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
