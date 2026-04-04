-- Penalidades de contribuição (regras §11) — colunas em contribution_scoring_rules.
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS penalidade_sem_7_dias INTEGER NOT NULL DEFAULT 200;
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS minimo_semanal_sem_penalidade INTEGER NOT NULL DEFAULT 5;
ALTER TABLE contribution_scoring_rules
    ADD COLUMN IF NOT EXISTS penalidade_semana_insuficiente INTEGER NOT NULL DEFAULT 100;
