"""
Renderização da tabela de regras de contribuição/penalidade para UI Streamlit.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy import text

from modules.database import get_connection


def carregar_parametros_contribuicao_ui() -> dict[str, int]:
    """Lê parâmetros atuais da tabela contribution_scoring_rules (id=1)."""
    defaults = {
        "pontos_evento_passado": 90,
        "multiplicador_diario_apos_qtd": 3,
        "multiplicador_diario_valor": 2,
        "bonus_semanal_meta_qtd": 15,
        "bonus_semanal_meta_pontos": 1000,
        "minimo_semanal_sem_penalidade": 5,
        "penalidade_sem_7_dias": 100,
        "penalidade_semana_insuficiente": 100,
        "janela_carencia_dias": 7,
        "max_desconto_semanal_xp": 100,
    }
    try:
        engine = get_connection()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS contribution_scoring_rules (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        pontos_evento_passado INTEGER NOT NULL DEFAULT 90,
                        multiplicador_diario_apos_qtd INTEGER NOT NULL DEFAULT 3,
                        multiplicador_diario_valor INTEGER NOT NULL DEFAULT 2,
                        bonus_semanal_meta_qtd INTEGER NOT NULL DEFAULT 15,
                        bonus_semanal_meta_pontos INTEGER NOT NULL DEFAULT 1000,
                        penalidade_sem_7_dias INTEGER NOT NULL DEFAULT 100,
                        minimo_semanal_sem_penalidade INTEGER NOT NULL DEFAULT 5,
                        penalidade_semana_insuficiente INTEGER NOT NULL DEFAULT 100,
                        janela_carencia_dias INTEGER NOT NULL DEFAULT 7,
                        max_desconto_semanal_xp INTEGER NOT NULL DEFAULT 100,
                        atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            conn.execute(text("INSERT INTO contribution_scoring_rules (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
            row = conn.execute(
                text(
                    """
                    SELECT pontos_evento_passado,
                           multiplicador_diario_apos_qtd,
                           multiplicador_diario_valor,
                           bonus_semanal_meta_qtd,
                           bonus_semanal_meta_pontos,
                           minimo_semanal_sem_penalidade,
                           penalidade_sem_7_dias,
                           penalidade_semana_insuficiente,
                           COALESCE(janela_carencia_dias, 7) AS janela_carencia_dias,
                           COALESCE(max_desconto_semanal_xp, 100) AS max_desconto_semanal_xp
                    FROM contribution_scoring_rules
                    WHERE id = 1
                    """
                )
            ).mappings().first()
        if not row:
            return defaults
        merged = defaults.copy()
        for k in merged:
            merged[k] = int(row.get(k, merged[k]))
        return merged
    except Exception:
        return defaults


def render_contrib_rules_table(*, compact: bool = False) -> None:
    """
    Exibe tabela visual com regras atuais de contribuições e penalidades.

    `compact=True` reduz o tamanho para encaixe melhor em páginas densas.
    """
    cfg = carregar_parametros_contribuicao_ui()
    pad = "0.55rem 0.7rem" if compact else "0.68rem 0.8rem"
    font = "0.88rem" if compact else "0.93rem"
    st.markdown(
        f"""
        <style>
        .ws-rules-wrap {{
            border: 1px solid rgba(107, 114, 128, 0.35);
            border-radius: 12px;
            overflow: hidden;
            margin: 0.35rem 0 0.25rem 0;
        }}
        .ws-rules-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: {font};
        }}
        .ws-rules-table thead th {{
            text-align: left;
            padding: {pad};
            background: rgba(21, 120, 154, 0.14);
            border-bottom: 1px solid rgba(21, 120, 154, 0.35);
        }}
        .ws-rules-table tbody td {{
            padding: {pad};
            border-bottom: 1px dashed rgba(107, 114, 128, 0.35);
            vertical-align: top;
            line-height: 1.45;
        }}
        .ws-rules-table tbody tr:last-child td {{
            border-bottom: none;
        }}
        .ws-tag-green {{
            background: rgba(34, 197, 94, 0.2);
            border: 1px solid rgba(22, 163, 74, 0.5);
            border-radius: 999px;
            padding: 0.12rem 0.5rem;
            font-weight: 700;
            color: #166534;
            display: inline-block;
        }}
        .ws-tag-red {{
            background: rgba(239, 68, 68, 0.16);
            border: 1px solid rgba(220, 38, 38, 0.5);
            border-radius: 999px;
            padding: 0.12rem 0.5rem;
            font-weight: 700;
            color: #991b1b;
            display: inline-block;
        }}
        html[data-theme="dark"] .ws-rules-table thead th {{
            background: rgba(21, 120, 154, 0.25);
            border-bottom-color: rgba(94, 184, 217, 0.45);
        }}
        html[data-theme="dark"] .ws-tag-green {{
            color: #86efac;
            border-color: rgba(74, 222, 128, 0.6);
            background: rgba(22, 163, 74, 0.25);
        }}
        html[data-theme="dark"] .ws-tag-red {{
            color: #fca5a5;
            border-color: rgba(248, 113, 113, 0.6);
            background: rgba(185, 28, 28, 0.28);
        }}
        </style>
        <div class="ws-rules-wrap">
            <table class="ws-rules-table" aria-label="Regras de contribuição e penalidades">
                <thead>
                    <tr>
                        <th>Regra</th>
                        <th>Como funciona</th>
                        <th>Resultado</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>🟢 Evento Atual</td>
                        <td>0-7 dias: 100 | 8-14: 75 | 15-21: 25 | &gt;21: 0</td>
                        <td><span class="ws-tag-green">Pontuação por prazo</span></td>
                    </tr>
                    <tr>
                        <td>🟢 Evento Passado</td>
                        <td>Valor fixo por contribuição aprovada</td>
                        <td><span class="ws-tag-green">+{cfg['pontos_evento_passado']} XP</span></td>
                    </tr>
                    <tr>
                        <td>🟢 Bônus diário</td>
                        <td>A partir da {cfg['multiplicador_diario_apos_qtd']}ª aprovação no mesmo dia</td>
                        <td><span class="ws-tag-green">{cfg['multiplicador_diario_valor']}x na pontuação</span></td>
                    </tr>
                    <tr>
                        <td>🟢 Bônus semanal</td>
                        <td>Ao atingir {cfg['bonus_semanal_meta_qtd']} aprovações na semana ISO</td>
                        <td><span class="ws-tag-green">+{cfg['bonus_semanal_meta_pontos']} XP</span></td>
                    </tr>
                    <tr>
                        <td>🟡 Janela de carência</td>
                        <td>Novo colaborador ou retorno recente de férias/atendimento externo</td>
                        <td><span class="ws-tag-green">{cfg['janela_carencia_dias']} dias sem penalidade</span></td>
                    </tr>
                    <tr>
                        <td>🔴 Penalidade semanal</td>
                        <td>
                            Sem 7 dias de aprovação (até -{cfg['penalidade_sem_7_dias']}) ou
                            abaixo da meta semanal de {cfg['minimo_semanal_sem_penalidade']}
                            aprovações (até -{cfg['penalidade_semana_insuficiente']})
                        </td>
                        <td><span class="ws-tag-red">Desconto limitado a -{cfg['max_desconto_semanal_xp']} XP</span></td>
                    </tr>
                    <tr>
                        <td>🛡️ Proteção de saldo</td>
                        <td>Mesmo com descontos, o total acumulado não fica negativo</td>
                        <td><span class="ws-tag-green">XP mínimo = 0</span></td>
                    </tr>
                </tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
