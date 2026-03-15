"""
Dados da Home: alertas e KPIs (mesmas queries do app.py Streamlit).

Sem cache decorator; no NiceGUI a atualização é sob demanda (botão ou refresh).
"""
from __future__ import annotations

import logging
from typing import Any, Tuple

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection

LOG = logging.getLogger(__name__)


def obter_alertas_usuario(usuario_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Alertas de plantão e validações pendentes para o usuário."""
    if not usuario_id:
        return pd.DataFrame(), pd.DataFrame()
    engine = get_connection()
    try:
        with engine.connect() as conn:
            q_plantao = text("""
                SELECT data_hora_entrada, data_hora_saida
                FROM plantoes_epsy
                WHERE id_analista_epsy = :uid AND data_hora_entrada::DATE = CURRENT_DATE
            """)
            df_plantao = pd.read_sql(q_plantao, conn, params={"uid": usuario_id})
            q_release = text("""
                SELECT r.versao_release AS versao, c.id_chamado AS nr_chamado
                FROM ciclos_homologacao ch
                JOIN releases r ON ch.id_release = r.id_release
                JOIN chamados c ON ch.id_chamado = c.id_chamado
                JOIN chamados_tecnuv ct ON ct.nr_chamado::text = c.id_chamado AND ct.id_analista_epsy = :uid
                WHERE ch.status_teste = 'Aguardando'
            """)
            df_release = pd.read_sql(q_release, conn, params={"uid": usuario_id})
            return df_plantao, df_release
    except Exception as e:
        LOG.exception("Erro ao buscar alertas para usuário %s: %s", usuario_id, e)
        return pd.DataFrame(), pd.DataFrame()


def obter_kpis_home(usuario_id: int) -> dict[str, Any]:
    """KPIs de gamificação (XP, ranking, missões)."""
    kpis: dict[str, Any] = {
        "minhas_dicas": 0,
        "meu_xp": 0,
        "posicao_ranking": "-",
        "impacto_visualizacoes": 0,
        "upvotes_recebidos": 0,
        "nivel_atual": "Iniciante 🌱",
        "progresso_nivel": 0.0,
        "missoes_ativas": [],
    }
    engine = get_connection()
    try:
        with engine.connect() as conn:
            res_user = conn.execute(
                text("""
                    SELECT COALESCE(xp_total, 0) as xp, COALESCE(medalha_atual, 'Iniciante 🌱') as medalha
                    FROM usuarios WHERE id = :uid
                """),
                {"uid": usuario_id},
            ).fetchone()
            if res_user:
                kpis["meu_xp"] = res_user.xp
                kpis["nivel_atual"] = res_user.medalha
                kpis["progresso_nivel"] = float((res_user.xp % 1000) / 1000.0)

            res_stats = conn.execute(
                text("""
                    SELECT COUNT(id) as total_posts,
                           COALESCE(SUM(qtd_upvotes), 0) as total_upvotes,
                           COALESCE(SUM(qtd_visualizacoes), 0) as total_views
                    FROM base_conhecimento
                    WHERE id_analista_autor = :uid AND status = 'APROVADO' AND origem = 'CONHECIMENTO_SUPORTE'
                """),
                {"uid": usuario_id},
            ).fetchone()
            if res_stats:
                kpis["minhas_dicas"] = res_stats.total_posts
                kpis["upvotes_recebidos"] = res_stats.total_upvotes
                kpis["impacto_visualizacoes"] = res_stats.total_views

            rank_val = conn.execute(
                text("""
                    SELECT posicao FROM (
                        SELECT id, RANK() OVER(ORDER BY xp_total DESC) as posicao
                        FROM usuarios WHERE ativo = true
                    ) r WHERE id = :uid
                """),
                {"uid": usuario_id},
            ).scalar()
            kpis["posicao_ranking"] = f"{rank_val}º Lugar" if rank_val else "N/A"

            if kpis["upvotes_recebidos"] < 10:
                kpis["missoes_ativas"].append("⭐ **Missão:** Alcance 10 curtidas para subir de nível!")
            voto_hoje = conn.execute(
                text("""
                    SELECT EXISTS(
                        SELECT 1 FROM base_conhecimento_votos
                        WHERE id_analista_votante = :uid AND data_voto >= now() - interval '24 hours'
                    )
                """),
                {"uid": usuario_id},
            ).scalar()
            if not voto_hoje:
                kpis["missoes_ativas"].append("🔍 **Missão:** Avalie a dica de um colega hoje!")
    except Exception as e:
        LOG.exception("Erro ao carregar KPIs: %s", e)
    return kpis
