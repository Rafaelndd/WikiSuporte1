from __future__ import annotations

import sys
import types

from modules.selenium_raspagem import OraculoBot


def test_ler_linhas_grade_helpdesk_usa_execucao_js_em_lote():
    bot = OraculoBot.__new__(OraculoBot)
    retorno_esperado = [
        {"colunas": ["123", "Cliente X"], "html_coluna_10": "<div>01/01/2026 10:00</div>"}
    ]

    chamadas = {"qtd": 0}

    def _execute_script(script):
        chamadas["qtd"] += 1
        assert "table tbody tr" in script
        return retorno_esperado

    bot.driver = types.SimpleNamespace(execute_script=_execute_script)

    linhas = bot._ler_linhas_grade_helpdesk()

    assert chamadas["qtd"] == 1
    assert linhas == retorno_esperado


def test_script_teste_retorna_130_quando_interrompido(monkeypatch):
    from scripts import test_raspagem_chamados as script_teste

    modulo_fake = types.SimpleNamespace(
        _executar_ciclo_chamados=lambda: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    monkeypatch.setitem(sys.modules, "modules.selenium_raspagem", modulo_fake)

    codigo_saida = script_teste.main()

    assert codigo_saida == 130
