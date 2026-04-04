"""
Transações de aprovação da base de conhecimento (CONHECIMENTO_SUPORTE) com XP (motores puros).
O saldo xp_total do autor é recalculado por triggers após UPDATE / eventos de bônus.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping

from sqlalchemy import Connection, text

from app.core.contribution_xp import (
    ContributionXpConfig,
    ResultadoXpFinal,
    XpMultiplicadoresConfig,
    calcular_pontos_base,
    calcular_xp_final_e_bonus,
    data_utc,
)

ORIGEM_CONHECIMENTO_SUPORTE = "CONHECIMENTO_SUPORTE"

STATUSES_APROVAVEIS = frozenset({"PENDENTE", "REVISAO_PENDENTE"})


class AprovacaoContribuicaoError(RuntimeError):
    """Estado da contribuição ou permissões impedem a aprovação."""


def _as_date(d: date | datetime | None, fallback: date) -> date:
    if d is None:
        return fallback
    if isinstance(d, datetime):
        return data_utc(d)
    return d


def carregar_configs_xp(conn: Connection) -> tuple[ContributionXpConfig, XpMultiplicadoresConfig]:
    row = conn.execute(
        text(
            """
            SELECT pontos_evento_passado,
                   multiplicador_diario_apos_qtd,
                   multiplicador_diario_valor,
                   bonus_semanal_meta_qtd,
                   bonus_semanal_meta_pontos
            FROM contribution_scoring_rules
            WHERE id = 1
            """
        )
    ).mappings().first()
    if not row:
        return ContributionXpConfig(), XpMultiplicadoresConfig()
    base = ContributionXpConfig(pontos_evento_passado=int(row["pontos_evento_passado"]))
    mult = XpMultiplicadoresConfig(
        multiplicador_diario_apos_qtd=int(row["multiplicador_diario_apos_qtd"]),
        multiplicador_diario_valor=int(row["multiplicador_diario_valor"]),
        bonus_semanal_meta_qtd=int(row["bonus_semanal_meta_qtd"]),
        bonus_semanal_meta_pontos=int(row["bonus_semanal_meta_pontos"]),
    )
    return base, mult


def contar_aprovacoes_autor_hoje_utc(
    conn: Connection,
    autor_id: int,
    *,
    exclude_contribuicao_id: int | None = None,
) -> int:
    """Contribuições já APROVADAS do autor hoje (UTC), por data_avaliacao."""
    q = """
        SELECT COUNT(*) AS n
        FROM base_conhecimento
        WHERE id_analista_autor = :aid
          AND status = 'APROVADO'
          AND origem = :origem
          AND data_avaliacao IS NOT NULL
          AND DATE(timezone('UTC', data_avaliacao))
              = DATE(timezone('UTC', CURRENT_TIMESTAMP))
    """
    params: dict[str, Any] = {"aid": autor_id, "origem": ORIGEM_CONHECIMENTO_SUPORTE}
    if exclude_contribuicao_id is not None:
        q += " AND id <> :excl"
        params["excl"] = exclude_contribuicao_id
    row = conn.execute(text(q), params).mappings().one()
    return int(row["n"])


def contar_aprovacoes_autor_semana_iso_utc(
    conn: Connection,
    autor_id: int,
    *,
    exclude_contribuicao_id: int | None = None,
) -> int:
    """Aprovações do autor na semana ISO (UTC) corrente, por data_avaliacao."""
    q = """
        SELECT COUNT(*) AS n
        FROM base_conhecimento
        WHERE id_analista_autor = :aid
          AND status = 'APROVADO'
          AND origem = :origem
          AND data_avaliacao IS NOT NULL
          AND to_char(timezone('UTC', data_avaliacao), 'IYYY-IW')
              = to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY-IW')
    """
    params: dict[str, Any] = {"aid": autor_id, "origem": ORIGEM_CONHECIMENTO_SUPORTE}
    if exclude_contribuicao_id is not None:
        q += " AND id <> :excl"
        params["excl"] = exclude_contribuicao_id
    row = conn.execute(text(q), params).mappings().one()
    return int(row["n"])


def semana_iso_utc_atual(conn: Connection) -> str:
    row = conn.execute(
        text("SELECT to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY-IW') AS w")
    ).mappings().one()
    return str(row["w"])


def computar_xp_aprovacao(
    conn: Connection,
    *,
    autor_id: int,
    exclude_contribuicao_id: int | None,
    modalidade: str | None,
    data_ocorrido: date | datetime | None,
    criado_em: datetime,
    era_revisao_pendente: bool,
) -> ResultadoXpFinal:
    cfg_base, cfg_mult = carregar_configs_xp(conn)
    hoje = contar_aprovacoes_autor_hoje_utc(
        conn, autor_id, exclude_contribuicao_id=exclude_contribuicao_id
    )
    semana = contar_aprovacoes_autor_semana_iso_utc(
        conn, autor_id, exclude_contribuicao_id=exclude_contribuicao_id
    )
    d_oc = _as_date(data_ocorrido, data_utc(criado_em))
    d_sub = data_utc(criado_em)
    base = calcular_pontos_base(
        modalidade or "EVENTO_ATUAL",
        d_oc,
        d_sub,
        era_revisao_pendente,
        cfg_base,
    )
    return calcular_xp_final_e_bonus(base, hoje, semana, cfg_mult)


def _bonus_event_key(autor_id: int, semana_iso: str) -> str:
    return f"BONUS_SEMANAL:{autor_id}:{semana_iso}"


def registrar_bonus_semanal_contribuicao(
    conn: Connection,
    contribuicao_id: int,
    autor_id: int,
    xp_res: ResultadoXpFinal,
) -> None:
    """Insere evento de bônus semanal idempotente (se aplicável)."""
    if not (xp_res.bonus_semanal_concedido and xp_res.pontos_bonus_semanal > 0):
        return
    wk = semana_iso_utc_atual(conn)
    ek = _bonus_event_key(autor_id, wk)
    conn.execute(
        text(
            """
            INSERT INTO user_xp_events
                (usuario_id, tipo_evento, pontos, id_base_conhecimento, event_key)
            VALUES
                (:uid, 'BONUS_SEMANAL', :pts, :bid, :ek)
            ON CONFLICT (event_key) DO NOTHING
            """
        ),
        {
            "uid": autor_id,
            "pts": xp_res.pontos_bonus_semanal,
            "bid": contribuicao_id,
            "ek": ek,
        },
    )


def aprovar_contribuicao_conhecimento(
    conn: Connection,
    contribuicao_id: int,
    avaliador_id: int,
) -> ResultadoXpFinal:
    """
    Aprova uma contribuição na mesma transação de `conn`.
    Grava pontos_contribuicao, opcionalmente insere bônus semanal em user_xp_events.
    """
    row = conn.execute(
        text(
            """
            SELECT id, status, origem, id_analista_autor, modalidade_contribuicao,
                   data_ocorrido, criado_em
            FROM base_conhecimento
            WHERE id = :id
            FOR UPDATE
            """
        ),
        {"id": contribuicao_id},
    ).mappings().one_or_none()
    if row is None:
        raise AprovacaoContribuicaoError("Contribuição não encontrada.")
    m: Mapping[str, Any] = row
    if m.get("origem") != ORIGEM_CONHECIMENTO_SUPORTE:
        raise AprovacaoContribuicaoError("Origem não suportada para este fluxo de aprovação.")
    st = (m.get("status") or "").strip()
    if st == "APROVADO":
        raise AprovacaoContribuicaoError("Contribuição já está aprovada.")
    if st not in STATUSES_APROVAVEIS:
        raise AprovacaoContribuicaoError(f"Status '{st}' não permite aprovação pela fila.")

    autor_id = int(m["id_analista_autor"])
    era_revisao = st == "REVISAO_PENDENTE"
    criado_em = m["criado_em"]
    if not isinstance(criado_em, datetime):
        raise AprovacaoContribuicaoError("criado_em inválido na contribuição.")
    if criado_em.tzinfo is None:
        criado_em = criado_em.replace(tzinfo=timezone.utc)

    xp_res = computar_xp_aprovacao(
        conn,
        autor_id=autor_id,
        exclude_contribuicao_id=contribuicao_id,
        modalidade=m.get("modalidade_contribuicao"),
        data_ocorrido=m.get("data_ocorrido"),
        criado_em=criado_em,
        era_revisao_pendente=era_revisao,
    )

    conn.execute(
        text(
            """
            UPDATE base_conhecimento
            SET status = 'APROVADO',
                motivo_rejeicao = NULL,
                pontos_contribuicao = :pts,
                data_avaliacao = CURRENT_TIMESTAMP,
                id_avaliador = :av
            WHERE id = :id
            """
        ),
        {"pts": xp_res.pontos_contribuicao, "av": avaliador_id, "id": contribuicao_id},
    )

    registrar_bonus_semanal_contribuicao(conn, contribuicao_id, autor_id, xp_res)

    return xp_res
