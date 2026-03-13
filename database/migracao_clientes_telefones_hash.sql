-- Adiciona colunas para vínculo cliente-telefone com Goto/Multi360
-- clientes_crm.cnpj e clientes_telefones.numero/telefone_hash para cruzar com atendimentos

ALTER TABLE clientes_crm ADD COLUMN IF NOT EXISTS cnpj VARCHAR(18);
ALTER TABLE clientes_telefones ADD COLUMN IF NOT EXISTS numero VARCHAR(50);
ALTER TABLE clientes_telefones ADD COLUMN IF NOT EXISTS telefone_hash VARCHAR(256);

CREATE INDEX IF NOT EXISTS idx_clientes_telefones_hash ON clientes_telefones(telefone_hash);
CREATE INDEX IF NOT EXISTS idx_clientes_telefones_numero ON clientes_telefones(numero);
CREATE INDEX IF NOT EXISTS idx_clientes_crm_cnpj ON clientes_crm(cnpj);

-- Permite armazenar cliente identificado nos atendimentos
ALTER TABLE atendimentos_goto ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(255);
ALTER TABLE atendimentos_multi360 ADD COLUMN IF NOT EXISTS cliente_nome VARCHAR(255);
