-- WikiSuporte — migração: campos para gestão de usuários (fase 1)
-- Executar contra a base já existente (idempotente).
-- Não altera password_hash nem nomes de login: preenche `username` a partir de `nome`
-- quando vazio, mantendo compatibilidade com streamlit-authenticator / wiki_authenticator.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS username VARCHAR(150);
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_ferias BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_atendimento_externo BOOLEAN DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS caminho_foto_perfil VARCHAR(500) DEFAULT '';

COMMENT ON COLUMN usuarios.username IS 'Login curto (minúsculas recomendado); autenticação aceita também nome.';
COMMENT ON COLUMN usuarios.em_ferias IS 'Indicador operacional; default false.';
COMMENT ON COLUMN usuarios.em_atendimento_externo IS 'Indicador operacional; default false.';
COMMENT ON COLUMN usuarios.caminho_foto_perfil IS 'Caminho ou URL da foto; vazio se não houver.';

-- Retrocompatibilidade: quem só tinha `nome` como identificador continua a autenticar pelo nome;
-- `username` espelha o nome normalizado para o novo modelo.
UPDATE usuarios
SET username = lower(trim(nome))
WHERE username IS NULL OR btrim(username) = '';
