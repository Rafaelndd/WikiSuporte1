-- Itens de release: um registro por linha de nota + número de chamado (ex.: bullet + (13645))
CREATE TABLE IF NOT EXISTS release_itens (
    id_item SERIAL PRIMARY KEY,
    id_release INTEGER NOT NULL REFERENCES releases(id_release) ON DELETE CASCADE,
    nr_chamado INTEGER NOT NULL,
    linha_nota TEXT,
    versao VARCHAR(80),
    titulo_release TEXT,
    data_liberacao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    autor VARCHAR(255),
    origem VARCHAR(32) DEFAULT 'manual',
    criado_em TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_release, nr_chamado, linha_nota)
);

CREATE INDEX IF NOT EXISTS idx_release_itens_nr ON release_itens(nr_chamado);
CREATE INDEX IF NOT EXISTS idx_release_itens_release ON release_itens(id_release);

COMMENT ON TABLE release_itens IS 'Uma linha por chamado citado no release; reincidência = COUNT(DISTINCT id_release) por nr_chamado > 1';
COMMENT ON TABLE releases_tecnuv IS 'Legado: releases raspados (modelo antigo); preferir releases + release_itens + ciclos_homologacao';
COMMENT ON TABLE chamados_corrigidos_releases IS 'Legado N:N chamado x release_tecnuv; homologação usa releases + ciclos_homologacao';
