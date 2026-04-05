"""
Cálculo de XP na aprovação de contribuições (regras em docs/regras_contribuicao.md §4–5).
Funções puras: sem acesso a banco ou I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Final

__all__ = (
    "ContributionXpConfig",
    "ResultadoXpFinal",
    "XpMultiplicadoresConfig",
    "calcular_pontos_base",
    "calcular_xp_final_e_bonus",
    "data_utc",
)

_MOD_EVENTO_ATUAL: Final = "EVENTO_ATUAL"
_MOD_EVENTO_PASSADO: Final = "EVENTO_PASSADO"


@dataclass(frozen=True, slots=True)
class ContributionXpConfig:
    """Parâmetros de pontos base (espelha colunas úteis de contribution_scoring_rules)."""

    pontos_evento_passado: int = 90


@dataclass(frozen=True, slots=True)
class XpMultiplicadoresConfig:
    multiplicador_diario_apos_qtd: int = 3
    multiplicador_diario_valor: int = 2
    bonus_semanal_meta_qtd: int = 15
    bonus_semanal_meta_pontos: int = 1000


@dataclass(frozen=True, slots=True)
class ResultadoXpFinal:
    """XP gravado na contribuição (após multiplicador diário) e metadados do bônus semanal."""

    pontos_contribuicao: int
    bonus_semanal_concedido: bool
    pontos_bonus_semanal: int


def data_utc(dt: datetime) -> date:
    """Data civil em UTC (comparável a data_ocorrido DATE no banco)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def calcular_pontos_base(
    modalidade: str,
    data_ocorrido: date,
    data_submissao: date,
    era_revisao_pendente: bool,
    cfg: ContributionXpConfig,
) -> int:
    """
    Pontos base antes de multiplicadores/bônus semanal.
    REVISAO_PENDENTE: máximo da modalidade (EVENTO_PASSADO = config; EVENTO_ATUAL = 100).
    """
    mod = (modalidade or _MOD_EVENTO_ATUAL).strip().upper()
    if era_revisao_pendente:
        if mod == _MOD_EVENTO_PASSADO:
            return max(0, cfg.pontos_evento_passado)
        if mod == _MOD_EVENTO_ATUAL:
            return 100
        return 0
    if mod == _MOD_EVENTO_PASSADO:
        return max(0, cfg.pontos_evento_passado)
    if mod != _MOD_EVENTO_ATUAL:
        return 0
    if data_submissao < data_ocorrido:
        return 0
    delta = (data_submissao - data_ocorrido).days
    if delta <= 7:
        return 100
    if delta <= 14:
        return 75
    if delta <= 21:
        return 25
    return 0


def calcular_xp_final_e_bonus(
    pontos_base: int,
    aprovacoes_hoje_antes: int,
    aprovacoes_semana_iso_antes: int,
    mult_cfg: XpMultiplicadoresConfig,
) -> ResultadoXpFinal:
    """
    aprovacoes_*_antes: contagens **antes** desta aprovação (a linha atual ainda não é APROVADO).
    Multiplicador diário aplica se (N+1) >= limiar. Bônus semanal se (S+1) >= meta.
    """
    mult = 1
    if (
        mult_cfg.multiplicador_diario_apos_qtd > 0
        and mult_cfg.multiplicador_diario_valor > 1
        and (aprovacoes_hoje_antes + 1) >= mult_cfg.multiplicador_diario_apos_qtd
    ):
        mult = mult_cfg.multiplicador_diario_valor

    pontos = max(0, pontos_base) * mult

    bonus_ok = False
    bonus_pts = 0
    if mult_cfg.bonus_semanal_meta_qtd > 0 and mult_cfg.bonus_semanal_meta_pontos > 0:
        if (aprovacoes_semana_iso_antes + 1) >= mult_cfg.bonus_semanal_meta_qtd:
            bonus_ok = True
            bonus_pts = mult_cfg.bonus_semanal_meta_pontos

    return ResultadoXpFinal(
        pontos_contribuicao=pontos,
        bonus_semanal_concedido=bonus_ok,
        pontos_bonus_semanal=bonus_pts,
    )
