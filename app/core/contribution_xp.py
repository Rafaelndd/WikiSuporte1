"""
Cálculo de XP para contribuições: pontos base, multiplicador diário e bônus semanal.

- Base: modalidade e atraso (`calcular_pontos_base`).
- Combo na aprovação: multiplicador sobre a base + sinalização de bônus semanal isolado.
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
    "ResultadoXpFinal",
    "StatusContribuicao",
    "XpMultiplicadoresConfig",
    "calcular_pontos_base",
    "calcular_xp_final_e_bonus",
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


@dataclass(frozen=True, slots=True)
class XpMultiplicadoresConfig:
    """
    Parâmetros do multiplicador diário (Regra 5) e meta de bônus semanal ISO.

    Limiares em 0 desativam a regra correspondente (multiplicador diário ou meta semanal).
    """

    multiplicador_diario_apos_qtd: int = 3
    multiplicador_diario_valor: float = 2.0
    bonus_semanal_meta_qtd: int = 15
    bonus_semanal_meta_pontos: int = 1000


@dataclass(frozen=True, slots=True)
class ResultadoXpFinal:
    """
    Resultado do processamento na aprovação.

    ``pontos_contribuicao`` inclui apenas o multiplicador diário sobre a base.
    ``pontos_bonus_semanal`` é o valor do prémio semanal quando disparado (não somado
    automaticamente a ``pontos_contribuicao``).
    """

    pontos_contribuicao: int
    bonus_semanal_concedido: bool
    pontos_bonus_semanal: int


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


def _pontos_apos_multiplicador_diario(
    pontos_base: int,
    aprovacoes_hoje: int,
    cfg: XpMultiplicadoresConfig,
) -> int:
    """Aplica multiplicador diário se limiar e valor estiverem ativos."""
    if cfg.multiplicador_diario_apos_qtd <= 0:
        return int(pontos_base)
    if cfg.multiplicador_diario_valor <= 1:
        return int(pontos_base)
    if (aprovacoes_hoje + 1) >= cfg.multiplicador_diario_apos_qtd:
        return int(round(float(pontos_base) * float(cfg.multiplicador_diario_valor)))
    return int(pontos_base)


def _bonus_semanal_disparado(
    aprovacoes_semana_iso: int,
    cfg: XpMultiplicadoresConfig,
) -> tuple[bool, int]:
    """(concedido, pontos do bônus). Meta 0 desativa o bônus."""
    if cfg.bonus_semanal_meta_qtd <= 0:
        return False, 0
    if (aprovacoes_semana_iso + 1) == cfg.bonus_semanal_meta_qtd:
        return True, int(cfg.bonus_semanal_meta_pontos)
    return False, 0


def calcular_xp_final_e_bonus(
    pontos_base: int,
    aprovacoes_hoje: int,
    aprovacoes_semana_iso: int,
    *,
    config: XpMultiplicadoresConfig | None = None,
) -> ResultadoXpFinal:
    """
    Processa multiplicador diário e sinaliza bônus semanal no momento da aprovação.

    ``aprovacoes_hoje`` / ``aprovacoes_semana_iso`` são contagens **antes** desta
    aprovação; a função usa ``+ 1`` para refletir o combo atual.

    Multiplicador diário: ativo quando ``(aprovacoes_hoje + 1) >= meta`` e
    ``multiplicador_diario_valor > 1``, salvo se ``multiplicador_diario_apos_qtd == 0``.

    Bônus semanal: dispara quando ``(aprovacoes_semana_iso + 1) == bonus_semanal_meta_qtd``;
    os pontos do bônus não entram em ``pontos_contribuicao``.
    """
    cfg = config or XpMultiplicadoresConfig()
    pts = _pontos_apos_multiplicador_diario(pontos_base, aprovacoes_hoje, cfg)
    concedido, bonus_pts = _bonus_semanal_disparado(aprovacoes_semana_iso, cfg)
    return ResultadoXpFinal(
        pontos_contribuicao=pts,
        bonus_semanal_concedido=concedido,
        pontos_bonus_semanal=bonus_pts,
    )
