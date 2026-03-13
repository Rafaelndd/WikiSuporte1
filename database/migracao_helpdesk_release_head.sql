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
