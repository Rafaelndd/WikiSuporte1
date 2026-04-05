"""Testes do serviço de penalidades (isenção, valor negativo, idempotência por event_key)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import penalidades_service as ps
from app.services.penalidades_service import processar_penalidades_contribuicao


def _mock_result_mapping(data: dict | None = None, one_row: dict | None = None):
    m = MagicMock()
    if data is not None:
        m.mappings.return_value.first.return_value = data
    if one_row is not None:
        m.mappings.return_value.one.return_value = one_row
    m.mappings.return_value.all.return_value = []
    return m


def test_usuario_em_ferias_e_pulado_sem_insert_penalidade():
    """Isento: não consulta métricas nem insere penalidade."""
    conn = MagicMock()
    calls: list[str] = []

    def exec_side_effect(stmt, params=None):
        s = str(stmt)
        calls.append(s)
        r = MagicMock()
        if "FROM contribution_scoring_rules" in s:
            r.mappings.return_value.first.return_value = {
                "penalidade_sem_7_dias": 200,
                "minimo_semanal_sem_penalidade": 5,
                "penalidade_semana_insuficiente": 100,
                "janela_carencia_dias": 7,
                "max_desconto_semanal_xp": 100,
            }
        elif "to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY')" in s:
            r.mappings.return_value.one.return_value = {"ano_iso": "2026", "semana_iso": "14"}
        elif "FROM usuarios" in s and "em_ferias" in s:
            r.mappings.return_value.all.return_value = [
                {
                    "id": 7,
                    "perfil": "analista",
                    "ativo": True,
                    "em_ferias": True,
                    "em_atendimento_externo": False,
                }
            ]
        else:
            pytest.fail(f"SQL inesperado para isento: {s[:120]}")
        return r

    conn.execute.side_effect = exec_side_effect
    resumo = processar_penalidades_contribuicao(conn)

    assert resumo.usuarios_encontrados == 1
    assert resumo.isentos_pulados == 1
    assert resumo.penalidades_inseridas == 0
    inserts = [c for c in calls if "INSERT INTO user_xp_events" in c]
    assert len(inserts) == 0
    metricas = [c for c in calls if "INTERVAL '7 days'" in c]
    assert len(metricas) == 0


def test_penalidade_gravada_com_pontos_negativos():
    conn = MagicMock()

    def exec_side_effect(stmt, params=None):
        s = str(stmt)
        r = MagicMock()
        if "FROM contribution_scoring_rules" in s:
            r.mappings.return_value.first.return_value = {
                "penalidade_sem_7_dias": 200,
                "minimo_semanal_sem_penalidade": 5,
                "penalidade_semana_insuficiente": 100,
                "janela_carencia_dias": 7,
                "max_desconto_semanal_xp": 100,
            }
        elif "to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY')" in s and "IW" in s:
            r.mappings.return_value.one.return_value = {"ano_iso": "2026", "semana_iso": "14"}
        elif "FROM usuarios" in s and "em_ferias" in s:
            r.mappings.return_value.all.return_value = [
                {
                    "id": 42,
                    "perfil": "analista",
                    "ativo": True,
                    "em_ferias": False,
                    "em_atendimento_externo": False,
                }
            ]
        elif "FROM log_auditoria_usuarios" in s:
            r.fetchone.return_value = None
        elif "INTERVAL '7 days'" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "IYYY-IW" in s and "COUNT(*)" in s:
            r.mappings.return_value.one.return_value = {"n": 5}
        elif "MAX(bc.data_avaliacao)" in s:
            r.mappings.return_value.one.return_value = {"dias": 999}
        elif "INSERT INTO user_xp_events" in s:
            assert params is not None
            assert params["pts"] == -100
            assert params["uid"] == 42
            assert "PENALIDADE_SEMANA_2026_14_USER_42_SEM_7_DIAS" == params["ek"]
            r.scalar_one_or_none.return_value = 9001
        else:
            pytest.fail(f"SQL não mapeado: {s[:160]}")
        return r

    conn.execute.side_effect = exec_side_effect
    resumo = processar_penalidades_contribuicao(conn)
    assert resumo.penalidades_inseridas == 1
    assert resumo.isentos_pulados == 0


def test_event_key_impede_segundo_desconto_na_mesma_semana():
    """Segunda execução: ON CONFLICT → scalar None → contabilizado como já existia."""
    conn = MagicMock()
    insert_calls = 0

    def exec_side_effect(stmt, params=None):
        nonlocal insert_calls
        s = str(stmt)
        r = MagicMock()
        if "FROM contribution_scoring_rules" in s:
            r.mappings.return_value.first.return_value = {
                "penalidade_sem_7_dias": 200,
                "minimo_semanal_sem_penalidade": 5,
                "penalidade_semana_insuficiente": 100,
                "janela_carencia_dias": 7,
                "max_desconto_semanal_xp": 100,
            }
        elif "to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY')" in s and "IW" in s:
            r.mappings.return_value.one.return_value = {"ano_iso": "2026", "semana_iso": "14"}
        elif "FROM usuarios" in s and "em_ferias" in s:
            r.mappings.return_value.all.return_value = [
                {
                    "id": 99,
                    "perfil": "analista",
                    "ativo": True,
                    "em_ferias": False,
                    "em_atendimento_externo": False,
                }
            ]
        elif "FROM log_auditoria_usuarios" in s:
            r.fetchone.return_value = None
        elif "INTERVAL '7 days'" in s:
            r.mappings.return_value.one.return_value = {"n": 0}
        elif "IYYY-IW" in s and "COUNT(*)" in s:
            r.mappings.return_value.one.return_value = {"n": 5}
        elif "MAX(bc.data_avaliacao)" in s:
            r.mappings.return_value.one.return_value = {"dias": 999}
        elif "INSERT INTO user_xp_events" in s:
            insert_calls += 1
            r.scalar_one_or_none.return_value = 1 if insert_calls == 1 else None
        else:
            pytest.fail(f"SQL não mapeado: {s[:160]}")
        return r

    conn.execute.side_effect = exec_side_effect

    r1 = processar_penalidades_contribuicao(conn)
    assert r1.penalidades_inseridas == 1
    assert r1.penalidades_ja_existiam == 0
    assert insert_calls == 1

    r2 = processar_penalidades_contribuicao(conn)
    assert r2.penalidades_inseridas == 0
    assert r2.penalidades_ja_existiam == 1
    assert insert_calls == 2


def test_montar_event_key_penalidade_formato():
    ek = ps.montar_event_key_penalidade("2026", "14", 3, "SEM_7_DIAS")
    assert ek == "PENALIDADE_SEMANA_2026_14_USER_3_SEM_7_DIAS"


def test_avaliar_motor_isento_nunca_aplica():
    from app.core.penalidades_xp import avaliar_penalidades_usuario

    r = avaliar_penalidades_usuario(
        aprovacoes_ultimos_7_dias=0,
        aprovacoes_semana_iso_atual=0,
        penalidade_sem_7_dias=200,
        minimo_semanal_sem_penalidade=5,
        penalidade_semana_insuficiente=100,
        isento=True,
    )
    assert not r.aplicar
    assert r.pontos == 0


def test_motor_cap_desconto_semanal_em_100():
    from app.core.penalidades_xp import avaliar_penalidades_usuario

    r = avaliar_penalidades_usuario(
        aprovacoes_ultimos_7_dias=0,
        aprovacoes_semana_iso_atual=0,
        penalidade_sem_7_dias=200,
        minimo_semanal_sem_penalidade=5,
        penalidade_semana_insuficiente=150,
        isento=False,
        max_desconto_semanal=100,
    )
    assert r.aplicar
    assert r.pontos == -100
