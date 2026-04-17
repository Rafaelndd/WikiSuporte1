"""Testes de integração leve do serviço de aprovação (mock de conexão SQLAlchemy)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services import base_conhecimento_service as svc
from app.services.base_conhecimento_service import (
    AprovacaoContribuicaoError,
    aprovar_contribuicao_conhecimento,
)


def _row_select_for_update():
    return {
        "id": 9,
        "status": "PENDENTE",
        "origem": svc.ORIGEM_CONHECIMENTO_SUPORTE,
        "id_analista_autor": 42,
        "modalidade_contribuicao": "EVENTO_ATUAL",
        "data_ocorrido": __import__("datetime").date(2026, 4, 1),
        "criado_em": datetime(2026, 4, 3, 12, 0, 0, tzinfo=timezone.utc),
    }


def test_aprovar_rejeita_se_ja_aprovado():
    conn = MagicMock()
    first = MagicMock()
    first.mappings.return_value.one_or_none.return_value = {
        "id": 1,
        "status": "APROVADO",
        "origem": svc.ORIGEM_CONHECIMENTO_SUPORTE,
        "id_analista_autor": 1,
        "modalidade_contribuicao": "EVENTO_ATUAL",
        "data_ocorrido": __import__("datetime").date(2026, 1, 1),
        "criado_em": datetime(2026, 4, 1, tzinfo=timezone.utc),
    }
    conn.execute.return_value = first

    with pytest.raises(AprovacaoContribuicaoError, match="já está aprovada"):
        aprovar_contribuicao_conhecimento(conn, 1, 99)


def test_aprovar_fluxo_completo_sem_bonus(monkeypatch):
    conn = MagicMock()
    contrib = _row_select_for_update()

    exec_results = []

    def exec_side_effect(stmt, params=None):
        s = str(stmt)
        r = MagicMock()
        if "FOR UPDATE" in s:
            r.mappings.return_value.one_or_none.return_value = contrib
        elif "FROM contribution_scoring_rules" in s:
            r.mappings.return_value.first.return_value = {
                "pontos_evento_passado": 125,
                "multiplicador_diario_apos_qtd": 3,
                "multiplicador_diario_valor": 2,
                "bonus_semanal_meta_qtd": 15,
                "bonus_semanal_meta_pontos": 1000,
            }
        elif "COUNT(*)" in s and "DATE(timezone" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "COUNT(*)" in s and "IYYY-IW" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "to_char(timezone" in s and "CURRENT_TIMESTAMP" in s:
            r.mappings.return_value.one.return_value = {"w": "2026-14"}
        elif s.strip().upper().startswith("UPDATE BASE_CONHECIMENTO"):
            r.rowcount = 1
        elif "INSERT INTO user_xp_events" in s:
            pytest.fail("não deveria inserir bônus semanal neste cenário")
        else:
            r.mappings.return_value.one_or_none.return_value = None
        exec_results.append((s[:80], params))
        return r

    conn.execute.side_effect = exec_side_effect

    xp_res = aprovar_contribuicao_conhecimento(conn, 9, 7)

    assert xp_res.pontos_contribuicao == 100
    assert xp_res.bonus_semanal_concedido is False

    updates = [
        c
        for c in conn.execute.call_args_list
        if len(c[0]) > 1 and isinstance(c[0][1], dict) and "pts" in c[0][1]
    ]
    assert len(updates) == 1
    u_params = updates[0][0][1]
    assert u_params["pts"] == 100
    assert u_params["av"] == 7
    assert u_params["id"] == 9


def test_contar_aprovacoes_monta_sql_exclude():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.one.return_value = {"n": 3}

    n = svc.contar_aprovacoes_autor_hoje_utc(conn, 5, exclude_contribuicao_id=9)
    assert n == 3
    args = conn.execute.call_args[0]
    assert "id <> :excl" in str(args[0])
    assert args[1]["excl"] == 9


def test_aprovar_evento_passado_aplica_pontuacao_fixa_padrao():
    conn = MagicMock()
    contrib = _row_select_for_update()
    contrib["modalidade_contribuicao"] = "EVENTO_PASSADO"
    contrib["data_ocorrido"] = __import__("datetime").date(2025, 1, 1)

    def exec_side_effect(stmt, params=None):
        s = str(stmt)
        r = MagicMock()
        if "FOR UPDATE" in s:
            r.mappings.return_value.one_or_none.return_value = contrib
        elif "FROM contribution_scoring_rules" in s:
            # Sem linha de configuração: serviço deve usar defaults (evento passado = 90)
            r.mappings.return_value.first.return_value = None
        elif "COUNT(*)" in s and "DATE(timezone" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "COUNT(*)" in s and "IYYY-IW" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "to_char(timezone" in s and "CURRENT_TIMESTAMP" in s:
            r.mappings.return_value.one.return_value = {"w": "2026-14"}
        elif s.strip().upper().startswith("UPDATE BASE_CONHECIMENTO"):
            r.rowcount = 1
        elif "INSERT INTO user_xp_events" in s:
            pytest.fail("não deveria inserir bônus semanal neste cenário")
        return r

    conn.execute.side_effect = exec_side_effect

    xp_res = aprovar_contribuicao_conhecimento(conn, 9, 7)

    assert xp_res.pontos_contribuicao == 90
    assert xp_res.bonus_semanal_concedido is False
