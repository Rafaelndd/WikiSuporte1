"""
Dados do Dashboard Chamados (paridade com pages/3_*.py).

Carrega chamados_tecnuv com período e analista; retorna lista de dict para ui.aggrid.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, List, Optional

import pandas as pd
from sqlalchemy import text

from modules.database import get_connection


def carregar_chamados_tecnuv(
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    analista: Optional[str] = None,
) -> tuple[pd.DataFrame, List[dict[str, Any]]]:
    """
    Carrega chamados_tecnuv do PostgreSQL e aplica filtros.
    Retorna (df, rows) onde rows é lista de dict para ui.aggrid.
    """
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM chamados_tecnuv", engine)
    except Exception:
        return pd.DataFrame(), []

    if df.empty:
        return df, []

    if "data_abertura" in df.columns:
        df["data_abertura"] = pd.to_datetime(df["data_abertura"], errors="coerce")
    if "data_encerramento" in df.columns:
        df["data_encerramento"] = pd.to_datetime(df["data_encerramento"], errors="coerce")

    col_epsy = df.get("usuario_epsy") if "usuario_epsy" in df.columns else df.get(
        "nome_analista_epsy", pd.Series(dtype=object)
    )
    df["usuario_epsy"] = col_epsy.fillna("Não Informado").astype(str)
    df["cliente_nome"] = df.get("cliente_nome", pd.Series(dtype=str)).fillna("Não Informado").astype(str)

    if data_inicio is not None:
        df = df[df["data_abertura"] >= pd.to_datetime(data_inicio)]
    if data_fim is not None:
        df = df[df["data_abertura"] < pd.to_datetime(data_fim) + timedelta(days=1)]
    if analista and analista != "Todos":
        df = df[df["usuario_epsy"] == analista]

    # Colunas para exibição na tabela (evitar HTML e colunas grandes)
    cols_exibir = ["nr_chamado", "cliente_nome", "usuario_epsy", "status_atual", "data_abertura", "data_encerramento"]
    cols_exibir = [c for c in cols_exibir if c in df.columns]
    df_out = df[cols_exibir].copy()
    for col in ["data_abertura", "data_encerramento"]:
        if col in df_out.columns:
            df_out[col] = df_out[col].dt.strftime("%d/%m/%Y %H:%M").fillna("")

    rows = df_out.to_dict("records")
    for r in rows:
        for k, v in r.items():
            if pd.isna(v):
                r[k] = ""
    return df, rows


def lista_analistas_chamados() -> List[str]:
    """Lista de analistas únicos para o filtro (Todos + nomes)."""
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT * FROM chamados_tecnuv LIMIT 1", engine)
        col = "usuario_epsy" if "usuario_epsy" in df.columns else "nome_analista_epsy"
        df = pd.read_sql(f"SELECT DISTINCT {col} AS nome FROM chamados_tecnuv", engine)
        nomes = sorted(
            a for a in df["nome"].dropna().astype(str).unique().tolist()
            if a.strip() and a.strip() != "Não Informado"
        )
        return ["Todos"] + nomes
    except Exception:
        return ["Todos"]
