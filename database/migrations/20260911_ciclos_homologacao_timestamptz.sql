-- Corrige a divergência de tipo entre database/init_database.sql e
-- database/migracao_ciclos_homologacao.sql para chamados, releases e
-- ciclos_homologacao: as três colunas de data estavam declaradas como
-- TIMESTAMP WITH TIME ZONE em um arquivo e TIMESTAMP (sem fuso) no outro.
-- Como CREATE TABLE IF NOT EXISTS é idempotente, a definição que rodasse
-- primeiro "vencia" silenciosamente — e em produção, quem venceu foi a
-- versão sem fuso.
--
-- Esta migração converte as três colunas para TIMESTAMPTZ, alinhando com:
--   1) a convenção usada no resto do schema (todas as outras colunas de
--      data/hora já são TIMESTAMPTZ);
--   2) o que o código de aplicação já assumia — services/db_homologacao.py
--      já fazia CAST(:data_lib AS TIMESTAMP WITH TIME ZONE) ao inserir em
--      releases.data_liberacao, mesmo com a coluna ainda sendo TIMESTAMP.
--
-- Os valores existentes são reinterpretados com `AT TIME ZONE
-- 'America/Sao_Paulo'` — confirmado como o timezone de sessão do servidor
-- (nenhum código da aplicação define timezone explicitamente), preservando
-- o horário de parede original sem deslocar nenhum valor.
--
-- Idempotente: só altera o tipo se a coluna ainda estiver sem fuso.

DO $$
BEGIN
    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'chamados' AND column_name = 'data_primeiro_registro') = 'timestamp without time zone' THEN
        ALTER TABLE chamados
            ALTER COLUMN data_primeiro_registro TYPE TIMESTAMPTZ
            USING data_primeiro_registro AT TIME ZONE 'America/Sao_Paulo';
    END IF;

    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'releases' AND column_name = 'data_liberacao') = 'timestamp without time zone' THEN
        ALTER TABLE releases
            ALTER COLUMN data_liberacao TYPE TIMESTAMPTZ
            USING data_liberacao AT TIME ZONE 'America/Sao_Paulo';
    END IF;

    IF (SELECT data_type FROM information_schema.columns
        WHERE table_name = 'ciclos_homologacao' AND column_name = 'data_teste') = 'timestamp without time zone' THEN
        ALTER TABLE ciclos_homologacao
            ALTER COLUMN data_teste TYPE TIMESTAMPTZ
            USING data_teste AT TIME ZONE 'America/Sao_Paulo';
    END IF;
END $$;
