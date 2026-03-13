-- WikiSuporte: status OBSOLETO + qtd_tentativas em base_conhecimento
-- Execute uma vez no PostgreSQL.

ALTER TABLE base_conhecimento
  ADD COLUMN IF NOT EXISTS qtd_tentativas INTEGER DEFAULT 1;

COMMENT ON COLUMN base_conhecimento.status IS
  'PENDENTE | APROVADO | REJEITADO | OBSOLETO (visível na base; autor deve atualizar; após edição volta PENDENTE)';

-- Opcional: normalizar registros antigos que sumiam da listagem
UPDATE base_conhecimento
SET status = 'OBSOLETO',
    motivo_rejeicao = COALESCE(NULLIF(TRIM(motivo_rejeicao), ''), '[Migrado] Marcado para revisão.')
WHERE origem = 'CONHECIMENTO_SUPORTE' AND status = 'REVISAO_PENDENTE';
