-- usuarios.username é usada como credencial de login (ver
-- services/wiki_authenticator.py) mas não tinha UNIQUE — dois usuários
-- poderiam colidir no mesmo username. Confirmado por introspecção no banco
-- restaurado a partir do dump de produção: 14/14 usuários já têm username
-- preenchido e não há duplicatas, então é seguro aplicar diretamente, sem
-- necessidade de backfill.
--
-- NOT NULL propositalmente NÃO é adicionada aqui: cadastro_usuarios.py
-- (linha ~112) grava username = NULL de propósito quando o operador não
-- informa um login curto — o usuário passa a logar apenas pelo campo
-- `nome` (ver login_aliases_and_display em services/wiki_authenticator.py,
-- que já trata username como opcional). UNIQUE não é afetado por isso:
-- Postgres não considera múltiplos NULLs como colisão entre si.
--
-- Idempotente: o DO block abaixo só aplica a constraint se ela ainda não
-- existir.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'usuarios'::regclass AND conname = 'usuarios_username_key'
    ) THEN
        ALTER TABLE usuarios ADD CONSTRAINT usuarios_username_key UNIQUE (username);
    END IF;
END $$;
