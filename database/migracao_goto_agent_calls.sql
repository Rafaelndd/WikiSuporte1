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
