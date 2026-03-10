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



CREATE TABLE log_auditoria_usuarios (
    id SERIAL PRIMARY KEY,
    data_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    operacao VARCHAR(10) NOT NULL, -- Guardará INSERT, UPDATE ou DELETE
    db_user VARCHAR(50) DEFAULT current_user, -- Ex: 'postgres' (Quem conectou no banco)
    app_user_id INTEGER, -- O ID do usuário logado no Python (WikiSuporte)
    app_name TEXT DEFAULT current_setting('application_name', true), -- O nome do app conectado
    dados_anteriores JSONB, -- Estado completo da linha ANTES da mudança
    dados_novos JSONB -- Estado completo da linha DEPOIS da mudança
);



CREATE OR REPLACE FUNCTION trg_audita_usuarios()
RETURNS TRIGGER AS $$
DECLARE
    v_app_user_id INTEGER;
    v_old_data JSONB;
    v_new_data JSONB;
BEGIN
    -- Captura o ID do usuário do Python
    BEGIN
        v_app_user_id := current_setting('myapp.user_id', true)::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        v_app_user_id := NULL; 
    END;

    -- Usa o nome exato da sua coluna para não gravar a senha no log de auditoria
    IF (TG_OP = 'UPDATE') THEN
        v_old_data := to_jsonb(OLD) - 'password_has';
        v_new_data := to_jsonb(NEW) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_anteriores, dados_novos)
        VALUES ('UPDATE', v_app_user_id, v_old_data, v_new_data);
        RETURN NEW;
        
    ELSIF (TG_OP = 'DELETE') THEN
        v_old_data := to_jsonb(OLD) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_anteriores, dados_novos)
        VALUES ('DELETE', v_app_user_id, v_old_data, NULL);
        RETURN OLD;
        
    ELSIF (TG_OP = 'INSERT') THEN
        v_new_data := to_jsonb(NEW) - 'password_hash';
        INSERT INTO log_auditoria_usuarios (operacao, app_user_id, dados_anteriores, dados_novos)
        VALUES ('INSERT', v_app_user_id, NULL, v_new_data);
        RETURN NEW;
    END IF;
    
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER trg_log_operacoes_usuarios
AFTER INSERT OR UPDATE OR DELETE ON usuarios
FOR EACH ROW EXECUTE FUNCTION trg_audita_usuarios();

CREATE OR REPLACE FUNCTION trg_func_hash_senha()
RETURNS TRIGGER AS $$
BEGIN
    -- Se o campo de senha estiver vazio/nulo, não faz nada
    IF NEW.password_hash IS NULL THEN
        RETURN NEW;
    END IF;

    -- Proteção contra "Duplo Hash": Só aplica a criptografia se a string NÃO começar com o padrão bcrypt ($2...)
    IF NEW.password_hash NOT LIKE '$2%' THEN
        NEW.password_hash = crypt(NEW.password_hash, gen_salt('bf'));
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER trg_protege_senha_usuario
BEFORE INSERT OR UPDATE OF password_hash
ON usuarios
FOR EACH ROW
EXECUTE FUNCTION trg_func_hash_senha();

-- AJUSTES NA TABELA DE CONHECIMENTO
ALTER TABLE base_conhecimento 
ADD COLUMN IF NOT EXISTS qtd_upvotes INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS qtd_visualizacoes INTEGER DEFAULT 0;

-- AJUSTES NA TABELA DE USUARIOS (Para persistir o progresso)
ALTER TABLE usuarios 
ADD COLUMN IF NOT EXISTS xp_total INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS medalha_atual VARCHAR(100) DEFAULT 'Iniciante 🌱';

-- TABELA DE VOTOS (Evita fraude e mede qualidade real)
CREATE TABLE IF NOT EXISTS base_conhecimento_votos (
    id SERIAL PRIMARY KEY,
    id_conhecimento INTEGER REFERENCES base_conhecimento(id) ON DELETE CASCADE,
    id_analista_votante INTEGER REFERENCES usuarios(id),
    data_voto TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_conhecimento, id_analista_votante)
);

ALTER TABLE base_conhecimento 
ADD COLUMN IF NOT EXISTS data_ocorrido DATE DEFAULT CURRENT_DATE;



CREATE OR REPLACE FUNCTION atualizar_xp_usuario()
RETURNS TRIGGER AS $$
DECLARE
    v_id_autor INTEGER;
    v_xp_calculado INTEGER;
    v_nova_medalha VARCHAR(100);
BEGIN
    -- Identificar o autor
    IF (TG_TABLE_NAME = 'base_conhecimento') THEN
        v_id_autor := NEW.id_analista_autor;
    ELSIF (TG_TABLE_NAME = 'base_conhecimento_votos') THEN
        SELECT id_analista_autor INTO v_id_autor FROM base_conhecimento 
        WHERE id = COALESCE(NEW.id_conhecimento, OLD.id_conhecimento);
    END IF;

    -- RECALCULAR XP COM REGRA TEMPORAL + BÔNUS DE QUALIDADE (UPVOTES)
    SELECT 
        SUM(
            CASE 
                WHEN (EXTRACT(DAY FROM (criado_em - data_ocorrido)) <= 7) THEN 100
                WHEN (EXTRACT(DAY FROM (criado_em - data_ocorrido)) <= 14) THEN 50
                WHEN (EXTRACT(DAY FROM (criado_em - data_ocorrido)) <= 21) THEN 25
                ELSE 0 
            END
        ) + (COALESCE(SUM(qtd_upvotes), 0) * 20)
    INTO v_xp_calculado
    FROM base_conhecimento 
    WHERE id_analista_autor = v_id_autor AND status = 'APROVADO';

    -- NOVA HIERARQUIA DE PATENTES (1k a 1M XP)
    IF v_xp_calculado >= 1000000 THEN v_nova_medalha := 'Expert';
    ELSIF v_xp_calculado >= 950000 THEN v_nova_medalha := 'Lenda do Suporte';
    ELSIF v_xp_calculado >= 850000 THEN v_nova_medalha := 'Referência Técnica';
    ELSIF v_xp_calculado >= 700000 THEN v_nova_medalha := 'Analista Mestre';
    ELSIF v_xp_calculado >= 550000 THEN v_nova_medalha := 'Analista Pleno';
    ELSIF v_xp_calculado >= 400000 THEN v_nova_medalha := 'Analista Jr';
    ELSIF v_xp_calculado >= 250000 THEN v_nova_medalha := 'Especialista Sênior';
    ELSIF v_xp_calculado >= 150000 THEN v_nova_medalha := 'Especialista N2';
    ELSIF v_xp_calculado >= 100000 THEN v_nova_medalha := 'Especialista N1';
    ELSIF v_xp_calculado >= 75000  THEN v_nova_medalha := 'Contribuidor Pleno';
    ELSIF v_xp_calculado >= 50000  THEN v_nova_medalha := 'Contribuidor Ativo';
    ELSIF v_xp_calculado >= 20000  THEN v_nova_medalha := 'Contribuidor Jr';
    ELSIF v_xp_calculado >= 10000  THEN v_nova_medalha := 'Novato Consistente';
    ELSIF v_xp_calculado >= 5000   THEN v_nova_medalha := 'Novato Proativo';
    ELSIF v_xp_calculado >= 1000   THEN v_nova_medalha := 'Novato Aspirante';
    ELSE v_nova_medalha := 'Estagiário';
    END IF;

    -- Atualização no Banco
    UPDATE usuarios 
    SET xp_total = COALESCE(v_xp_calculado, 0), 
        medalha_atual = v_nova_medalha 
    WHERE id = v_id_autor;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;


-- Garante o trigger na tabela de contribuições
DROP TRIGGER IF EXISTS trg_atualizar_xp_base ON base_conhecimento;
CREATE TRIGGER trg_atualizar_xp_base
AFTER INSERT OR UPDATE ON base_conhecimento
FOR EACH ROW EXECUTE FUNCTION atualizar_xp_usuario();

-- Garante o trigger na tabela de votos (se houver)
DROP TRIGGER IF EXISTS trg_atualizar_xp_votos ON base_conhecimento_votos;
CREATE TRIGGER trg_atualizar_xp_votos
AFTER INSERT OR UPDATE OR DELETE ON base_conhecimento_votos
FOR EACH ROW EXECUTE FUNCTION atualizar_xp_usuario();


DO $$ 
DECLARE 
    r RECORD;
    xp_total_calc bigint;
    patente_calc text;
BEGIN
    -- Loop por todos os usuários que possuem ao menos uma contribuição aprovada
    FOR r IN (SELECT DISTINCT id_analista_autor FROM base_conhecimento WHERE status = 'APROVADO') 
    LOOP
        -- 1. Calcula o XP Total (Agilidade + Upvotes)
        SELECT 
            COALESCE(SUM(
                CASE 
                    WHEN (criado_em::date - data_ocorrido::date <= 7) THEN 100
                    WHEN (criado_em::date - data_ocorrido::date <= 14) THEN 50
                    WHEN (criado_em::date - data_ocorrido::date <= 21) THEN 25
                    ELSE 0 
                END
            ), 0) + (COALESCE(SUM(qtd_upvotes), 0) * 20)
        INTO xp_total_calc
        FROM base_conhecimento 
        WHERE id_analista_autor = r.id_analista_autor AND status = 'APROVADO';

        -- 2. Define o Nome da Patente (Texto puro para facilitar busca no Python)
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

        -- 3. Atualiza o cadastro do Analista
        UPDATE usuarios 
        SET xp_total = xp_total_calc, 
            medalha_atual = patente_calc 
        WHERE id = r.id_analista_autor;
    END LOOP;
END $$;


-- =================================================================================
-- FIM DO SCRIPT
-- =================================================================================