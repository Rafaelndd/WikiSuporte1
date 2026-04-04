"""
Cálculo de pontos base (XP) para contribuições aprovadas.

Apenas a parcela base por modalidade e atraso; multiplicadores ficam fora deste módulo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Final, Union

PONTOS_MAXIMO_BASE_EVENTO_ATUAL: Final[int] = 100

__all__ = [
    "ContributionXpConfig",
    "ModalidadeContribuicao",
    "PONTOS_MAXIMO_BASE_EVENTO_ATUAL",
    "StatusContribuicao",
    "calcular_pontos_base",
]


class ModalidadeContribuicao(str, Enum):
    """Modalidade da contribuição para fins de pontuação base."""

    EVENTO_PASSADO = "EVENTO_PASSADO"
    EVENTO_ATUAL = "EVENTO_ATUAL"


class StatusContribuicao(str, Enum):
    """Valores relevantes ao histórico de status (normalização)."""

    REVISAO_PENDENTE = "REVISAO_PENDENTE"


@dataclass(frozen=True, slots=True)
class ContributionXpConfig:
    """Parâmetros configuráveis da regra de XP base."""

    pontos_evento_passado: int = 125


def _as_date(val: Union[date, datetime]) -> date:
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone(timezone.utc).date()
        return val.date()
    return val


def _dias_atraso_submissao(data_ocorrido: date, criado_em: Union[date, datetime]) -> int:
    """
    Diferença em dias completos: data de criação (submissão) menos data do ocorrido.
    Positivo = submissão depois do evento; negativo = submissão antes do evento.
    """
    c = _as_date(criado_em)
    return (c - data_ocorrido).days


def _pontos_evento_atual_por_atraso(dias: int) -> int:
    if dias < 0:
        return 0
    if dias <= 7:
        return PONTOS_MAXIMO_BASE_EVENTO_ATUAL
    if dias <= 14:
        return 75
    if dias <= 21:
        return 25
    return 0


def _normalizar_status_anterior(
    status_anterior_ao_aprovar: str | StatusContribuicao | None,
) -> str | None:
    if status_anterior_ao_aprovar is None:
        return None
    if isinstance(status_anterior_ao_aprovar, StatusContribuicao):
        return status_anterior_ao_aprovar.value
    s = str(status_anterior_ao_aprovar).strip().upper()
    return s or None


def _era_revisao_pendente(status_anterior_ao_aprovar: str | StatusContribuicao | None) -> bool:
    norm = _normalizar_status_anterior(status_anterior_ao_aprovar)
    return norm == StatusContribuicao.REVISAO_PENDENTE.value


def calcular_pontos_base(
    modalidade: ModalidadeContribuicao,
    data_ocorrido: date,
    criado_em: Union[date, datetime],
    *,
    status_anterior_ao_aprovar: str | StatusContribuicao | None = None,
    config: ContributionXpConfig | None = None,
) -> int:
    """
    Retorna os pontos base da contribuição, sem multiplicadores.

    - EVENTO_PASSADO: valor fixo ``config.pontos_evento_passado`` (ignora datas).
    - EVENTO_ATUAL: faixas por atraso em dias (apenas datas); negativo ou >21 → 0.
    - Se o status anterior à aprovação for REVISAO_PENDENTE: ignora atraso e aplica
      o máximo da modalidade (100 para EVENTO_ATUAL; valor de config para EVENTO_PASSADO).
    """
    cfg = config or ContributionXpConfig()

    if modalidade == ModalidadeContribuicao.EVENTO_PASSADO:
        # Valor fixo; REVISAO_PENDENTE mantém o mesmo teto (valor de configuração).
        return int(cfg.pontos_evento_passado)

    if modalidade == ModalidadeContribuicao.EVENTO_ATUAL:
        if _era_revisao_pendente(status_anterior_ao_aprovar):
            return PONTOS_MAXIMO_BASE_EVENTO_ATUAL
        dias = _dias_atraso_submissao(data_ocorrido, criado_em)
        return _pontos_evento_atual_por_atraso(dias)

    raise ValueError(f"Modalidade não suportada: {modalidade!r}")
