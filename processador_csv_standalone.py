"""
Processador Standalone de CSVs – WikiSuporte
=============================================
Extrai, trata e exibe resultados dos arquivos CSV exportados pelo GoTo Connect
(Conversations, Call Report e Agent Calls) e pelo Multi360.

Uso direto via terminal:
    python processador_csv_standalone.py caminho/para/arquivo.csv
    python processador_csv_standalone.py pasta/com/csvs/
    python processador_csv_standalone.py arquivo1.csv arquivo2.csv

Sem argumentos, varre o diretório atual em busca de arquivos CSV/XLSX.

Dependências: pandas, openpyxl (pip install pandas openpyxl)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Configuração de segurança (LGPD)
# ---------------------------------------------------------------------------

SALT = os.getenv("APP_SALT_KEY", "chave_secreta_wiki_suporte_2026")


# ---------------------------------------------------------------------------
# Utilitários de LGPD
# ---------------------------------------------------------------------------


def gerar_hash_lgpd(texto: str) -> str:
    """Hash SHA-256 irreversível do dado sensível (com SALT)."""
    if not texto or (isinstance(texto, float) and pd.isna(texto)) or texto == "":
        return ""
    dado = f"{texto}{SALT}".encode("utf-8")
    return hashlib.sha256(dado).hexdigest()


def mascarar_dado_lgpd(texto: str, tipo: str = "telefone") -> str:
    """Mascara dado sensível para exibição segura."""
    if not texto or (isinstance(texto, float) and pd.isna(texto)) or texto == "":
        return ""
    texto_str = str(texto)
    if tipo == "telefone":
        return f"(**) *****-{texto_str[-4:]}" if len(texto_str) >= 4 else "****"
    if tipo == "nome":
        return "CLIENTE_CONFIDENCIAL"
    return "****"


# ---------------------------------------------------------------------------
# Utilitários de limpeza
# ---------------------------------------------------------------------------


def extrair_apenas_numeros(texto) -> str:
    """Remove tudo que não for dígito."""
    if pd.isna(texto):
        return ""
    return re.sub(r"\D", "", str(texto))


def padronizar_texto(texto) -> str:
    """Strip, espaço simples e maiúsculas."""
    if pd.isna(texto):
        return ""
    return re.sub(r"\s+", " ", str(texto)).strip().upper()


# ---------------------------------------------------------------------------
# Leitura dinâmica de arquivo (CSV ou XLSX)
# ---------------------------------------------------------------------------


def ler_arquivo_dinamico(arquivo) -> pd.DataFrame:
    """Lê CSV ou XLSX a partir de caminho (str/Path) ou objeto file-like."""
    if isinstance(arquivo, (str, Path)):
        nome = str(arquivo).lower()
        if nome.endswith(".xlsx"):
            return pd.read_excel(arquivo, engine="openpyxl")
        return pd.read_csv(arquivo, sep=None, engine="python")
    # file-like
    nome = getattr(arquivo, "name", "").lower()
    if nome.endswith(".xlsx"):
        return pd.read_excel(arquivo, engine="openpyxl")
    return pd.read_csv(arquivo, sep=None, engine="python")


# ---------------------------------------------------------------------------
# Detecção do tipo de arquivo
# ---------------------------------------------------------------------------

_TIPO_DESCONHECIDO = "DESCONHECIDO"
_TIPO_GOTO = "GOTO"
_TIPO_GOTO_AGENT_CALLS = "GOTO_AGENT_CALLS"
_TIPO_MULTI360 = "MULTI360"


def detectar_tipo(df: pd.DataFrame) -> str:
    """Detecta o tipo de relatório a partir das colunas do DataFrame."""
    cols = {str(c).strip() for c in df.columns}
    # Agent Calls do GoTo
    if {"Contact ID", "Contact Resolution", "Agent Name"}.issubset(cols):
        return _TIPO_GOTO_AGENT_CALLS
    # Conversations / Call Report do GoTo
    if "Resultado da chamada" in cols or "Resultado" in cols:
        return _TIPO_GOTO
    # GoTo com colunas em inglês
    if "Call Result" in cols or "Start Time (local)" in cols:
        return _TIPO_GOTO
    # Multi360
    if "PROTOCOLO" in cols or ("ORIGEM" in cols and "ATENDENTE" in cols):
        return _TIPO_MULTI360
    return _TIPO_DESCONHECIDO


# ---------------------------------------------------------------------------
# Helpers de colunas para GoTo
# ---------------------------------------------------------------------------


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


def _parse_duracao_goto(val) -> float:
    """Converte duração GoTo ('29s', '05m 32s') para milissegundos."""
    if pd.isna(val) or val in ("", "0s"):
        return 0.0
    s = str(val).strip().lower()
    total_ms = 0.0
    for n, u in re.findall(r"(\d+)\s*(h|m|s|min|sec)", s):
        n_int = int(n)
        if u == "h":
            total_ms += n_int * 3_600_000
        elif u in ("m", "min"):
            total_ms += n_int * 60_000
        else:
            total_ms += n_int * 1_000
    return total_ms


# ---------------------------------------------------------------------------
# Processamento GoTo Conversations / Call Report
# ---------------------------------------------------------------------------


def processar_csv_goto(arquivo) -> pd.DataFrame:
    """
    Processa CSV de atendimentos GoTo (Conversations ou Call Report).

    Retorna DataFrame com colunas:
        data_chamada, id_conversa, duracao_ms, direcao, resultado,
        telefone_hash, telefone_origem, participantes, gravado, data_importacao
    """
    df_bruto = ler_arquivo_dinamico(arquivo)
    df = pd.DataFrame()

    formato_conversations = (
        "Data [America/Sao_Paulo]" in df_bruto.columns
        and "Resultado da chamada" in df_bruto.columns
    )

    if formato_conversations:
        data_col = df_bruto["Data [America/Sao_Paulo]"]
        try:
            datas = pd.to_datetime(data_col, format="ISO8601", errors="coerce")
        except Exception:
            datas = pd.to_datetime(data_col, format="mixed", errors="coerce")
        if datas.dt.tz is not None:
            datas = datas.dt.tz_localize(None)
        df["data_chamada"] = datas
        df["id_conversa"] = (
            df_bruto.get("Conversation space id", "").astype(str).str.strip().replace("nan", "")
        )
        df["duracao_ms"] = pd.to_numeric(
            df_bruto.get("Duração [milissegundos]"), errors="coerce"
        ).astype("Int64")
        df["direcao"] = df_bruto.get("Direção", pd.Series(dtype=str)).apply(padronizar_texto)
        df["resultado"] = df_bruto["Resultado da chamada"].astype(str).apply(padronizar_texto)
        telefone_raw = df_bruto.get("De", pd.Series(dtype=str)).apply(extrair_apenas_numeros)
        df["participantes"] = df_bruto.get("Participantes", "").astype(str).replace("nan", "")
        df["gravado"] = df_bruto.get("Gravações", "false").astype(str).str.lower()
    else:
        # Formato alternativo (Call Report com separador tab, duração textual)
        col_resultado = (
            df_bruto.get("Resultado da chamada")
            or df_bruto.get("Resultado")
            or _find_column_by_sample(
                df_bruto,
                ["Chamada perdida", "Encerrada com sucesso", "Chamada do plano de discagem encerrada"],
            )
        )
        col_data = (
            df_bruto.get("Data [America/Sao_Paulo]")
            or df_bruto.get("Start Time (local)")
            or _find_first_datetime_column(df_bruto)
        )
        col_de = df_bruto.get("De") or _find_column_with_phone_like(df_bruto)

        if col_data is None or col_resultado is None:
            raise ValueError(
                "Arquivo GoTo não reconhecido: faltam colunas de data e/ou resultado.\n"
                "Esperado: 'Data [America/Sao_Paulo]' + 'Resultado da chamada', ou variantes compatíveis."
            )

        datas = pd.to_datetime(col_data, format="mixed", errors="coerce")
        if hasattr(datas.dt, "tz") and datas.dt.tz is not None:
            datas = datas.dt.tz_localize(None)
        df["data_chamada"] = datas
        df["resultado"] = col_resultado.astype(str).apply(padronizar_texto)

        id_col = df_bruto.get("Conversation space id") or df_bruto.get("Call ID")
        df["id_conversa"] = (
            id_col.astype(str).str.strip().replace("nan", "")
            if id_col is not None
            else pd.Series("", index=df_bruto.index)
        )

        col_dur_ms = df_bruto.get("Duração [milissegundos]") or df_bruto.get("Duration (ms)")
        col_dur_str = (
            df_bruto.get("Duração")
            if "Duração" in df_bruto.columns
            else _find_column_by_sample(df_bruto, ["29s", "05m 32s", "0s"])
        )
        if col_dur_ms is not None:
            df["duracao_ms"] = pd.to_numeric(col_dur_ms, errors="coerce").astype("Int64")
        elif col_dur_str is not None:
            df["duracao_ms"] = col_dur_str.apply(lambda x: int(_parse_duracao_goto(x)))
        else:
            df["duracao_ms"] = 0

        col_direcao = df_bruto.get("Direção") or df_bruto.get("Direction")
        df["direcao"] = (
            col_direcao if col_direcao is not None else pd.Series("", index=df_bruto.index)
        ).apply(padronizar_texto)

        telefone_raw = (
            col_de if col_de is not None else pd.Series("", index=df_bruto.index)
        ).apply(extrair_apenas_numeros)

        df["participantes"] = (
            df_bruto.get("Participantes", pd.Series("", index=df_bruto.index))
            .astype(str)
            .replace("nan", "")
        )
        df["gravado"] = "false"

    df["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
    df["telefone_origem"] = telefone_raw.astype(str).str.strip().replace("nan", "").fillna("")
    df["data_importacao"] = datetime.now()

    def _resolver_id(row):
        id_orig = str(row.get("id_conversa", "")).strip()
        if id_orig and id_orig != "nan":
            return id_orig
        assinatura = f"{row['data_chamada']}_{row['telefone_hash']}_{row.get('duracao_ms', 0)}"
        return f"SINTETICO_{hashlib.md5(assinatura.encode(), usedforsecurity=False).hexdigest()}"

    df["id_conversa"] = df.apply(_resolver_id, axis=1)
    return df


# ---------------------------------------------------------------------------
# Processamento GoTo Agent Calls
# ---------------------------------------------------------------------------


def processar_agent_calls_goto(arquivo) -> pd.DataFrame:
    """
    Processa CSV do relatório GoTo 'Agent Calls'
    (agent-calls_YYYYMMDD_YYYYMMDD.csv).

    Retorna DataFrame com colunas:
        contact_id, queue_name, contact_creation_time, contact_resolution_time,
        time_in_queue_millis, talk_time_millis, wrap_time_millis, handle_time_millis,
        contact_resolution, contact_type, contact_participant_value,
        agent_name, telefone_hash, telefone_origem, data_importacao
    """
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    try:
        df_bruto = pd.read_csv(arquivo, encoding="utf-8", sep=",", quotechar='"')
    except Exception:
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        df_bruto = ler_arquivo_dinamico(arquivo)

    cols = {str(c).strip() for c in df_bruto.columns}
    if not {"Contact ID", "Contact Resolution", "Agent Name"}.issubset(cols):
        raise ValueError(
            "Arquivo não reconhecido como GoTo Agent Calls.\n"
            "Esperado: colunas 'Contact ID', 'Contact Resolution', 'Agent Name'."
        )

    df = pd.DataFrame()
    df["contact_id"] = df_bruto["Contact ID"].astype(str).str.strip()
    df["queue_name"] = df_bruto.get("Queue Name", "").astype(str).str.strip().replace("nan", "")
    df["contact_creation_time"] = pd.to_datetime(
        df_bruto["Contact Creation Time"], format="mixed", errors="coerce"
    )
    df["contact_resolution_time"] = pd.to_datetime(
        df_bruto.get("Contact Resolution Time"), format="mixed", errors="coerce"
    )
    for col_ms in ("time_in_queue_millis", "talk_time_millis", "wrap_time_millis", "handle_time_millis"):
        col_src = col_ms.replace("_", " ").title().replace("Millis", "(millis)")
        df[col_ms] = pd.to_numeric(df_bruto.get(col_src), errors="coerce").astype("Int64")

    df["contact_resolution"] = df_bruto.get("Contact Resolution", "").astype(str).str.strip().replace("nan", "")
    df["contact_type"] = df_bruto.get("Contact Type", "").astype(str).str.strip().replace("nan", "")

    participant = df_bruto.get("Contact Participant Value", pd.Series(dtype=str)).astype(str).str.strip()
    telefone_raw = participant.apply(extrair_apenas_numeros)
    df["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
    df["telefone_origem"] = participant.replace("nan", "")
    df["contact_participant_value"] = participant
    df["agent_name"] = df_bruto.get("Agent Name", "").astype(str).str.strip().replace("nan", "")
    df["data_importacao"] = datetime.now()

    for col_ts in ("contact_creation_time", "contact_resolution_time"):
        try:
            if df[col_ts].dt.tz is not None:
                df[col_ts] = df[col_ts].dt.tz_localize(None)
        except Exception:
            pass

    return df


# ---------------------------------------------------------------------------
# Processamento Multi360
# ---------------------------------------------------------------------------


def processar_csv_multi360(arquivo) -> pd.DataFrame:
    """
    Processa CSV de atendimentos Multi360 (WhatsApp/Chat).

    Retorna DataFrame com colunas:
        protocolo, origem, status, atendente, departamento,
        nome_contato (anonimizado), telefone_hash, numero_telefone (mascarado),
        data_inicio, data_finalizacao, data_ultima_mensagem, avaliacao, data_importacao
    """
    df_bruto = ler_arquivo_dinamico(arquivo)
    df = pd.DataFrame()

    if "PROTOCOLO" in df_bruto.columns:
        df["protocolo"] = pd.to_numeric(df_bruto["PROTOCOLO"], errors="coerce").astype("Int64")
    if "ORIGEM" in df_bruto.columns:
        df["origem"] = df_bruto["ORIGEM"].apply(padronizar_texto)
    if "STATUS" in df_bruto.columns:
        df["status"] = df_bruto["STATUS"].apply(padronizar_texto)
    if "ATENDENTE" in df_bruto.columns:
        df["atendente"] = df_bruto["ATENDENTE"].astype(str).str.strip().replace("nan", "")
    if "DEPARTAMENTO" in df_bruto.columns:
        df["departamento"] = df_bruto["DEPARTAMENTO"].astype(str).str.strip().replace("nan", "")
    if "NOME" in df_bruto.columns:
        df["nome_contato"] = df_bruto["NOME"].apply(lambda x: mascarar_dado_lgpd(x, "nome"))
    if "NUMERO" in df_bruto.columns:
        num_raw = df_bruto["NUMERO"].apply(extrair_apenas_numeros)
        df["telefone_hash"] = num_raw.apply(gerar_hash_lgpd)
        df["numero_telefone"] = num_raw.apply(lambda x: mascarar_dado_lgpd(x, "telefone"))
    if "DATA" in df_bruto.columns:
        df["data_inicio"] = pd.to_datetime(df_bruto["DATA"], format="%d/%m/%Y %H:%M", errors="coerce")
    if "DATAFINALIZACAO" in df_bruto.columns:
        df["data_finalizacao"] = pd.to_datetime(
            df_bruto["DATAFINALIZACAO"], format="%d/%m/%Y %H:%M", errors="coerce"
        )
    if "DATAULTIMAMENSAGEM" in df_bruto.columns:
        df["data_ultima_mensagem"] = pd.to_datetime(
            df_bruto["DATAULTIMAMENSAGEM"], format="%d/%m/%Y %H:%M", errors="coerce"
        )
    if "AVALIACAO" in df_bruto.columns:
        df["avaliacao"] = pd.to_numeric(df_bruto["AVALIACAO"], errors="coerce").astype("Int64")

    df["data_importacao"] = datetime.now()
    return df


# ---------------------------------------------------------------------------
# Utilitário ZIP (Agent Calls dentro de .zip)
# ---------------------------------------------------------------------------


def extrair_agent_calls_do_zip(zip_bytes: io.BytesIO):
    """
    Abre um .zip e retorna (BytesIO do CSV agent-calls, nome_arquivo).
    Retorna (None, None) se não encontrar o arquivo.
    """
    with zipfile.ZipFile(zip_bytes, "r") as z:
        for name in z.namelist():
            if "agent-calls" in name.lower() and name.lower().endswith(".csv"):
                return io.BytesIO(z.read(name)), name
    return None, None


# ---------------------------------------------------------------------------
# Roteador principal: detecta e processa qualquer arquivo suportado
# ---------------------------------------------------------------------------


def processar_arquivo(caminho: str | Path) -> tuple[pd.DataFrame, str]:
    """
    Detecta o tipo do arquivo e aplica o processador correto.

    Retorna:
        (DataFrame processado, tipo detectado)

    Lança ValueError para arquivos não reconhecidos.
    """
    caminho = Path(caminho)

    # ZIP com Agent Calls
    if caminho.suffix.lower() == ".zip":
        with open(caminho, "rb") as f:
            csv_bytes, nome = extrair_agent_calls_do_zip(io.BytesIO(f.read()))
        if csv_bytes is None:
            raise ValueError(f"ZIP '{caminho.name}' não contém arquivo 'agent-calls*.csv'.")
        df = processar_agent_calls_goto(csv_bytes)
        return df, _TIPO_GOTO_AGENT_CALLS

    df_bruto = ler_arquivo_dinamico(caminho)
    tipo = detectar_tipo(df_bruto)

    if tipo == _TIPO_GOTO_AGENT_CALLS:
        return processar_agent_calls_goto(caminho), tipo
    if tipo == _TIPO_GOTO:
        return processar_csv_goto(caminho), tipo
    if tipo == _TIPO_MULTI360:
        return processar_csv_multi360(caminho), tipo

    raise ValueError(
        f"Arquivo '{caminho.name}' não reconhecido como GoTo (Conversations/Call Report/Agent Calls) "
        "ou Multi360. Verifique as colunas do arquivo."
    )


# ---------------------------------------------------------------------------
# Geração de relatório de resultados
# ---------------------------------------------------------------------------


def gerar_relatorio_goto(df: pd.DataFrame, nome_arquivo: str) -> str:
    """Gera resumo textual do DataFrame GoTo Conversations / Call Report."""
    linhas = [
        f"\n{'=' * 60}",
        f"  Relatório GoTo – {nome_arquivo}",
        f"{'=' * 60}",
        f"  Total de registros    : {len(df):,}",
    ]

    if "data_chamada" in df.columns:
        data_min = df["data_chamada"].min()
        data_max = df["data_chamada"].max()
        linhas.append(f"  Período               : {data_min} → {data_max}")

    if "resultado" in df.columns:
        contagem = df["resultado"].value_counts()
        linhas.append("\n  Resultados das chamadas:")
        for resultado, qtd in contagem.items():
            pct = qtd / len(df) * 100
            linhas.append(f"    {resultado:<50} {qtd:>6,}  ({pct:.1f}%)")

    if "direcao" in df.columns:
        contagem_dir = df["direcao"].value_counts()
        linhas.append("\n  Direção:")
        for dir_, qtd in contagem_dir.items():
            linhas.append(f"    {dir_:<20} {qtd:>6,}")

    if "duracao_ms" in df.columns:
        dur_valida = df["duracao_ms"].dropna()
        if len(dur_valida) > 0:
            media_s = dur_valida.mean() / 1000
            max_s = dur_valida.max() / 1000
            linhas.append(
                f"\n  Duração média         : {media_s:.1f}s   |   Máxima: {max_s:.1f}s"
            )

    linhas.append(f"{'=' * 60}\n")
    return "\n".join(linhas)


def gerar_relatorio_agent_calls(df: pd.DataFrame, nome_arquivo: str) -> str:
    """Gera resumo textual do DataFrame GoTo Agent Calls."""
    linhas = [
        f"\n{'=' * 60}",
        f"  Relatório GoTo Agent Calls – {nome_arquivo}",
        f"{'=' * 60}",
        f"  Total de contatos     : {len(df):,}",
    ]

    if "contact_creation_time" in df.columns:
        data_min = df["contact_creation_time"].min()
        data_max = df["contact_creation_time"].max()
        linhas.append(f"  Período               : {data_min} → {data_max}")

    if "agent_name" in df.columns:
        top_agentes = df["agent_name"].value_counts().head(10)
        linhas.append("\n  Top 10 agentes (por atendimentos):")
        for agente, qtd in top_agentes.items():
            linhas.append(f"    {agente:<40} {qtd:>6,}")

    if "queue_name" in df.columns:
        filas = df["queue_name"].value_counts()
        linhas.append("\n  Filas:")
        for fila, qtd in filas.items():
            linhas.append(f"    {fila:<40} {qtd:>6,}")

    for col_ms, label in (
        ("talk_time_millis", "Tempo de fala"),
        ("handle_time_millis", "Tempo de tratamento"),
        ("time_in_queue_millis", "Tempo em fila"),
    ):
        if col_ms in df.columns:
            vals = df[col_ms].dropna()
            if len(vals) > 0:
                linhas.append(
                    f"  {label:<25}: média {vals.mean() / 1000:.1f}s  |  máx {vals.max() / 1000:.1f}s"
                )

    linhas.append(f"{'=' * 60}\n")
    return "\n".join(linhas)


def gerar_relatorio_multi360(df: pd.DataFrame, nome_arquivo: str) -> str:
    """Gera resumo textual do DataFrame Multi360."""
    linhas = [
        f"\n{'=' * 60}",
        f"  Relatório Multi360 – {nome_arquivo}",
        f"{'=' * 60}",
        f"  Total de registros    : {len(df):,}",
    ]

    if "data_inicio" in df.columns:
        data_min = df["data_inicio"].min()
        data_max = df["data_inicio"].max()
        linhas.append(f"  Período               : {data_min} → {data_max}")

    if "status" in df.columns:
        contagem_status = df["status"].value_counts()
        linhas.append("\n  Status dos atendimentos:")
        for status, qtd in contagem_status.items():
            pct = qtd / len(df) * 100
            linhas.append(f"    {status:<30} {qtd:>6,}  ({pct:.1f}%)")

    if "origem" in df.columns:
        contagem_origem = df["origem"].value_counts()
        linhas.append("\n  Origens:")
        for origem, qtd in contagem_origem.items():
            linhas.append(f"    {origem:<30} {qtd:>6,}")

    if "atendente" in df.columns:
        top_atendentes = df["atendente"].value_counts().head(10)
        linhas.append("\n  Top 10 atendentes:")
        for atendente, qtd in top_atendentes.items():
            linhas.append(f"    {atendente:<40} {qtd:>6,}")

    if "avaliacao" in df.columns:
        avals = df["avaliacao"].dropna()
        if len(avals) > 0:
            linhas.append(f"\n  Avaliação média       : {avals.mean():.2f}  (de {len(avals):,} respostas)")

    linhas.append(f"{'=' * 60}\n")
    return "\n".join(linhas)


def gerar_relatorio(df: pd.DataFrame, tipo: str, nome_arquivo: str) -> str:
    """Seleciona o gerador de relatório correto conforme o tipo."""
    if tipo == _TIPO_GOTO_AGENT_CALLS:
        return gerar_relatorio_agent_calls(df, nome_arquivo)
    if tipo == _TIPO_GOTO:
        return gerar_relatorio_goto(df, nome_arquivo)
    if tipo == _TIPO_MULTI360:
        return gerar_relatorio_multi360(df, nome_arquivo)
    return f"\n[AVISO] Tipo '{tipo}' sem relatório definido.\n"


# ---------------------------------------------------------------------------
# Exportação de resultado (opcional)
# ---------------------------------------------------------------------------


def exportar_resultado(df: pd.DataFrame, caminho_saida: str | Path) -> None:
    """Salva o DataFrame processado em CSV (sem índice)."""
    caminho_saida = Path(caminho_saida)
    df.to_csv(caminho_saida, index=False, encoding="utf-8-sig")
    print(f"  ✅ Resultado exportado → {caminho_saida}")


# ---------------------------------------------------------------------------
# Descoberta de arquivos em diretório
# ---------------------------------------------------------------------------

EXTENSOES_SUPORTADAS = {".csv", ".xlsx", ".zip"}


def listar_arquivos(caminho: str | Path) -> list[Path]:
    """
    Retorna lista de arquivos suportados.
    Se caminho for diretório, varre recursivamente.
    Se for arquivo, retorna lista com esse arquivo.
    """
    caminho = Path(caminho)
    if caminho.is_file():
        return [caminho] if caminho.suffix.lower() in EXTENSOES_SUPORTADAS else []
    if caminho.is_dir():
        return sorted(
            p
            for p in caminho.rglob("*")
            if p.is_file() and p.suffix.lower() in EXTENSOES_SUPORTADAS
        )
    return []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Processador standalone de CSVs do WikiSuporte.\n"
            "Suporta: GoTo Conversations, GoTo Call Report, GoTo Agent Calls (.zip), Multi360."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "entradas",
        nargs="*",
        metavar="ARQUIVO_OU_PASTA",
        help="Arquivo(s) CSV/XLSX/ZIP ou pasta(s). Sem argumentos: varre o diretório atual.",
    )
    parser.add_argument(
        "--exportar",
        action="store_true",
        help="Salva cada resultado como CSV processado (mesmo nome com sufixo _processado.csv).",
    )
    parser.add_argument(
        "--saida",
        metavar="PASTA",
        default=None,
        help="Pasta de destino para os CSVs exportados (padrão: mesma pasta do arquivo de entrada).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    entradas = args.entradas if args.entradas else ["."]
    arquivos: list[Path] = []
    for entrada in entradas:
        encontrados = listar_arquivos(entrada)
        if not encontrados:
            print(f"[AVISO] Nenhum arquivo suportado encontrado em: {entrada}", file=sys.stderr)
        arquivos.extend(encontrados)

    if not arquivos:
        print("Nenhum arquivo CSV/XLSX/ZIP encontrado para processar.", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 {len(arquivos)} arquivo(s) encontrado(s) para processar.\n")

    total_ok = 0
    total_erro = 0

    for arquivo in arquivos:
        print(f"📂 Processando: {arquivo}")
        try:
            df, tipo = processar_arquivo(arquivo)
            print(f"   Tipo detectado: {tipo}  |  Registros: {len(df):,}")
            print(gerar_relatorio(df, tipo, arquivo.name))

            if args.exportar:
                pasta_saida = Path(args.saida) if args.saida else arquivo.parent
                pasta_saida.mkdir(parents=True, exist_ok=True)
                nome_saida = pasta_saida / (arquivo.stem + "_processado.csv")
                exportar_resultado(df, nome_saida)

            total_ok += 1

        except ValueError as e:
            print(f"   ❌ Erro de validação: {e}\n", file=sys.stderr)
            total_erro += 1
        except Exception as e:
            print(f"   ❌ Erro inesperado: {e}\n", file=sys.stderr)
            total_erro += 1

    print(f"\n{'─' * 60}")
    print(f"  Concluído: {total_ok} arquivo(s) processado(s), {total_erro} erro(s).")
    print(f"{'─' * 60}\n")

    if total_erro > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
