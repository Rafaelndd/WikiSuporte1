"""
Rotina de penalidades por contribuição: isenções, métricas e eventos idempotentes em user_xp_events.
Requer migrações: contribution_scoring_rules (com colunas de penalidade), user_xp_events, colunas em base_conhecimento.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TypedDict

from sqlalchemy import Connection, text

from app.core.penalidades_xp import ResultadoPenalidade, avaliar_penalidades_usuario

ORIGEM_CONHECIMENTO_SUPORTE = "CONHECIMENTO_SUPORTE"
JANELA_CARENCIA_DIAS_DEFAULT = 7
MAX_DESCONTO_SEMANAL_XP_DEFAULT = 100


class ResumoPenalidadesDict(TypedDict):
    """Resumo exposto à UI / integrações (valores inteiros)."""

    processados: int
    penalizados: int
    isentos: int
    usuarios_listados: int
    penalidades_ja_existiam: int
    sem_penalidade_motor: int


@dataclass
class ResumoProcessamentoPenalidades:
    usuarios_encontrados: int = 0
    isentos_pulados: int = 0
    sem_penalidade_motor: int = 0
    penalidades_inseridas: int = 0
    penalidades_ja_existiam: int = 0


def resumo_para_dict(r: ResumoProcessamentoPenalidades) -> ResumoPenalidadesDict:
    processados = r.usuarios_encontrados - r.isentos_pulados
    return {
        "processados": processados,
        "penalizados": r.penalidades_inseridas,
        "isentos": r.isentos_pulados,
        "usuarios_listados": r.usuarios_encontrados,
        "penalidades_ja_existiam": r.penalidades_ja_existiam,
        "sem_penalidade_motor": r.sem_penalidade_motor,
    }


def carregar_regras_penalidade(conn: Connection) -> tuple[int, int, int, int, int]:
    row = conn.execute(
        text(
            """
            SELECT penalidade_sem_7_dias,
                   minimo_semanal_sem_penalidade,
                   penalidade_semana_insuficiente,
                   COALESCE(janela_carencia_dias, :carencia_default) AS janela_carencia_dias,
                   COALESCE(max_desconto_semanal_xp, :max_desc_default) AS max_desconto_semanal_xp
            FROM contribution_scoring_rules
            WHERE id = 1
            """
        ),
        {
            "carencia_default": JANELA_CARENCIA_DIAS_DEFAULT,
            "max_desc_default": MAX_DESCONTO_SEMANAL_XP_DEFAULT,
        },
    ).mappings().first()
    if not row:
        return (0, 0, 0, JANELA_CARENCIA_DIAS_DEFAULT, MAX_DESCONTO_SEMANAL_XP_DEFAULT)
    return (
        int(row["penalidade_sem_7_dias"]),
        int(row["minimo_semanal_sem_penalidade"]),
        int(row["penalidade_semana_insuficiente"]),
        int(row["janela_carencia_dias"]),
        int(row["max_desconto_semanal_xp"]),
    )


def listar_analistas_para_penalidade(conn: Connection) -> list[Mapping[str, Any]]:
    result = conn.execute(
        text(
            """
            SELECT id, perfil, ativo, em_ferias, em_atendimento_externo, data_criacao
            FROM usuarios
            WHERE COALESCE(ativo, FALSE) = TRUE
              AND lower(trim(COALESCE(perfil, ''))) = 'analista'
            ORDER BY id
            """
        )
    )
    return list(result.mappings().all())


def usuario_em_janela_carencia(
    conn: Connection,
    usuario_id: int,
    data_criacao: Any,
    *,
    janela_dias: int = JANELA_CARENCIA_DIAS_DEFAULT,
) -> bool:
    """
    Janela de carência para:
    - colaborador novo (criado nos últimos N dias), ou
    - retorno recente de férias/atendimento externo (flag true -> false em auditoria).
    """
    dias = max(1, int(janela_dias))

    if data_criacao is not None:
        try:
            diff_novo = conn.execute(
                text(
                    """
                    SELECT (
                        DATE(timezone('UTC', CURRENT_TIMESTAMP))
                        - DATE(timezone('UTC', CAST(:dc AS timestamptz)))
                    )::integer AS dias
                    """
                ),
                {"dc": data_criacao},
            ).mappings().one()
            if int(diff_novo["dias"]) < dias:
                return True
        except Exception:
            pass

    try:
        row = conn.execute(
            text(
                """
                SELECT 1
                FROM log_auditoria_usuarios
                WHERE operacao = 'UPDATE'
                  AND data_hora >= (CURRENT_TIMESTAMP - (:dias * INTERVAL '1 day'))
                  AND COALESCE((dados_novos->>'id')::integer, (dados_anteriores->>'id')::integer) = :uid
                  AND (
                    (lower(COALESCE(dados_anteriores->>'em_ferias', 'false')) = 'true'
                     AND lower(COALESCE(dados_novos->>'em_ferias', 'false')) = 'false')
                    OR
                    (lower(COALESCE(dados_anteriores->>'em_atendimento_externo', 'false')) = 'true'
                     AND lower(COALESCE(dados_novos->>'em_atendimento_externo', 'false')) = 'false')
                  )
                LIMIT 1
                """
            ),
            {"uid": int(usuario_id), "dias": dias},
        ).fetchone()
        return row is not None
    except Exception:
        return False


def obter_semana_iso_utc_referencia(conn: Connection) -> tuple[str, str]:
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


def coletar_metricas_contribuicao(conn: Connection, usuario_id: int) -> tuple[int, int, int]:
    return (
        dias_desde_ultima_aprovacao(conn, usuario_id),
        contar_aprovacoes_ultimos_7_dias_utc(conn, usuario_id),
        contar_aprovacoes_semana_iso_atual_utc(conn, usuario_id),
    )


def montar_event_key_penalidade(
    ano_iso: str, semana_iso: str, usuario_id: int, codigo_penalidade: str
) -> str:
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
    Avalia analistas ativos (perfil analista) na transação de `conn`.
    Retorna o resumo estruturado; use `resumo_para_dict` na UI (Streamlit, APIs).
    """
    resumo = ResumoProcessamentoPenalidades()
    p7, min_sem, p_insuf, carencia_dias, max_desc = carregar_regras_penalidade(conn)
    ano_iso, semana_iso = obter_semana_iso_utc_referencia(conn)

    analistas = listar_analistas_para_penalidade(conn)
    resumo.usuarios_encontrados = len(analistas)

    for row in analistas:
        uid = int(row["id"])
        isento = bool(row.get("em_ferias")) or bool(row.get("em_atendimento_externo"))
        if isento:
            resumo.isentos_pulados += 1
            continue
        em_carencia = usuario_em_janela_carencia(
            conn,
            uid,
            row.get("data_criacao"),
            janela_dias=carencia_dias,
        )
        if em_carencia:
            resumo.isentos_pulados += 1
            continue

        _, a7, sem = coletar_metricas_contribuicao(conn, uid)
        r = avaliar_penalidades_usuario(
            aprovacoes_ultimos_7_dias=a7,
            aprovacoes_semana_iso_atual=sem,
            penalidade_sem_7_dias=p7,
            minimo_semanal_sem_penalidade=min_sem,
            penalidade_semana_insuficiente=p_insuf,
            isento=False,
            max_desconto_semanal=max_desc,
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
