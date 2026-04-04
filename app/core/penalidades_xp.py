"""
Motor puro de penalidades por contribuição (docs/regras_contribuicao.md §11).
Sem I/O: a rotina chama `avaliar_penalidades_usuario` com métricas já calculadas.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ("ResultadoPenalidade", "avaliar_penalidades_usuario")


@dataclass(frozen=True, slots=True)
class ResultadoPenalidade:
    """Se aplicar=True, `pontos` é negativo (desconto de XP)."""

    aplicar: bool
    pontos: int
    codigo: str
    motivo: str


def avaliar_penalidades_usuario(
    *,
    aprovacoes_ultimos_7_dias: int,
    aprovacoes_semana_iso_atual: int,
    penalidade_sem_7_dias: int,
    minimo_semanal_sem_penalidade: int,
    penalidade_semana_insuficiente: int,
    isento: bool,
) -> ResultadoPenalidade:
    """
    Prioridade (§11): primeiro “sem aprovação nos últimos 7 dias”; senão, meta semanal.
    Isentos (férias / atendimento externo na rotina) não recebem penalidade.
    """
    if isento:
        return ResultadoPenalidade(False, 0, "", "isento_ferias_ou_atendimento_externo")

    a7 = max(0, aprovacoes_ultimos_7_dias)
    sem = max(0, aprovacoes_semana_iso_atual)

    if penalidade_sem_7_dias > 0 and a7 == 0:
        return ResultadoPenalidade(
            True,
            -abs(penalidade_sem_7_dias),
            "SEM_7_DIAS",
            "nenhuma_aprovacao_nos_ultimos_7_dias_utc",
        )

    if (
        penalidade_semana_insuficiente > 0
        and minimo_semanal_sem_penalidade > 0
        and sem < minimo_semanal_sem_penalidade
    ):
        return ResultadoPenalidade(
            True,
            -abs(penalidade_semana_insuficiente),
            "SEMANA_INSUFICIENTE",
            "abaixo_do_minimo_semanal_de_aprovacoes",
        )

    return ResultadoPenalidade(False, 0, "", "nenhuma_penalidade_aplicavel")
