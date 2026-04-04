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
    pontos_evento_passado INTEGER NOT NULL DEFAULT 125,
    multiplicador_diario_apos_qtd INTEGER NOT NULL DEFAULT 3,
    multiplicador_diario_valor INTEGER NOT NULL DEFAULT 2,
    bonus_semanal_meta_qtd INTEGER NOT NULL DEFAULT 15,
    bonus_semanal_meta_pontos INTEGER NOT NULL DEFAULT 1000,
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

    v_xp := COALESCE(v_contrib, 0) + COALESCE(v_ev, 0);

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
