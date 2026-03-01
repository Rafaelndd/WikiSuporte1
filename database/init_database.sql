-- =================================================================================
-- PROJETO: WikiSuporte / Oráculo ERP (Psy)
-- AUTOR: Rafael Duarte Nascimento
-- DESCRIÇÃO: Script Oficial de Inicialização do Banco de Dados PostgreSQL
-- =================================================================================

-- Extensões Úteis
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =================================================================================
-- 1. INFRAESTRUTURA BASE E CONFIGURAÇÕES
-- =================================================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'suporte',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuracoes_robo (
    chave VARCHAR(50) PRIMARY KEY,
    valor VARCHAR(255) NOT NULL,
    descricao TEXT,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO configuracoes_robo (chave, valor, descricao) 
VALUES 
    ('robo_ativo', 'false', 'Liga/Desliga a varredura automática'),
    ('intervalo_minutos', '60', 'Tempo de hibernação do robô')
ON CONFLICT (chave) DO NOTHING;

-- =================================================================================
-- 2. PLANTÕES DA EQUIPE EPSY (Corrigido com SERIAL)
-- =================================================================================
CREATE TABLE IF NOT EXISTS plantoes_epsy (
    id_plantao SERIAL PRIMARY KEY,
    nome_plantonista VARCHAR(255) NOT NULL,
    id_usuario_epsy INTEGER,
    data_hora_entrada TIMESTAMP,
    data_hora_saida TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =================================================================================
-- 3. CHAMADOS TECNUV (O Fornecedor)
-- =================================================================================
CREATE TABLE IF NOT EXISTS chamados_tecnuv (
    nr_chamado INTEGER PRIMARY KEY,
    cliente_nome VARCHAR(255),
    ticket_vinculado VARCHAR(50),
    versao_sistema VARCHAR(50),
    assunto_html TEXT,
    motivo_abertura_html TEXT,
    atendente_tecnuv VARCHAR(100),
    nome_analista_epsy VARCHAR(100), -- Nomenclatura atualizada conforme solicitado
    setor VARCHAR(100),
    status_atual VARCHAR(100) NOT NULL,
    situacao VARCHAR(100),
    prioridade VARCHAR(50),
    data_abertura TIMESTAMP,
    ultima_alteracao_tecnuv TIMESTAMP,
    assunto_encerramento TEXT,
    data_encerramento TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_transicao_status (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE
);

-- =================================================================================
-- 4. TICKETS EPSY (Operação Interna)
-- =================================================================================
CREATE TABLE IF NOT EXISTS tickets_epsy (
    nr_ticket INTEGER PRIMARY KEY, -- O ID do ticket interno
    cliente_nome VARCHAR(255),
    assunto TEXT,
    nome_analista_epsy VARCHAR(100), -- Coluna atualizada conforme o seu pedido
    status_atual VARCHAR(100) NOT NULL,
    data_abertura TIMESTAMP,
    data_ultima_interacao TIMESTAMP,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS historico_transicao_tickets (
    id SERIAL PRIMARY KEY,
    nr_ticket INTEGER NOT NULL,
    status_anterior VARCHAR(100),
    status_novo VARCHAR(100) NOT NULL,
    data_mudanca TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ticket FOREIGN KEY (nr_ticket) REFERENCES tickets_epsy(nr_ticket) ON DELETE CASCADE
);

-- =================================================================================
-- 5. CONTROLE DE RELEASES E REINCIDÊNCIA
-- =================================================================================
CREATE TABLE IF NOT EXISTS releases_tecnuv (
    id_release SERIAL PRIMARY KEY,
    titulo_versao VARCHAR(255) NOT NULL,
    autor_data VARCHAR(255),
    texto_completo TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chamados_corrigidos_releases (
    nr_chamado INTEGER,
    id_release INTEGER,
    PRIMARY KEY (nr_chamado, id_release),
    CONSTRAINT fk_chamado_rel FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE,
    CONSTRAINT fk_release FOREIGN KEY (id_release) REFERENCES releases_tecnuv(id_release) ON DELETE CASCADE
);

-- =================================================================================
-- 6. BASE DE CONHECIMENTO E GAMIFICAÇÃO (Módulo Psy)
-- =================================================================================
CREATE TABLE IF NOT EXISTS usuarios_gamificacao (
    usuario_id SERIAL PRIMARY KEY,
    nome_analista_epsy VARCHAR(100) UNIQUE,
    pontos_xp INTEGER DEFAULT 0,
    nivel VARCHAR(50) DEFAULT 'Aprendiz',
    artigos_aprovados INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS base_conhecimento (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    conteudo TEXT NOT NULL,
    tipo_origem VARCHAR(50), 
    autor_usuario VARCHAR(100),
    revisor_usuario VARCHAR(100),
    feedback_revisao TEXT,
    status VARCHAR(50) DEFAULT 'Pendente', 
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 1. EXTENSÕES PARA LGPD (Criptografia)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. CLIENTES E CRM (Com LGPD)
CREATE TABLE IF NOT EXISTS clientes_crm (
    id_cliente SERIAL PRIMARY KEY,
    razao_social VARCHAR(255),
    cnpj_criptografado BYTEA, -- LGPD: Guardado com PGP_SYM_ENCRYPT
    email_criptografado BYTEA
);

CREATE TABLE IF NOT EXISTS clientes_telefones (
    id_telefone SERIAL PRIMARY KEY,
    id_cliente INTEGER REFERENCES clientes_crm(id_cliente),
    numero_criptografado BYTEA, -- LGPD
    origem_dado VARCHAR(50) -- 'GoTo', 'Multi360', 'Manual'
);

-- 3. INTERAÇÕES E COBRANÇAS (1 para N com os Chamados)
CREATE TABLE IF NOT EXISTS historico_interacoes (
    id_interacao SERIAL PRIMARY KEY,
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado),
    nome_analista_epsy VARCHAR(100),
    data_interacao TIMESTAMP,
    descricao_texto TEXT
);

CREATE TABLE IF NOT EXISTS cobrancas_chamados (
    id_cobranca SERIAL PRIMARY KEY,
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado),
    nome_analista_epsy VARCHAR(100),
    data_cobranca TIMESTAMP,
    meio_contato VARCHAR(50) -- 'WhatsApp', 'Email', 'Telefone'
);

-- 4. VÍNCULOS MÚLTIPLOS (O mesmo chamado afeta vários postos)
CREATE TABLE IF NOT EXISTS clientes_vinculados_chamado (
    nr_chamado INTEGER REFERENCES chamados_tecnuv(nr_chamado),
    id_cliente INTEGER REFERENCES clientes_crm(id_cliente),
    PRIMARY KEY (nr_chamado, id_cliente)
);

-- 5. AUDITORIA (Rastreabilidade Total)
CREATE TABLE IF NOT EXISTS logs_auditoria_dados_tabelas (
    id_log SERIAL PRIMARY KEY,
    tabela_afetada VARCHAR(100),
    operacao VARCHAR(10), -- 'INSERT', 'UPDATE', 'DELETE'
    usuario_banco VARCHAR(100),
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    dados_antigos JSONB,
    dados_novos JSONB
);

-- =================================================================================
-- 7. ÍNDICES E TRIGGERS DE PERFORMANCE
-- =================================================================================
CREATE INDEX IF NOT EXISTS idx_chamados_status ON chamados_tecnuv(status_atual);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets_epsy(status_atual);

CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trg_atualiza_chamado BEFORE UPDATE ON chamados_tecnuv FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
CREATE TRIGGER trg_atualiza_ticket BEFORE UPDATE ON tickets_epsy FOR EACH ROW EXECUTE PROCEDURE update_modified_column();


--===================================================================================     

-- 1. Renomear a tabela principal de utilizadores
ALTER TABLE usuarios_dashboard RENAME TO usuarios;

-- 2. Garantir que a PK da tabela usuarios se chama 'id' (ou ajustar conforme o seu banco)
-- Assumindo que a PK de 'usuarios' é 'id'.

-- =========================================================================
-- FUNÇÃO AUXILIAR: Adicionar colunas caso não existam (Evita erros no script)
-- Como o banco está populado, adicionamos sem NOT NULL primeiro.
-- =========================================================================

-- Tabela: atendimentos_goto
ALTER TABLE atendimentos_goto RENAME COLUMN id_usuario_epsy TO id_analista_epsy;
-- Se a coluna nome não existir, criamos:
ALTER TABLE atendimentos_goto ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE atendimentos_goto ADD CONSTRAINT fk_goto_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: atendimentos_multi360
ALTER TABLE atendimentos_multi360 RENAME COLUMN id_usuario_epsy TO id_analista_epsy;
ALTER TABLE atendimentos_multi360 ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE atendimentos_multi360 ADD CONSTRAINT fk_multi360_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: chamados_tecnuv
-- (Assumindo que já renomeamos operador_nome para nome_analista_epsy antes, mas garantimos o ID)
ALTER TABLE chamados_tecnuv ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE chamados_tecnuv ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE chamados_tecnuv ADD CONSTRAINT fk_chamados_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: clientes_crm
-- Registrar quem cadastrou o contato
ALTER TABLE clientes_crm ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE clientes_crm ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE clientes_crm ADD CONSTRAINT fk_crm_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: historico_interacoes
ALTER TABLE historico_interacoes ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE historico_interacoes ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE historico_interacoes ADD CONSTRAINT fk_interacoes_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: historico_transicoes_status
ALTER TABLE historico_transicoes_status ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE historico_transicoes_status ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE historico_transicoes_status ADD CONSTRAINT fk_transicoes_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabelas de Logs (Assumindo os nomes exatos)
ALTER TABLE logs_auditoria_dados_tabelas ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE logs_auditoria_dados_tabelas ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE logs_auditoria_dados_tabelas ADD CONSTRAINT fk_logs_dados_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

ALTER TABLE logs_auditoria_sistema ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE logs_auditoria_sistema ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE logs_auditoria_sistema ADD CONSTRAINT fk_logs_sistema_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: plantoes_epsy
ALTER TABLE plantoes_epsy RENAME COLUMN id_usuario_epsy TO id_analista_epsy;
ALTER TABLE plantoes_epsy RENAME COLUMN nome_plantonista TO nome_analista_epsy;
ALTER TABLE plantoes_epsy ADD CONSTRAINT fk_plantoes_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;

-- Tabela: tickets_epsy
ALTER TABLE tickets_epsy ADD COLUMN IF NOT EXISTS id_analista_epsy INTEGER;
ALTER TABLE tickets_epsy ADD COLUMN IF NOT EXISTS nome_analista_epsy VARCHAR(100);
ALTER TABLE tickets_epsy ADD CONSTRAINT fk_tickets_analista FOREIGN KEY (id_analista_epsy) REFERENCES usuarios(id) NOT VALID;


-- Garantir que as tabelas possuem a coluna nr_chamado (INTEGER) e criar a FK

-- Tabela: historico_interacoes
ALTER TABLE historico_interacoes ADD COLUMN IF NOT EXISTS nr_chamado INTEGER;
ALTER TABLE historico_interacoes ADD CONSTRAINT fk_interacoes_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE NOT VALID;

-- Tabela: chamados_corrigidos_releases
-- Assumindo que a coluna nr_chamado já existe (da nossa modelagem anterior)
ALTER TABLE chamados_corrigidos_releases ADD CONSTRAINT fk_corrigidos_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE NOT VALID;

-- Tabela: clientes_vinculados_chamado
ALTER TABLE clientes_vinculados_chamado ADD COLUMN IF NOT EXISTS nr_chamado INTEGER;
ALTER TABLE clientes_vinculados_chamado ADD CONSTRAINT fk_vinculados_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE NOT VALID;

-- Tabela: cobrancas_chamados
ALTER TABLE cobrancas_chamados ADD COLUMN IF NOT EXISTS nr_chamado INTEGER;
ALTER TABLE cobrancas_chamados ADD CONSTRAINT fk_cobrancas_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE NOT VALID;

-- Tabela: release_chamados_correcao
ALTER TABLE release_chamados_correcao ADD COLUMN IF NOT EXISTS nr_chamado INTEGER;
ALTER TABLE release_chamados_correcao ADD CONSTRAINT fk_rel_correcao_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE NOT VALID;

-- Tabela: releases_tecnuv
-- ATENÇÃO: Um release tem VÁRIOS chamados. Colocar nr_chamado aqui restringe 1 release a 1 chamado.
-- Como você pediu explicitamente, vou adicionar, mas a boa prática é usar a tabela 'chamados_corrigidos_releases' como ponte.
ALTER TABLE releases_tecnuv ADD COLUMN IF NOT EXISTS nr_chamado INTEGER;
ALTER TABLE releases_tecnuv ADD CONSTRAINT fk_releases_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE SET NULL NOT VALID;

-- =========================================================================
-- ATUALIZAÇÃO EM MASSA: VÍNCULO DOS ANALISTAS (GoTo)
-- =========================================================================

UPDATE atendimentos_goto ag
SET 
    id_analista_epsy = u.id,
    nome_analista_epsy = u.nome
FROM usuarios u
WHERE 
    -- A Mágica: Procura exatamente o padrão "5332: 5332" em qualquer lugar do texto
    ag.participantes LIKE '%' || u.ramal || ': ' || u.ramal || '%'
    
    -- Segurança: Só atualiza se o usuário realmente tiver um ramal cadastrado
    AND u.ramal IS NOT NULL 
    AND u.ramal <> ''
    
    -- Segurança: Só tenta atualizar os que ainda estão vazios
    AND ag.id_analista_epsy IS NULL;


    -- 1. APAGA A TABELA ANTIGA DE TICKETS
DROP TABLE IF EXISTS tickets_epsy CASCADE;

-- 2. RECRIA A TABELA COM TODAS AS COLUNAS DO DEEP SCRAPING
CREATE TABLE tickets_epsy (
    nr_ticket INTEGER PRIMARY KEY,          -- O ID oficial do sistema da Tecnuv
    cliente_nome VARCHAR(255),
    assunto TEXT,
    data_abertura TIMESTAMP,
    nome_analista_epsy VARCHAR(100),        -- Quem abriu (Texto)
    id_analista_epsy INTEGER,               -- Quem abriu (ID cruzado com a EPSY)
    status_atual VARCHAR(100) NOT NULL,
    chamado_vinculado INTEGER,              -- FK para a tabela chamados_tecnuv (se quiser)
    tempo_aberto_str VARCHAR(100),          -- Ex: "3 Dias 0 Horas"
    avaliacao VARCHAR(50),                  -- Ex: "5"
    data_ultima_interacao TIMESTAMP,
    ultima_mensagem TEXT,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- (Opcional, mas recomendado) Recria a trigger que atualiza o "atualizado_em" automaticamente
DROP TRIGGER IF EXISTS trg_atualiza_ticket ON tickets_epsy;
CREATE TRIGGER trg_atualiza_ticket 
    BEFORE UPDATE ON tickets_epsy 
    FOR EACH ROW 
    EXECUTE PROCEDURE update_modified_column();



-- 1. ENSINA O BANCO COMO ATUALIZAR A HORA (A Função)
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 2. AMARRA A FUNÇÃO À TABELA DE TICKETS (O Gatilho)
DROP TRIGGER IF EXISTS trg_atualiza_ticket ON tickets_epsy;

CREATE TRIGGER trg_atualiza_ticket 
    BEFORE UPDATE ON tickets_epsy 
    FOR EACH ROW 
    EXECUTE PROCEDURE update_modified_column();


-- =========================================================================
-- O CÉREBRO DA IA: TABELA UNIFICADA DE CONHECIMENTO (RAG)
-- =========================================================================

CREATE TABLE IF NOT EXISTS base_conhecimento (
    id SERIAL PRIMARY KEY,                  -- O ID interno do nosso sistema (Garantido pela sua regra)
    nr_documento INTEGER,                   -- A coluna '#' da Tecnuv (Pode ser NULL para criações internas)
    origem VARCHAR(50) NOT NULL,            -- 'MANUAL_HELPDESK', 'WIKI_HELPDESK', 'CONHECIMENTO_SUPORTE'
    
    titulo VARCHAR(255) NOT NULL,
    categoria VARCHAR(100),
    subcategoria VARCHAR(100),
    
    conteudo TEXT NOT NULL,                 -- Texto da Wiki/Suporte ou a URL do PDF do Manual
    id_analista_autor INTEGER,              -- FK para a tabela de usuarios (Quem criou a dica interna)
    
    status VARCHAR(50) DEFAULT 'APROVADO',  -- 'RASCUNHO', 'APROVADO', 'DESATUALIZADO'
    
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- =========================================================================
    -- REGRAS DE INTEGRIDADE (A sua trava contra duplicatas)
    -- =========================================================================
    -- 1. Garante que nunca teremos dois Manuais da Tecnuv com o mesmo Número (#)
    -- O PostgreSQL é inteligente: Ele aplica o UNIQUE apenas se o nr_documento NÃO for nulo.
    -- Ou seja, ele trava duplicatas da Tecnuv, mas permite que os analistas criem artigos sem número!
    CONSTRAINT unique_doc_origem UNIQUE (origem, nr_documento),
    
    -- 2. Conecta a tabela ao autor (se for conhecimento interno)
    CONSTRAINT fk_base_autor FOREIGN KEY (id_analista_autor) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- Recria a Trigger para manter a data de atualização automática
DROP TRIGGER IF EXISTS trg_atualiza_conhecimento ON base_conhecimento;
CREATE TRIGGER trg_atualiza_conhecimento 
    BEFORE UPDATE ON base_conhecimento 
    FOR EACH ROW 
    EXECUTE PROCEDURE update_modified_column();


-- 1. Excluímos as tabelas antigas com segurança (CASCADE garante que as constraints antigas sumam)
DROP TABLE IF EXISTS cobrancas_chamados CASCADE;
DROP TABLE IF EXISTS clientes_vinculados_chamado CASCADE;

-- 2. Recriamos a tabela de Clientes Vinculados
CREATE TABLE clientes_vinculados_chamado (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL,
    nome_cliente VARCHAR(255) NOT NULL,
    cnpj_cliente VARCHAR(25), -- Para quando a Tecnuv enviar o CNPJ junto com o nome
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_vinculados_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE
);

-- 3. Recriamos a tabela de Cobranças
CREATE TABLE cobrancas_chamados (
    id SERIAL PRIMARY KEY,
    nr_chamado INTEGER NOT NULL,
    data_cobranca TIMESTAMP,
    analista_epsy VARCHAR(100), -- Ex: "Emil"
    cliente_solicitante VARCHAR(255), -- Ex: "TORRE ALTA COMERCIO DE COMBUSTIVEIS LTDA"
    texto_bruto_cobranca TEXT, -- Salvamos o texto original do HTML por segurança e auditoria
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_cobrancas_chamado FOREIGN KEY (nr_chamado) REFERENCES chamados_tecnuv(nr_chamado) ON DELETE CASCADE
);

-- 4. Adicionamos a coluna de Previsão na tabela principal (se ainda não existir)
ALTER TABLE chamados_tecnuv ADD COLUMN IF NOT EXISTS previsao_conclusao DATE;