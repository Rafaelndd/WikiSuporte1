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
