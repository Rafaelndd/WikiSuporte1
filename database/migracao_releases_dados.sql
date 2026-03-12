-- =================================================================================
-- PROJETO: WikiSuporte - Dados completos dos releases
-- DESCRIÇÃO: Adiciona colunas para armazenar arquivo, autor, texto completo
-- =================================================================================

ALTER TABLE releases ADD COLUMN IF NOT EXISTS autor VARCHAR(255);
ALTER TABLE releases ADD COLUMN IF NOT EXISTS nome_arquivo VARCHAR(255);
ALTER TABLE releases ADD COLUMN IF NOT EXISTS texto_completo TEXT;
ALTER TABLE releases ADD COLUMN IF NOT EXISTS caminho_arquivo VARCHAR(512);

COMMENT ON COLUMN releases.autor IS 'Autor do release (cadastro manual ou Processamento Automático)';
COMMENT ON COLUMN releases.nome_arquivo IS 'Nome original do arquivo enviado';
COMMENT ON COLUMN releases.texto_completo IS 'Conteúdo textual completo do release';
COMMENT ON COLUMN releases.caminho_arquivo IS 'Caminho relativo ao projeto onde o arquivo foi salvo';
