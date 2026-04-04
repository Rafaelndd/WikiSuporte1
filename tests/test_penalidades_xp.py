"""Testes do motor de penalidades e isenções (Regra 11)."""

from __future__ import annotations

from app.core.penalidades_xp import (
    PenalidadesXpConfig,
    ResultadoPenalidade,
    TipoPenalidade,
    UsuarioStatusPenalidade,
    avaliar_penalidades_usuario,
)

CFG_PADRAO = PenalidadesXpConfig(
    penalidade_sem_7_dias=50,
    minimo_semanal_sem_penalidade=3,
    penalidade_semana_insuficiente=30,
)


def test_admin_nunca_penalizado() -> None:
    u = UsuarioStatusPenalidade(perfil="admin", ativo=True, em_ferias=False, em_atendimento_externo=False)
    r = avaliar_penalidades_usuario(u, dias_desde_ultima_aprovacao=999, aprovacoes_semana=0, config=CFG_PADRAO)
    assert r == ResultadoPenalidade(False, TipoPenalidade.NENHUMA, 0)


def test_admin_case_insensitive() -> None:
    u = UsuarioStatusPenalidade(perfil="  ADMIN  ")
    r = avaliar_penalidades_usuario(u, 100, 0, config=CFG_PADRAO)
    assert not r.houve_penalidade


def test_inativo_nunca_penalizado() -> None:
    u = UsuarioStatusPenalidade(perfil="analista", ativo=False)
    r = avaliar_penalidades_usuario(u, 999, 0, config=CFG_PADRAO)
    assert not r.houve_penalidade


def test_analista_ferias_isento_mesmo_com_metricas_pessimas() -> None:
    u = UsuarioStatusPenalidade(
        perfil="analista",
        ativo=True,
        em_ferias=True,
        em_atendimento_externo=False,
    )
    r = avaliar_penalidades_usuario(u, 999, 0, config=CFG_PADRAO)
    assert not r.houve_penalidade


def test_analista_atendimento_externo_isento() -> None:
    u = UsuarioStatusPenalidade(
        perfil="analista",
        em_ferias=False,
        em_atendimento_externo=True,
    )
    r = avaliar_penalidades_usuario(u, 999, 0, config=CFG_PADRAO)
    assert not r.houve_penalidade


def test_analista_ferias_isento_config_penalidades_zeradas() -> None:
    """Isenção não depende de valores de config."""
    u = UsuarioStatusPenalidade(perfil="analista", em_ferias=True)
    cfg = PenalidadesXpConfig()
    r = avaliar_penalidades_usuario(u, 999, 0, config=cfg)
    assert not r.houve_penalidade


def test_regra_a_7_dias_sem_contribuir() -> None:
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, dias_desde_ultima_aprovacao=7, aprovacoes_semana=10, config=CFG_PADRAO)
    assert r.houve_penalidade
    assert r.tipo == TipoPenalidade.SEM_CONTRIBUICAO_7_DIAS
    assert r.valor_debitado == 50


def test_regra_a_prioridade_sobre_regra_b() -> None:
    """Com 10 dias e semana fraca, aplica A (mutuamente exclusivo)."""
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, 10, aprovacoes_semana=0, config=CFG_PADRAO)
    assert r.tipo == TipoPenalidade.SEM_CONTRIBUICAO_7_DIAS


def test_regra_b_meta_semanal_insuficiente_apos_passar_regra_a() -> None:
    """Dias < 7 mas aprovações abaixo do mínimo."""
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, dias_desde_ultima_aprovacao=3, aprovacoes_semana=2, config=CFG_PADRAO)
    assert r.houve_penalidade
    assert r.tipo == TipoPenalidade.SEMANA_INSUFICIENTE
    assert r.valor_debitado == 30


def test_analista_sem_penalidade_metas_ok() -> None:
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, dias_desde_ultima_aprovacao=1, aprovacoes_semana=5, config=CFG_PADRAO)
    assert not r.houve_penalidade
    assert r.valor_debitado == 0


def test_config_penalidade_7_dias_zero_desliga_regra_a() -> None:
    cfg = PenalidadesXpConfig(
        penalidade_sem_7_dias=0,
        minimo_semanal_sem_penalidade=3,
        penalidade_semana_insuficiente=30,
    )
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, 30, 0, config=cfg)
    assert r.tipo == TipoPenalidade.SEMANA_INSUFICIENTE


def test_config_penalidade_semana_zero_desliga_regra_b() -> None:
    cfg = PenalidadesXpConfig(
        penalidade_sem_7_dias=50,
        minimo_semanal_sem_penalidade=3,
        penalidade_semana_insuficiente=0,
    )
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, 3, 0, config=cfg)
    assert not r.houve_penalidade


def test_config_minimo_semanal_zero_desliga_regra_b() -> None:
    cfg = PenalidadesXpConfig(
        penalidade_sem_7_dias=0,
        minimo_semanal_sem_penalidade=0,
        penalidade_semana_insuficiente=100,
    )
    u = UsuarioStatusPenalidade(perfil="analista")
    r = avaliar_penalidades_usuario(u, 3, 0, config=cfg)
    assert not r.houve_penalidade
