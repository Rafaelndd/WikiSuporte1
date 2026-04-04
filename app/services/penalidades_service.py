"""
Rotina de penalidades por contribuição (§11): isenções, métricas reais e eventos idempotentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import Connection, text

from app.core.penalidades_xp import ResultadoPenalidade, avaliar_penalidades_usuario

ORIGEM_CONHECIMENTO_SUPORTE = "CONHECIMENTO_SUPORTE"


@dataclass
class ResumoProcessamentoPenalidades:
    usuarios_encontrados: int = 0
    isentos_pulados: int = 0
    sem_penalidade_motor: int = 0
    penalidades_inseridas: int = 0
    penalidades_ja_existiam: int = 0


@dataclass
class MetricasContribuicaoUsuario:
    dias_desde_ultima_aprovacao: int
    aprovacoes_ultimos_7_dias: int
    aprovacoes_semana_iso_atual: int


def carregar_regras_penalidade(
    conn: Connection,
) -> tuple[int, int, int]:
    """penalidade_sem_7_dias, minimo_semanal_sem_penalidade, penalidade_semana_insuficiente."""
    row = conn.execute(
        text(
            """
            SELECT penalidade_sem_7_dias,
                   minimo_semanal_sem_penalidade,
                   penalidade_semana_insuficiente
            FROM contribution_scoring_rules
            WHERE id = 1
            """
        )
    ).mappings().first()
    if not row:
        return (0, 0, 0)
    return (
        int(row["penalidade_sem_7_dias"]),
        int(row["minimo_semanal_sem_penalidade"]),
        int(row["penalidade_semana_insuficiente"]),
    )


def listar_analistas_para_penalidade(conn: Connection) -> list[Mapping[str, Any]]:
    """Ativos com perfil analista (exclui apenas admin — únicos perfis atuais no sistema)."""
    result = conn.execute(
        text(
            """
            SELECT id, perfil, ativo, em_ferias, em_atendimento_externo
            FROM usuarios
            WHERE COALESCE(ativo, FALSE) = TRUE
              AND lower(trim(COALESCE(perfil, ''))) = 'analista'
            ORDER BY id
            """
        )
    )
    return list(result.mappings().all())


def obter_semana_iso_utc_referencia(conn: Connection) -> tuple[str, str]:
    """Retorna (ano_iso, semana_iso) como em to_char IYYY e IW."""
    row = conn.execute(
        text(
            """
            SELECT to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY') AS ano_iso,
                   to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IW') AS semana_iso
            """
        )
    ).mappings().one()
    return (str(row["ano_iso"]), str(row["semana_iso"]))


def contar_aprovacoes_ultimos_7_dias_utc(conn: Connection, usuario_id: int) -> int:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*) AS n
            FROM base_conhecimento
            WHERE id_analista_autor = :uid
              AND status = 'APROVADO'
              AND origem = :origem
              AND data_avaliacao IS NOT NULL
              AND data_avaliacao >= (timezone('UTC', CURRENT_TIMESTAMP) - INTERVAL '7 days')
            """
        ),
        {"uid": usuario_id, "origem": ORIGEM_CONHECIMENTO_SUPORTE},
    ).mappings().one()
    return int(row["n"])


def contar_aprovacoes_semana_iso_atual_utc(conn: Connection, usuario_id: int) -> int:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*) AS n
            FROM base_conhecimento
            WHERE id_analista_autor = :uid
              AND status = 'APROVADO'
              AND origem = :origem
              AND data_avaliacao IS NOT NULL
              AND to_char(timezone('UTC', data_avaliacao), 'IYYY-IW')
                  = to_char(timezone('UTC', CURRENT_TIMESTAMP), 'IYYY-IW')
            """
        ),
        {"uid": usuario_id, "origem": ORIGEM_CONHECIMENTO_SUPORTE},
    ).mappings().one()
    return int(row["n"])


def dias_desde_ultima_aprovacao(conn: Connection, usuario_id: int) -> int:
    """
    Dias entre a data UTC atual e a última data_avaliacao (CONHECIMENTO_SUPORTE, APROVADO).
    Se nunca houve aprovação, retorna 999.
    """
    row = conn.execute(
        text(
            """
            SELECT CASE
                WHEN MAX(bc.data_avaliacao) IS NULL THEN 999
                ELSE (
                    DATE(timezone('UTC', CURRENT_TIMESTAMP))
                    - DATE(timezone('UTC', MAX(bc.data_avaliacao)))
                )::integer
            END AS dias
            FROM base_conhecimento bc
            WHERE bc.id_analista_autor = :uid
              AND bc.status = 'APROVADO'
              AND bc.origem = :origem
              AND bc.data_avaliacao IS NOT NULL
            """
        ),
        {"uid": usuario_id, "origem": ORIGEM_CONHECIMENTO_SUPORTE},
    ).mappings().one()
    return int(row["dias"])


def coletar_metricas_contribuicao(
    conn: Connection, usuario_id: int
) -> MetricasContribuicaoUsuario:
    return MetricasContribuicaoUsuario(
        dias_desde_ultima_aprovacao=dias_desde_ultima_aprovacao(conn, usuario_id),
        aprovacoes_ultimos_7_dias=contar_aprovacoes_ultimos_7_dias_utc(conn, usuario_id),
        aprovacoes_semana_iso_atual=contar_aprovacoes_semana_iso_atual_utc(conn, usuario_id),
    )


def montar_event_key_penalidade(
    ano_iso: str, semana_iso: str, usuario_id: int, codigo_penalidade: str
) -> str:
    """
    Chave idempotente por semana ISO (UTC) e usuário.
    Formato: PENALIDADE_SEMANA_{ano}_{semana}_USER_{id}_{codigo}
    """
    codigo_curto = codigo_penalidade.replace(" ", "_")
    return f"PENALIDADE_SEMANA_{ano_iso}_{semana_iso}_USER_{usuario_id}_{codigo_curto}"


def tipo_evento_para_codigo(codigo: str) -> str:
    if codigo == "SEM_7_DIAS":
        return "PENALIDADE_SEM_7_DIAS"
    if codigo == "SEMANA_INSUFICIENTE":
        return "PENALIDADE_SEMANA_INSUFICIENTE"
    return "PENALIDADE_CONTRIBUICAO"


def persistir_penalidade_se_necessario(
    conn: Connection,
    usuario_id: int,
    resultado: ResultadoPenalidade,
    ano_iso: str,
    semana_iso: str,
) -> str:
    """
    Insere em user_xp_events com ON CONFLICT DO NOTHING.
    Retorna: 'inserida' | 'duplicada' | 'ignorada'
    """
    if not resultado.aplicar or resultado.pontos >= 0 or not resultado.codigo:
        return "ignorada"

    event_key = montar_event_key_penalidade(ano_iso, semana_iso, usuario_id, resultado.codigo)
    tipo = tipo_evento_para_codigo(resultado.codigo)

    res = conn.execute(
        text(
            """
            INSERT INTO user_xp_events
                (usuario_id, tipo_evento, pontos, id_base_conhecimento, event_key)
            VALUES
                (:uid, :tipo, :pts, NULL, :ek)
            ON CONFLICT (event_key) DO NOTHING
            RETURNING id
            """
        ),
        {"uid": usuario_id, "tipo": tipo, "pts": resultado.pontos, "ek": event_key},
    )
    if res.scalar_one_or_none() is not None:
        return "inserida"
    return "duplicada"


def processar_penalidades_contribuicao(conn: Connection) -> ResumoProcessamentoPenalidades:
    """
    Avalia todos os analistas elegíveis na transação de `conn`.
    Idempotente: reexecutar na mesma semana não duplica desconto (event_key + ON CONFLICT).
    """
    resumo = ResumoProcessamentoPenalidades()
    p7, min_sem, p_insuf = carregar_regras_penalidade(conn)
    ano_iso, semana_iso = obter_semana_iso_utc_referencia(conn)

    analistas = listar_analistas_para_penalidade(conn)
    resumo.usuarios_encontrados = len(analistas)

    for row in analistas:
        uid = int(row["id"])
        isento = bool(row.get("em_ferias")) or bool(row.get("em_atendimento_externo"))
        if isento:
            resumo.isentos_pulados += 1
            continue

        m = coletar_metricas_contribuicao(conn, uid)
        r = avaliar_penalidades_usuario(
            aprovacoes_ultimos_7_dias=m.aprovacoes_ultimos_7_dias,
            aprovacoes_semana_iso_atual=m.aprovacoes_semana_iso_atual,
            penalidade_sem_7_dias=p7,
            minimo_semanal_sem_penalidade=min_sem,
            penalidade_semana_insuficiente=p_insuf,
            isento=False,
        )

        if not r.aplicar:
            resumo.sem_penalidade_motor += 1
            continue

        status = persistir_penalidade_se_necessario(conn, uid, r, ano_iso, semana_iso)
        if status == "inserida":
            resumo.penalidades_inseridas += 1
        elif status == "duplicada":
            resumo.penalidades_ja_existiam += 1

    return resumo
