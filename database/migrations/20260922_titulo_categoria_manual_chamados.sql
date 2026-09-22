-- Adiciona coluna "titulo" (texto curto da grade TecNuv, usado para classificação
-- automática por palavra-chave) e "categoria_manual" (classificação escolhida por um
-- usuário, sempre com prioridade sobre categoria_ia) em chamados_tecnuv.
--
-- Idempotente: ADD COLUMN IF NOT EXISTS.

ALTER TABLE chamados_tecnuv
    ADD COLUMN IF NOT EXISTS titulo TEXT;

ALTER TABLE chamados_tecnuv
    ADD COLUMN IF NOT EXISTS categoria_manual TEXT;
