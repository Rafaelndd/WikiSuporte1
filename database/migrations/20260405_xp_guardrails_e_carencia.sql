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
