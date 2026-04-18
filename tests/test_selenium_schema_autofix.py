from __future__ import annotations

import types

from modules.selenium_raspagem import OraculoBot


def test_garantir_schema_minimo_executa_alter_table_e_backfill():
    bot = OraculoBot.__new__(OraculoBot)
    comandos = []

    class _Conn:
        def execute(self, stmt):
            comandos.append(str(stmt))

    class _Ctx:
        def __enter__(self):
            return _Conn()

        def __exit__(self, exc_type, exc, tb):
            return False

    bot.engine = types.SimpleNamespace(begin=lambda: _Ctx())

    bot._garantir_schema_minimo()

    sql_concat = " ".join(comandos).lower()
    assert "alter table if exists chamados_tecnuv" in sql_concat
    assert "add column if not exists atualizado_em" in sql_concat
    assert "update chamados_tecnuv" in sql_concat
    assert "where atualizado_em is null" in sql_concat
