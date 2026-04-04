"""Testes unitários dos motores puros de XP (contribuição)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.core.contribution_xp import (
    ContributionXpConfig,
    XpMultiplicadoresConfig,
    calcular_pontos_base,
    calcular_xp_final_e_bonus,
    data_utc,
)


def test_data_utc_naive_tratada_como_utc():
    dt = datetime(2026, 4, 1, 15, 0, 0)
    assert data_utc(dt) == date(2026, 4, 1)


def test_data_utc_com_tz():
    dt = datetime(2026, 4, 1, 2, 0, 0, tzinfo=timezone.utc)
    assert data_utc(dt) == date(2026, 4, 1)


def test_evento_passado_base():
    cfg = ContributionXpConfig(pontos_evento_passado=125)
    o = date(2026, 1, 1)
    s = date(2026, 4, 3)
    assert calcular_pontos_base("EVENTO_PASSADO", o, s, False, cfg) == 125


def test_evento_atual_faixas():
    cfg = ContributionXpConfig()
    o = date(2026, 4, 1)
    assert calcular_pontos_base("EVENTO_ATUAL", o, date(2026, 4, 1), False, cfg) == 100
    assert calcular_pontos_base("EVENTO_ATUAL", o, date(2026, 4, 8), False, cfg) == 100
    assert calcular_pontos_base("EVENTO_ATUAL", o, date(2026, 4, 9), False, cfg) == 75
    assert calcular_pontos_base("EVENTO_ATUAL", o, date(2026, 4, 22), False, cfg) == 25
    assert calcular_pontos_base("EVENTO_ATUAL", o, date(2026, 4, 30), False, cfg) == 0


def test_evento_atual_submissao_antes_ocorrido_zero():
    cfg = ContributionXpConfig()
    o = date(2026, 4, 10)
    s = date(2026, 4, 1)
    assert calcular_pontos_base("EVENTO_ATUAL", o, s, False, cfg) == 0


def test_revisao_pendente_maximo_modalidade():
    cfg = ContributionXpConfig(pontos_evento_passado=80)
    o = date(2026, 1, 1)
    s = date(2026, 6, 1)
    assert calcular_pontos_base("EVENTO_PASSADO", o, s, True, cfg) == 80
    assert calcular_pontos_base("EVENTO_ATUAL", o, s, True, cfg) == 100


def test_multiplicador_diario_terceira_aprovacao():
    m = XpMultiplicadoresConfig(multiplicador_diario_apos_qtd=3, multiplicador_diario_valor=2)
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje_antes=2, aprovacoes_semana_iso_antes=0, mult_cfg=m)
    assert r.pontos_contribuicao == 200
    assert r.bonus_semanal_concedido is False


def test_sem_multiplicador_antes_do_limiar():
    m = XpMultiplicadoresConfig(multiplicador_diario_apos_qtd=3, multiplicador_diario_valor=2)
    r = calcular_xp_final_e_bonus(50, 1, 0, m)
    assert r.pontos_contribuicao == 50


def test_bonus_semanal_na_meta():
    m = XpMultiplicadoresConfig(
        bonus_semanal_meta_qtd=15,
        bonus_semanal_meta_pontos=1000,
        multiplicador_diario_apos_qtd=0,
        multiplicador_diario_valor=1,
    )
    r = calcular_xp_final_e_bonus(10, 0, 14, m)
    assert r.pontos_contribuicao == 10
    assert r.bonus_semanal_concedido is True
    assert r.pontos_bonus_semanal == 1000


@pytest.mark.parametrize(
    "apos_qtd,valor",
    [(0, 2), (3, 1)],
)
def test_multiplicador_desligado(apos_qtd: int, valor: int):
    m = XpMultiplicadoresConfig(
        multiplicador_diario_apos_qtd=apos_qtd,
        multiplicador_diario_valor=valor,
        bonus_semanal_meta_qtd=0,
        bonus_semanal_meta_pontos=0,
    )
    r = calcular_xp_final_e_bonus(100, 10, 10, m)
    assert r.pontos_contribuicao == 100
