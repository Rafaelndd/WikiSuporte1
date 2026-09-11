-- Adiciona indices em colunas de FK que nao tinham nenhum indice de suporte
-- (levantamento por introspeccao em pg_constraint/pg_index no banco
-- restaurado a partir do dump de producao -- 30 colunas).
--
-- Cada indice e guardado por uma checagem em information_schema.columns em
-- vez de assumir que a tabela/coluna existe: duas delas
-- (atendimentos_suporte.cliente_identificado_id e
-- chamados_tecnuv.id_cliente) existem no banco de producao mas nao sao
-- criadas por nenhum script deste repositorio nem por um modelo ORM em
-- modules/models.py -- schema aplicado por um caminho nao documentado. Sem
-- a checagem, rodar este script contra uma instalacao nova (sem essas
-- colunas) falharia.
--
-- Idempotente: CREATE INDEX IF NOT EXISTS.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimento_anexos' AND column_name='atendimento_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimento_anexos_atendimento_id ON atendimento_anexos(atendimento_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimentos_goto' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimentos_goto_id_analista_epsy ON atendimentos_goto(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimentos_multi360' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimentos_multi360_id_analista_epsy ON atendimentos_multi360(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimentos_registrados' AND column_name='contato_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimentos_registrados_contato_id ON atendimentos_registrados(contato_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimentos_registrados' AND column_name='telefone_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimentos_registrados_telefone_id ON atendimentos_registrados(telefone_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='atendimentos_suporte' AND column_name='cliente_identificado_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_atendimentos_suporte_cliente_identificado_id ON atendimentos_suporte(cliente_identificado_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='base_conhecimento' AND column_name='id_avaliador') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_base_conhecimento_id_avaliador ON base_conhecimento(id_avaliador)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='chamados_corrigidos_releases' AND column_name='id_release') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_chamados_corrigidos_releases_id_release ON chamados_corrigidos_releases(id_release)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='chamados_tecnuv' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_chamados_tecnuv_id_analista_epsy ON chamados_tecnuv(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='chamados_tecnuv' AND column_name='id_cliente') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_chamados_tecnuv_id_cliente ON chamados_tecnuv(id_cliente)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='clientes_contatos' AND column_name='id_cliente') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_clientes_contatos_id_cliente ON clientes_contatos(id_cliente)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='clientes_crm' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_clientes_crm_id_analista_epsy ON clientes_crm(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='clientes_vinculados_chamado' AND column_name='id_cliente') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_clientes_vinculados_chamado_id_cliente ON clientes_vinculados_chamado(id_cliente)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='clientes_vinculados_chamado' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_clientes_vinculados_chamado_nr_chamado ON clientes_vinculados_chamado(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cobrancas_chamados' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_cobrancas_chamados_nr_chamado ON cobrancas_chamados(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_buscas_psy' AND column_name='usuario_id') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_buscas_psy_usuario_id ON historico_buscas_psy(usuario_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_interacoes' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_interacoes_id_analista_epsy ON historico_interacoes(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_transicao_status' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_transicao_status_id_analista_epsy ON historico_transicao_status(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_transicao_status' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_transicao_status_nr_chamado ON historico_transicao_status(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_transicao_tickets' AND column_name='nr_ticket') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_transicao_tickets_nr_ticket ON historico_transicao_tickets(nr_ticket)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_transicoes_status' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_transicoes_status_id_analista_epsy ON historico_transicoes_status(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='historico_transicoes_status' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_historico_transicoes_status_nr_chamado ON historico_transicoes_status(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='logs_auditoria_dados_tabelas' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_logs_auditoria_dados_tabelas_id_analista_epsy ON logs_auditoria_dados_tabelas(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='logs_auditoria_sistema' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_logs_auditoria_sistema_id_analista_epsy ON logs_auditoria_sistema(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='plantoes_epsy' AND column_name='id_analista_epsy') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_plantoes_epsy_id_analista_epsy ON plantoes_epsy(id_analista_epsy)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='registro_atendimentos' AND column_name='id_analista') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_registro_atendimentos_id_analista ON registro_atendimentos(id_analista)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='registro_atendimentos' AND column_name='id_cliente') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_registro_atendimentos_id_cliente ON registro_atendimentos(id_cliente)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='release_chamados_correcao' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_release_chamados_correcao_nr_chamado ON release_chamados_correcao(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='releases_tecnuv' AND column_name='nr_chamado') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_releases_tecnuv_nr_chamado ON releases_tecnuv(nr_chamado)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='user_xp_events' AND column_name='id_base_conhecimento') THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_user_xp_events_id_base_conhecimento ON user_xp_events(id_base_conhecimento)';
    END IF;
END $$;
