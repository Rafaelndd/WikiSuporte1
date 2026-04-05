"""Motor puro de penalidades por contribuição (regras de negócio, sem I/O)."""

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
    max_desconto_semanal: int = 100,
) -> ResultadoPenalidade:
    if isento:
        return ResultadoPenalidade(False, 0, "", "isento_ferias_ou_atendimento_externo")

    a7 = max(0, aprovacoes_ultimos_7_dias)
    sem = max(0, aprovacoes_semana_iso_atual)

    limite_desconto = max(0, int(max_desconto_semanal))

    if penalidade_sem_7_dias > 0 and a7 == 0 and limite_desconto > 0:
        desconto = min(abs(penalidade_sem_7_dias), limite_desconto)
        return ResultadoPenalidade(
            True,
            -desconto,
            "SEM_7_DIAS",
            "nenhuma_aprovacao_nos_ultimos_7_dias_utc",
        )

    if (
        penalidade_semana_insuficiente > 0
        and minimo_semanal_sem_penalidade > 0
        and sem < minimo_semanal_sem_penalidade
        and limite_desconto > 0
    ):
        desconto = min(abs(penalidade_semana_insuficiente), limite_desconto)
        return ResultadoPenalidade(
            True,
            -desconto,
            "SEMANA_INSUFICIENTE",
            "abaixo_do_minimo_semanal_de_aprovacoes",
        )

    return ResultadoPenalidade(False, 0, "", "nenhuma_penalidade_aplicavel")
