"""
Motor de penalidades e isenções de XP (Regra 11).

Avalia se um utilizador deve sofrer débito por inatividade ou meta semanal insuficiente.
Sem efeitos colaterais; adequado a chamadas no fluxo de fecho de período ou jobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

__all__ = [
    "PenalidadesXpConfig",
    "ResultadoPenalidade",
    "TipoPenalidade",
    "UsuarioStatusPenalidade",
    "avaliar_penalidades_usuario",
]


class TipoPenalidade(str, Enum):
    """Tipo de resultado da avaliação (mutuamente exclusivo por processamento)."""

    NENHUMA = "NENHUMA"
    SEM_CONTRIBUICAO_7_DIAS = "SEM_CONTRIBUICAO_7_DIAS"
    SEMANA_INSUFICIENTE = "SEMANA_INSUFICIENTE"


@dataclass(frozen=True, slots=True)
class UsuarioStatusPenalidade:
    """Estado operacional do utilizador no momento da avaliação."""

    perfil: str
    ativo: bool | None = True
    em_ferias: bool = False
    em_atendimento_externo: bool = False


@dataclass(frozen=True, slots=True)
class PenalidadesXpConfig:
    """Parâmetros configuráveis; valores 0 desativam a regra correspondente."""

    penalidade_sem_7_dias: int = 0
    minimo_semanal_sem_penalidade: int = 0
    penalidade_semana_insuficiente: int = 0


@dataclass(frozen=True, slots=True)
class ResultadoPenalidade:
    """Resultado da avaliação: débito sugerido e motivo."""

    houve_penalidade: bool
    tipo: TipoPenalidade
    valor_debitado: int


_RESULTADO_LIMPO: Final[ResultadoPenalidade] = ResultadoPenalidade(
    houve_penalidade=False,
    tipo=TipoPenalidade.NENHUMA,
    valor_debitado=0,
)


def _perfil_e_admin(perfil: str | None) -> bool:
    return (perfil or "").strip().lower() == "admin"


def _isento_filtro_base(usuario: UsuarioStatusPenalidade) -> bool:
    """Inativo ou admin: nunca penalidade."""
    if usuario.ativo is False:
        return True
    if _perfil_e_admin(usuario.perfil):
        return True
    return False


def _isento_ferias_ou_externo(usuario: UsuarioStatusPenalidade) -> bool:
    return bool(usuario.em_ferias) or bool(usuario.em_atendimento_externo)


def avaliar_penalidades_usuario(
    usuario: UsuarioStatusPenalidade,
    dias_desde_ultima_aprovacao: int,
    aprovacoes_semana: int,
    *,
    config: PenalidadesXpConfig | None = None,
) -> ResultadoPenalidade:
    """
    Avalia penalidades mutuamente exclusivas (Regra A antes da Regra B).

    - Regra A: ``dias_desde_ultima_aprovacao >= 7`` e ``penalidade_sem_7_dias > 0``.
    - Regra B: só se A não aplicou; ``aprovacoes_semana < minimo_semanal_sem_penalidade``
      e ``penalidade_semana_insuficiente > 0``.

    Isenções: inativo, admin, ``em_ferias`` ou ``em_atendimento_externo``.
    """
    cfg = config or PenalidadesXpConfig()

    if _isento_filtro_base(usuario):
        return _RESULTADO_LIMPO

    if _isento_ferias_ou_externo(usuario):
        return _RESULTADO_LIMPO

    if (
        dias_desde_ultima_aprovacao >= 7
        and cfg.penalidade_sem_7_dias > 0
    ):
        return ResultadoPenalidade(
            houve_penalidade=True,
            tipo=TipoPenalidade.SEM_CONTRIBUICAO_7_DIAS,
            valor_debitado=int(cfg.penalidade_sem_7_dias),
        )

    if (
        cfg.penalidade_semana_insuficiente > 0
        and cfg.minimo_semanal_sem_penalidade > 0
        and aprovacoes_semana < cfg.minimo_semanal_sem_penalidade
    ):
        return ResultadoPenalidade(
            houve_penalidade=True,
            tipo=TipoPenalidade.SEMANA_INSUFICIENTE,
            valor_debitado=int(cfg.penalidade_semana_insuficiente),
        )

    return _RESULTADO_LIMPO
