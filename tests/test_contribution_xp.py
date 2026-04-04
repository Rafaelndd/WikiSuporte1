"""Testes do motor de pontos base (XP) de contribuições."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.contribution_xp import (
    PONTOS_MAXIMO_BASE_EVENTO_ATUAL,
    ContributionXpConfig,
    ModalidadeContribuicao,
    ResultadoXpFinal,
    StatusContribuicao,
    XpMultiplicadoresConfig,
    calcular_pontos_base,
    calcular_xp_final_e_bonus,
)

DATA_O = date(2025, 6, 1)


def test_evento_passado_valor_fixo_config_padrao() -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_PASSADO,
            DATA_O,
            date(2099, 1, 1),
        )
        == 125
    )


def test_evento_passado_valor_fixo_config_custom() -> None:
    cfg = ContributionXpConfig(pontos_evento_passado=200)
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_PASSADO,
            DATA_O,
            date(2020, 1, 1),
            config=cfg,
        )
        == 200
    )


def test_evento_passado_ignora_revisao_pendente_mesmo_valor_config() -> None:
    cfg = ContributionXpConfig(pontos_evento_passado=88)
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_PASSADO,
            DATA_O,
            date(2099, 1, 1),
            status_anterior_ao_aprovar=StatusContribuicao.REVISAO_PENDENTE,
            config=cfg,
        )
        == 88
    )


@pytest.mark.parametrize(
    ("criado", "esperado"),
    [
        (DATA_O, PONTOS_MAXIMO_BASE_EVENTO_ATUAL),
        (DATA_O + timedelta(days=7), PONTOS_MAXIMO_BASE_EVENTO_ATUAL),
        (DATA_O + timedelta(days=8), 75),
        (DATA_O + timedelta(days=14), 75),
        (DATA_O + timedelta(days=15), 25),
        (DATA_O + timedelta(days=21), 25),
        (DATA_O + timedelta(days=22), 0),
    ],
)
def test_evento_atual_faixas_dias(criado: date, esperado: int) -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            criado,
        )
        == esperado
    )


def test_evento_atual_submissao_antes_do_ocorrido_zero() -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            DATA_O - timedelta(days=1),
        )
        == 0
    )


def test_evento_atual_datetime_apenas_parte_data() -> None:
    """Horas ignoradas: mesmo dia do evento conta como 0 dias de atraso."""
    criado = datetime(2025, 6, 1, 23, 59, 59)
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            criado,
        )
        == PONTOS_MAXIMO_BASE_EVENTO_ATUAL
    )


def test_evento_atual_datetime_com_timezone_utc() -> None:
    ocorrido = date(2025, 6, 10)
    criado = datetime(2025, 6, 18, 12, 0, tzinfo=timezone.utc)
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            ocorrido,
            criado,
        )
        == 75
    )


def test_evento_atual_revisao_pendente_ignora_atraso_maximo_100() -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            DATA_O + timedelta(days=500),
            status_anterior_ao_aprovar=StatusContribuicao.REVISAO_PENDENTE,
        )
        == PONTOS_MAXIMO_BASE_EVENTO_ATUAL
    )


def test_evento_atual_revisao_pendente_string_normalizada() -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            DATA_O + timedelta(days=500),
            status_anterior_ao_aprovar="  revisao_pendente  ",
        )
        == PONTOS_MAXIMO_BASE_EVENTO_ATUAL
    )


def test_evento_atual_sem_revisao_pendente_atraso_grande_zero() -> None:
    assert (
        calcular_pontos_base(
            ModalidadeContribuicao.EVENTO_ATUAL,
            DATA_O,
            DATA_O + timedelta(days=500),
            status_anterior_ao_aprovar=None,
        )
        == 0
    )


def test_modalidade_desconhecida_levanta() -> None:
    class _FakeModalidade:
        value = "OUTRA"

    with pytest.raises(ValueError, match="Modalidade não suportada"):
        calcular_pontos_base(
            _FakeModalidade(),  # type: ignore[arg-type]
            DATA_O,
            DATA_O,
        )


# --- Multiplicador diário e bônus semanal (Regra 5) ---


def test_xp_final_sem_multiplicador_abaixo_meta_diaria() -> None:
    """2 aprovações hoje + esta = 3ª ainda não: 1+1 < 3."""
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=1, aprovacoes_semana_iso=0)
    assert r == ResultadoXpFinal(
        pontos_contribuicao=100,
        bonus_semanal_concedido=False,
        pontos_bonus_semanal=0,
    )


def test_xp_final_com_multiplicador_atinge_meta_diaria() -> None:
    """2 + 1 >= 3 → base × 2."""
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=2, aprovacoes_semana_iso=0)
    assert r.pontos_contribuicao == 200
    assert r.bonus_semanal_concedido is False
    assert r.pontos_bonus_semanal == 0


def test_xp_final_bonus_semanal_meta_exata() -> None:
    """14 + 1 == 15 → bônus isolado; sem multiplicador (0+1 < 3)."""
    r = calcular_xp_final_e_bonus(50, aprovacoes_hoje=0, aprovacoes_semana_iso=14)
    assert r.pontos_contribuicao == 50
    assert r.bonus_semanal_concedido is True
    assert r.pontos_bonus_semanal == 1000


def test_xp_final_config_multiplicador_diario_limite_zero_desliga() -> None:
    cfg = XpMultiplicadoresConfig(multiplicador_diario_apos_qtd=0)
    r = calcular_xp_final_e_bonus(
        100,
        aprovacoes_hoje=99,
        aprovacoes_semana_iso=14,
        config=cfg,
    )
    assert r.pontos_contribuicao == 100
    assert r.bonus_semanal_concedido is True
    assert r.pontos_bonus_semanal == 1000


def test_xp_final_config_multiplicador_valor_um_desliga() -> None:
    cfg = XpMultiplicadoresConfig(multiplicador_diario_valor=1.0)
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=5, aprovacoes_semana_iso=0, config=cfg)
    assert r.pontos_contribuicao == 100


def test_xp_final_config_bonus_semanal_meta_zero_desliga() -> None:
    cfg = XpMultiplicadoresConfig(bonus_semanal_meta_qtd=0)
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=2, aprovacoes_semana_iso=14, config=cfg)
    assert r.pontos_contribuicao == 200
    assert r.bonus_semanal_concedido is False
    assert r.pontos_bonus_semanal == 0


def test_xp_final_multiplicador_e_bonus_semanal_simultaneos() -> None:
    r = calcular_xp_final_e_bonus(40, aprovacoes_hoje=2, aprovacoes_semana_iso=14)
    assert r.pontos_contribuicao == 80
    assert r.bonus_semanal_concedido is True
    assert r.pontos_bonus_semanal == 1000


def test_xp_final_bonus_semanal_nao_dispara_um_antes_da_meta() -> None:
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=2, aprovacoes_semana_iso=13)
    assert r.bonus_semanal_concedido is False
    assert r.pontos_bonus_semanal == 0


def test_xp_final_bonus_semanal_nao_dispara_um_depois_da_meta() -> None:
    r = calcular_xp_final_e_bonus(100, aprovacoes_hoje=2, aprovacoes_semana_iso=15)
    assert r.bonus_semanal_concedido is False
