"""
Módulo de processamento de arquivos CSV/XLSX/ZIP.
Adaptado de modules/processador_csv.py para uso com FastAPI (sem dependências Streamlit).
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import warnings
import zipfile
from datetime import datetime
from typing import Optional

import pandas as pd

# ──────────────────────────────────────────────
# Configuração LGPD
# ──────────────────────────────────────────────

_SALT_KEY = os.getenv("APP_SALT_KEY")
if not _SALT_KEY:
    warnings.warn(
        "APP_SALT_KEY não definida. Defina a variável de ambiente para garantir "
        "a segurança dos hashes LGPD. Um valor de fallback inseguro está sendo usado.",
        stacklevel=1,
    )
    _SALT_KEY = "chave_secreta_wiki_suporte_2026"

SALT = _SALT_KEY
MAX_BYTES_UPLOAD = int(os.getenv("MAX_BYTES_UPLOAD_IMPORTACAO", 10 * 1024 * 1024))  # 10 MB


# ──────────────────────────────────────────────
# Helpers LGPD
# ──────────────────────────────────────────────

def gerar_hash_lgpd(texto: str) -> str:
    """Gera um hash SHA-256 irreversível do dado sensível."""
    if not texto or (isinstance(texto, float)):
        return ""
    dado = f"{texto}{SALT}".encode("utf-8")
    return hashlib.sha256(dado).hexdigest()


def mascarar_dado_lgpd(texto: str, tipo: str = "telefone") -> str:
    """Mascara dado sensível para exibição segura."""
    if not texto or texto != texto:  # NaN check
        return ""
    s = str(texto)
    if tipo == "telefone":
        return f"(**) *****-{s[-4:]}" if len(s) >= 4 else "****"
    if tipo == "nome":
        return "CLIENTE_CONFIDENCIAL"
    return "****"


# ──────────────────────────────────────────────
# Helpers de limpeza
# ──────────────────────────────────────────────

def extrair_apenas_numeros(texto) -> str:
    if pd.isna(texto):
        return ""
    return re.sub(r"\D", "", str(texto))


def padronizar_texto(texto) -> str:
    if pd.isna(texto):
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip().upper()


def _parse_duracao_goto(val) -> float:
    """Converte duração no formato GoTo ('29s', '05m 32s') para milissegundos."""
    if pd.isna(val) or val in ("", "0s"):
        return 0.0
    s = str(val).strip().lower()
    total_ms = 0.0
    for part in re.findall(r"(\d+)\s*(h|m|s|min|sec)", s):
        n = int(part[0])
        u = part[1]
        if u == "h":
            total_ms += n * 3_600_000
        elif u in ("m", "min"):
            total_ms += n * 60_000
        else:
            total_ms += n * 1_000
    return total_ms


# ──────────────────────────────────────────────
# Leitura genérica de arquivo
# ──────────────────────────────────────────────

def ler_arquivo(conteudo: bytes, nome_arquivo: str) -> pd.DataFrame:
    """Lê bytes de um arquivo CSV ou XLSX e retorna DataFrame."""
    nome = nome_arquivo.lower()
    buf = io.BytesIO(conteudo)
    if nome.endswith(".xlsx"):
        return pd.read_excel(buf)
    return pd.read_csv(buf, sep=None, engine="python")


def extrair_csv_do_zip(conteudo: bytes) -> tuple[bytes, str]:
    """
    Procura um CSV relevante dentro do ZIP.
    Prioridade: agent-calls*.csv, depois qualquer .csv.
    Retorna (bytes_do_csv, nome_arquivo) ou lança ValueError.
    """
    with zipfile.ZipFile(io.BytesIO(conteudo), "r") as z:
        nomes = z.namelist()
        # Prioridade: agent-calls
        for name in nomes:
            if "agent-calls" in name.lower() and name.lower().endswith(".csv"):
                return z.read(name), name
        # Qualquer CSV
        for name in nomes:
            if name.lower().endswith(".csv"):
                return z.read(name), name
        raise ValueError("Nenhum arquivo CSV encontrado dentro do ZIP.")


# ──────────────────────────────────────────────
# Detecção automática de tipo
# ──────────────────────────────────────────────

def identificar_tipo_arquivo(df: pd.DataFrame) -> str:
    """
    Retorna 'goto_agent_calls', 'goto_conversations', 'multi360' ou 'desconhecido'.
    """
    cols = [str(c).strip() for c in df.columns]
    # GoTo Agent Calls
    if all(c in cols for c in ("Contact ID", "Contact Resolution", "Agent Name")):
        return "goto_agent_calls"
    # GoTo Conversations
    if "Data [America/Sao_Paulo]" in cols and "Resultado da chamada" in cols:
        return "goto_conversations"
    # Multi360
    if "PROTOCOLO" in cols:
        return "multi360"
    return "desconhecido"


# ──────────────────────────────────────────────
# Processamento GoTo Agent Calls
# ──────────────────────────────────────────────

def processar_agent_calls_goto(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Processa DataFrame do relatório GoTo 'Agent Calls'.
    Valida colunas obrigatórias antes de processar.
    """
    required = {"Contact ID", "Contact Resolution", "Agent Name"}
    missing = required - set(df_bruto.columns)
    if missing:
        raise ValueError(
            f"Arquivo GoTo Agent Calls inválido. Colunas ausentes: {', '.join(sorted(missing))}"
        )

    def _get_col(col_name: str) -> pd.Series:
        """Returns the column Series or a series of None when absent."""
        return df_bruto[col_name] if col_name in df_bruto.columns else pd.Series([None] * len(df_bruto), index=df_bruto.index)

    df = pd.DataFrame()
    df["contact_id"] = df_bruto["Contact ID"].astype(str).str.strip()
    df["queue_name"] = _get_col("Queue Name").astype(str).str.strip().replace("nan", "")

    df["contact_creation_time"] = pd.to_datetime(_get_col("Contact Creation Time"), format="mixed", errors="coerce")
    df["contact_resolution_time"] = pd.to_datetime(_get_col("Contact Resolution Time"), format="mixed", errors="coerce")
    df["time_in_queue_millis"] = pd.to_numeric(_get_col("Time in Queue (millis)"), errors="coerce").astype("Int64")
    df["talk_time_millis"] = pd.to_numeric(_get_col("Talk Time (millis)"), errors="coerce").astype("Int64")
    df["wrap_time_millis"] = pd.to_numeric(_get_col("Wrap Time (millis)"), errors="coerce").astype("Int64")
    df["handle_time_millis"] = pd.to_numeric(_get_col("Handle Time (millis)"), errors="coerce").astype("Int64")
    df["contact_resolution"] = _get_col("Contact Resolution").astype(str).str.strip().replace("nan", "")
    df["contact_type"] = _get_col("Contact Type").astype(str).str.strip().replace("nan", "")

    participant_val = _get_col("Contact Participant Value").astype(str).str.strip()
    telefone_raw = participant_val.apply(extrair_apenas_numeros)
    df["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
    df["telefone_origem"] = participant_val.replace("nan", "")
    df["contact_participant_value"] = participant_val

    df["agent_name"] = _get_col("Agent Name").astype(str).str.strip().replace("nan", "")
    df["data_importacao"] = datetime.now().isoformat()

    # Remove timezone para consistência
    for col in ("contact_creation_time", "contact_resolution_time"):
        try:
            if df[col].dt.tz is not None:
                df[col] = df[col].dt.tz_localize(None)
            df[col] = df[col].astype(str).replace("NaT", "")
        except Exception:
            df[col] = df[col].astype(str).replace("NaT", "")

    return df


# ──────────────────────────────────────────────
# Processamento GoTo Conversations
# ──────────────────────────────────────────────

def _find_column_by_sample(df: pd.DataFrame, amostras: list) -> Optional[pd.Series]:
    for col in df.columns:
        s = df[col].astype(str).str.strip().str.lower()
        for a in amostras:
            if (s == a.lower()).any():
                return df[col]
    return None


def _find_first_datetime_column(df: pd.DataFrame) -> Optional[pd.Series]:
    for col in df.columns:
        try:
            sample = df[col].dropna().astype(str).iloc[0] if len(df) else ""
            if "T" in sample and ("Z" in sample or "-" in sample[-6:] or "+" in sample):
                return df[col]
        except Exception:
            continue
    return None


def _find_column_with_phone_like(df: pd.DataFrame) -> Optional[pd.Series]:
    for col in df.columns:
        try:
            s = df[col].astype(str).str.replace(r"\D", "", regex=True)
            if s.str.len().ge(10).any():
                return df[col]
        except Exception:
            continue
    return None


def processar_goto_conversations(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Processa DataFrame do relatório GoTo Conversations."""
    df = pd.DataFrame()

    # Formato padrão PT-BR
    if "Data [America/Sao_Paulo]" in df_bruto.columns and "Resultado da chamada" in df_bruto.columns:
        data_col = df_bruto["Data [America/Sao_Paulo]"]
        try:
            datas = pd.to_datetime(data_col, format="ISO8601", errors="coerce")
        except Exception:
            datas = pd.to_datetime(data_col, format="mixed", errors="coerce")
        if datas.dt.tz is not None:
            datas = datas.dt.tz_localize(None)
        df["data_chamada"] = datas.astype(str).replace("NaT", "")
        df["id_conversa"] = df_bruto.get("Conversation space id", pd.Series("", index=df_bruto.index)).astype(str).str.strip().replace("nan", "")
        df["duracao_ms"] = pd.to_numeric(df_bruto.get("Duração [milissegundos]"), errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
        df["direcao"] = df_bruto.get("Direção", pd.Series(dtype=str)).apply(padronizar_texto)
        df["resultado"] = df_bruto["Resultado da chamada"].astype(str).apply(padronizar_texto)
        telefone_raw = df_bruto.get("De", pd.Series(dtype=str)).apply(extrair_apenas_numeros)
        df["participantes"] = df_bruto.get("Participantes", pd.Series("", index=df_bruto.index)).astype(str).replace("nan", "")
        df["gravado"] = df_bruto.get("Gravações", pd.Series("false", index=df_bruto.index)).astype(str).str.lower()
    else:
        col_resultado = _find_column_by_sample(
            df_bruto, ["Chamada perdida", "Encerrada com sucesso", "Chamada do plano de discagem encerrada"]
        )
        col_data = _find_first_datetime_column(df_bruto)
        if col_data is None or col_resultado is None:
            raise ValueError("Arquivo GoTo Conversations não reconhecido: faltam colunas de data e/ou resultado.")
        datas = pd.to_datetime(col_data, format="mixed", errors="coerce")
        if datas.dt.tz is not None:
            datas = datas.dt.tz_localize(None)
        df["data_chamada"] = datas.astype(str).replace("NaT", "")
        df["resultado"] = col_resultado.astype(str).apply(padronizar_texto)
        id_col = df_bruto.get("Conversation space id") or df_bruto.get("Call ID")
        df["id_conversa"] = id_col.astype(str).str.strip().replace("nan", "") if id_col is not None else pd.Series("", index=df_bruto.index)
        col_duracao = df_bruto.get("Duração [milissegundos]") or df_bruto.get("Duration (ms)")
        col_duracao_str = _find_column_by_sample(df_bruto, ["29s", "05m 32s", "0s"])
        if col_duracao is not None:
            df["duracao_ms"] = pd.to_numeric(col_duracao, errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
        elif col_duracao_str is not None:
            df["duracao_ms"] = col_duracao_str.apply(lambda x: str(int(_parse_duracao_goto(x))))
        else:
            df["duracao_ms"] = "0"
        col_direcao = df_bruto.get("Direção") or df_bruto.get("Direction")
        df["direcao"] = (col_direcao if col_direcao is not None else pd.Series("", index=df_bruto.index)).apply(padronizar_texto)
        telefone_raw = _find_column_with_phone_like(df_bruto)
        if telefone_raw is not None:
            telefone_raw = telefone_raw.apply(extrair_apenas_numeros)
        else:
            telefone_raw = pd.Series("", index=df_bruto.index)
        df["participantes"] = df_bruto.get("Participantes", pd.Series("", index=df_bruto.index)).astype(str).replace("nan", "")
        df["gravado"] = "false"

    df["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
    df["data_importacao"] = datetime.now().isoformat()
    return df


# ──────────────────────────────────────────────
# Processamento Multi360
# ──────────────────────────────────────────────

def processar_multi360(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Processa DataFrame do relatório Multi360 / Plantões."""
    if "PROTOCOLO" not in df_bruto.columns:
        raise ValueError("Arquivo Multi360 inválido: coluna 'PROTOCOLO' ausente.")

    df = pd.DataFrame()

    df["protocolo"] = pd.to_numeric(df_bruto["PROTOCOLO"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    df["origem"] = df_bruto.get("ORIGEM", pd.Series("", index=df_bruto.index)).apply(padronizar_texto)
    df["status"] = df_bruto.get("STATUS", pd.Series("", index=df_bruto.index)).apply(padronizar_texto)
    df["atendente"] = df_bruto.get("ATENDENTE", pd.Series("", index=df_bruto.index)).astype(str).str.strip().replace("nan", "")
    df["departamento"] = df_bruto.get("DEPARTAMENTO", pd.Series("", index=df_bruto.index)).astype(str).str.strip().replace("nan", "")

    # LGPD – nomes
    if "NOME" in df_bruto.columns:
        df["nome_contato"] = df_bruto["NOME"].apply(lambda x: mascarar_dado_lgpd(x, "nome"))
    else:
        df["nome_contato"] = ""

    # LGPD – telefones
    if "NUMERO" in df_bruto.columns:
        num_raw = df_bruto["NUMERO"].apply(extrair_apenas_numeros)
        df["telefone_hash"] = num_raw.apply(gerar_hash_lgpd)
        df["numero_telefone"] = num_raw.apply(lambda x: mascarar_dado_lgpd(x, "telefone"))
    else:
        df["telefone_hash"] = ""
        df["numero_telefone"] = ""

    for src_col, dst_col, fmt in [
        ("DATA", "data_inicio", "%d/%m/%Y %H:%M"),
        ("DATAFINALIZACAO", "data_finalizacao", "%d/%m/%Y %H:%M"),
        ("DATAULTIMAMENSAGEM", "data_ultima_mensagem", "%d/%m/%Y %H:%M"),
    ]:
        if src_col in df_bruto.columns:
            df[dst_col] = pd.to_datetime(df_bruto[src_col], format=fmt, errors="coerce").astype(str).replace("NaT", "")
        else:
            df[dst_col] = ""

    df["avaliacao"] = pd.to_numeric(df_bruto.get("AVALIACAO", pd.Series(dtype=str)), errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    df["data_importacao"] = datetime.now().isoformat()

    return df


# ──────────────────────────────────────────────
# Ponto de entrada principal
# ──────────────────────────────────────────────

def processar_arquivo(conteudo: bytes, nome_arquivo: str) -> dict:
    """
    Recebe bytes do arquivo enviado pelo frontend.
    Retorna dict com: tipo, total_registros, colunas, preview (até 15 linhas), dados completos.
    """
    nome_lower = nome_arquivo.lower()

    # ZIP → extrai CSV interno
    if nome_lower.endswith(".zip"):
        conteudo, nome_arquivo = extrair_csv_do_zip(conteudo)
        nome_lower = nome_arquivo.lower()

    df_bruto = ler_arquivo(conteudo, nome_arquivo)
    tipo = identificar_tipo_arquivo(df_bruto)

    if tipo == "goto_agent_calls":
        df = processar_agent_calls_goto(df_bruto)
    elif tipo == "goto_conversations":
        df = processar_goto_conversations(df_bruto)
    elif tipo == "multi360":
        df = processar_multi360(df_bruto)
    else:
        raise ValueError(
            "Tipo de arquivo não reconhecido. "
            "Verifique se o arquivo possui as colunas esperadas para GoTo ou Multi360."
        )

    # Converte NaN/NaT para None antes de serializar
    df_json = df.where(pd.notnull(df), None)
    preview = df_json.head(15).to_dict(orient="records")
    dados = df_json.to_dict(orient="records")

    return {
        "tipo": tipo,
        "total_registros": len(df),
        "colunas": list(df.columns),
        "preview": preview,
        "dados": dados,
    }
