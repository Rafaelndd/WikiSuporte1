import pandas as pd
import re
from datetime import datetime
import io
import hashlib
import os

# ==========================================
# CONFIGURAÇÕES DE SEGURANÇA (LGPD)
# ==========================================

# A chave secreta (SALT) para o embaralhamento. 
SALT = os.getenv("APP_SALT_KEY", "chave_secreta_wiki_suporte_2026")

def gerar_hash_lgpd(texto: str) -> str:
    """Gera um Hash irreversível (SHA-256) do dado sensível."""
    if not texto or pd.isna(texto) or texto == "":
        return ""
    dado_com_salt = f"{texto}{SALT}".encode('utf-8')
    return hashlib.sha256(dado_com_salt).hexdigest()

def mascarar_dado_lgpd(texto: str, tipo: str = "telefone") -> str:
    """Mascara os dados para que fiquem seguros na base de dados e no Dashboard."""
    if not texto or pd.isna(texto) or texto == "":
        return ""
    
    texto_str = str(texto)
    if tipo == "telefone":
        # Retorna: (**) *****-1234
        return f"(**) *****-{texto_str[-4:]}" if len(texto_str) >= 4 else "****"
    elif tipo == "nome":
        # Substitui o nome real do cliente
        return "CLIENTE_CONFIDENCIAL"
    return "****"

# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA
# ==========================================

def extrair_apenas_numeros(texto) -> str:
    """Remove letras e caracteres especiais, mantendo apenas dígitos."""
    if pd.isna(texto):
        return ""
    return re.sub(r'\D', '', str(texto))

def padronizar_texto(texto) -> str:
    """Remove espaços duplos, espaços nas extremidades e padroniza para Maiúsculas."""
    if pd.isna(texto):
        return ""
    return re.sub(r'\s+', ' ', str(texto)).strip().upper()


# ==========================================
# FUNÇÃO PRINCIPAL DE LEITURA DE ARQUIVO
# ==========================================

def ler_arquivo_dinamico(arquivo) -> pd.DataFrame:
    """
    Identifica a extensão do arquivo enviado pelo Streamlit 
    e utiliza o motor correto do Pandas (read_csv ou read_excel).
    """
    # O Streamlit UploadedFile possui o atributo .name
    nome_arquivo = arquivo.name.lower()
    
    if nome_arquivo.endswith('.xlsx'):
        # Requer a biblioteca 'openpyxl' instalada
        return pd.read_excel(arquivo)
    else:
        # Padrão CSV com a nossa "mágica do Excel" (separador dinâmico)
        return pd.read_csv(arquivo, sep=None, engine='python')

# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_goto
# ==========================================

# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_goto
# ==========================================

def _parse_duracao_goto(val) -> float:
    """Converte duração no formato GoTo ('29s', '05m 32s', '19m 04s') para milissegundos."""
    if pd.isna(val) or val == "" or val == "0s":
        return 0.0
    s = str(val).strip().lower()
    total_ms = 0.0
    for part in re.findall(r"(\d+)\s*(h|m|s|min|sec)", s):
        n = int(part[0])
        u = part[1]
        if u in ("h",):
            total_ms += n * 3600 * 1000
        elif u in ("m", "min"):
            total_ms += n * 60 * 1000
        else:
            total_ms += n * 1000
    return total_ms


def processar_csv_goto(arquivo: io.BytesIO) -> pd.DataFrame:
    """
    Processa CSV de atendimentos GoTo (Conversations ou Call Report).
    Classificação no Dashboard: Atendida = 'Encerrada com sucesso' ou 'Chamada do plano de discagem encerrada';
    Perdida = 'Chamada perdida'; Abandonada na URA = apenas quando não houver 'encerrada' no resultado.
    """
    try:
        df_bruto = ler_arquivo_dinamico(arquivo)
        df_limpo = pd.DataFrame()

        # Formato padrão (Conversations): colunas exatas do export GoTo em português
        if "Data [America/Sao_Paulo]" in df_bruto.columns and "Resultado da chamada" in df_bruto.columns:
            data_col = df_bruto["Data [America/Sao_Paulo]"]
            try:
                datas_convertidas = pd.to_datetime(data_col, format="ISO8601", errors="coerce")
            except Exception:
                datas_convertidas = pd.to_datetime(data_col, format="mixed", errors="coerce")
            if datas_convertidas.dt.tz is not None:
                datas_convertidas = datas_convertidas.dt.tz_localize(None)
            df_limpo["data_chamada"] = datas_convertidas
            df_limpo["id_conversa"] = df_bruto.get("Conversation space id", "").astype(str).str.strip().replace("nan", "")
            df_limpo["duracao_ms"] = pd.to_numeric(df_bruto.get("Duração [milissegundos]"), errors="coerce").astype("Int64")
            df_limpo["direcao"] = df_bruto.get("Direção", pd.Series(dtype=str)).apply(padronizar_texto)
            df_limpo["resultado"] = df_bruto["Resultado da chamada"].astype(str).apply(padronizar_texto)
            telefone_raw = df_bruto.get("De", pd.Series(dtype=str)).apply(extrair_apenas_numeros)
            df_limpo["participantes"] = df_bruto.get("Participantes", "").astype(str).replace("nan", "")
            df_limpo["gravado"] = df_bruto.get("Gravações", "false").astype(str).str.lower()
        else:
            # Formato alternativo (Call Report com tab, datas ISO, duração "29s"/"05m 32s")
            col_resultado = df_bruto.get("Resultado da chamada") or df_bruto.get("Resultado") or _find_column_by_sample(
                df_bruto, ["Chamada perdida", "Encerrada com sucesso", "Chamada do plano de discagem encerrada"]
            )
            col_data = df_bruto.get("Data [America/Sao_Paulo]") or df_bruto.get("Start Time (local)") or _find_first_datetime_column(df_bruto)
            col_de = df_bruto.get("De") or _find_column_with_phone_like(df_bruto)
            if col_data is None or col_resultado is None:
                raise ValueError(
                    "Arquivo GoTo não reconhecido: faltam colunas de data e/ou resultado. "
                    "Esperado: 'Data [America/Sao_Paulo]' e 'Resultado da chamada', ou colunas com 'Chamada perdida' / 'Encerrada com sucesso'."
                )
            datas_convertidas = pd.to_datetime(col_data, format="mixed", errors="coerce")
            if hasattr(datas_convertidas.dt, "tz") and datas_convertidas.dt.tz is not None:
                datas_convertidas = datas_convertidas.dt.tz_localize(None)
            df_limpo["data_chamada"] = datas_convertidas
            df_limpo["resultado"] = col_resultado.astype(str).apply(padronizar_texto)
            id_col = df_bruto.get("Conversation space id") or df_bruto.get("Call ID")
            df_limpo["id_conversa"] = id_col.astype(str).str.strip().replace("nan", "") if id_col is not None else pd.Series("", index=df_bruto.index)
            col_duracao = df_bruto.get("Duração [milissegundos]") or df_bruto.get("Duration (ms)")
            col_duracao_str = df_bruto.get("Duração") if "Duração" in df_bruto.columns else _find_column_by_sample(df_bruto, ["29s", "05m 32s", "0s"])
            if col_duracao is not None:
                df_limpo["duracao_ms"] = pd.to_numeric(col_duracao, errors="coerce").astype("Int64")
            elif col_duracao_str is not None:
                df_limpo["duracao_ms"] = col_duracao_str.apply(lambda x: int(_parse_duracao_goto(x)))
            else:
                df_limpo["duracao_ms"] = 0
            col_direcao = df_bruto.get("Direção") or df_bruto.get("Direction")
            df_limpo["direcao"] = (col_direcao if col_direcao is not None else pd.Series("", index=df_bruto.index)).apply(padronizar_texto)
            telefone_raw = (col_de if col_de is not None else pd.Series("", index=df_bruto.index)).apply(extrair_apenas_numeros)
            df_limpo["participantes"] = df_bruto.get("Participantes", pd.Series("", index=df_bruto.index)).astype(str).replace("nan", "")
            df_limpo["gravado"] = "false"

        df_limpo["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
        df_limpo["telefone_origem"] = telefone_raw.astype(str).str.strip().replace("nan", "").fillna("")
        df_limpo["data_importacao"] = datetime.now()

        def resolver_id_faltante(row):
            id_original = str(row.get("id_conversa", "")).strip()
            if id_original and id_original != "nan":
                return id_original
            assinatura_evento = f"{row['data_chamada']}_{row['telefone_hash']}_{row.get('duracao_ms', 0)}"
            return f"SINTETICO_{hashlib.md5(assinatura_evento.encode('utf-8'), usedforsecurity=False).hexdigest()}"

        df_limpo["id_conversa"] = df_limpo.apply(resolver_id_faltante, axis=1)
        return df_limpo

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Erro no processamento GoTo: {e}") from e


def _find_column_by_sample(df: pd.DataFrame, amostras: list):
    """Retorna a coluna que contém pelo menos um dos valores em amostras (case-insensitive)."""
    for col in df.columns:
        s = df[col].astype(str).str.strip().str.lower()
        for a in amostras:
            if (s == a.lower()).any():
                return df[col]
    return None


def _find_first_datetime_column(df: pd.DataFrame):
    """Retorna a primeira coluna que pareça ser datetime (valores ISO ou datelike)."""
    for col in df.columns:
        try:
            sample = df[col].dropna().astype(str).iloc[0] if len(df) else ""
            if "T" in sample and ("Z" in sample or "-" in sample[-6:] or "+" in sample):
                return df[col]
        except Exception:
            continue
    return None


def _find_column_with_phone_like(df: pd.DataFrame):
    """Retorna coluna que tenha valores parecidos com telefone (+55, números longos)."""
    for col in df.columns:
        try:
            s = df[col].astype(str).str.replace(r"\D", "", regex=True)
            if s.str.len().ge(10).any():
                return df[col]
        except Exception:
            continue
    return None


# ==========================================
# PROCESSAMENTO: GoTo Agent Calls (relatório agent-calls_*.csv)
# ==========================================

def _is_agent_calls_csv(df: pd.DataFrame) -> bool:
    """Detecta se o DataFrame é do relatório Agent Calls do GoTo (colunas em inglês)."""
    cols = [str(c).strip() for c in df.columns]
    return "Contact ID" in cols and "Contact Resolution" in cols and "Agent Name" in cols


def processar_agent_calls_goto(arquivo: io.BytesIO) -> pd.DataFrame:
    """
    Processa CSV do relatório GoTo 'Agent Calls' (agent-calls_YYYYMMDD_YYYYMMDD.csv).
    Cada linha é uma chamada atendida (Contact Resolution = COMPLETED).
    Retorna DataFrame no formato da tabela goto_agent_calls.
    """
    if hasattr(arquivo, "seek"):
        arquivo.seek(0)
    try:
        df_bruto = pd.read_csv(arquivo, encoding="utf-8", sep=",", quotechar='"')
    except Exception:
        arquivo.seek(0) if hasattr(arquivo, "seek") else None
        df_bruto = ler_arquivo_dinamico(arquivo)
    if not _is_agent_calls_csv(df_bruto):
        raise ValueError("Arquivo não é um relatório GoTo Agent Calls. Esperado: colunas 'Contact ID', 'Contact Resolution', 'Agent Name'.")
    df = pd.DataFrame()
    df["contact_id"] = df_bruto["Contact ID"].astype(str).str.strip()
    df["queue_name"] = df_bruto.get("Queue Name", "").astype(str).str.strip().replace("nan", "")
    df["contact_creation_time"] = pd.to_datetime(df_bruto["Contact Creation Time"], format="mixed", errors="coerce")
    df["contact_resolution_time"] = pd.to_datetime(df_bruto.get("Contact Resolution Time"), format="mixed", errors="coerce")
    df["time_in_queue_millis"] = pd.to_numeric(df_bruto.get("Time in Queue (millis)"), errors="coerce").astype("Int64")
    df["talk_time_millis"] = pd.to_numeric(df_bruto.get("Talk Time (millis)"), errors="coerce").astype("Int64")
    df["wrap_time_millis"] = pd.to_numeric(df_bruto.get("Wrap Time (millis)"), errors="coerce").astype("Int64")
    df["handle_time_millis"] = pd.to_numeric(df_bruto.get("Handle Time (millis)"), errors="coerce").astype("Int64")
    df["contact_resolution"] = df_bruto.get("Contact Resolution", "").astype(str).str.strip().replace("nan", "")
    df["contact_type"] = df_bruto.get("Contact Type", "").astype(str).str.strip().replace("nan", "")
    participant_val = df_bruto.get("Contact Participant Value", pd.Series(dtype=str)).astype(str).str.strip()
    telefone_raw = participant_val.apply(extrair_apenas_numeros)
    df["telefone_hash"] = telefone_raw.apply(gerar_hash_lgpd)
    df["telefone_origem"] = participant_val.astype(str).str.strip().replace("nan", "")
    df["contact_participant_value"] = participant_val
    df["agent_name"] = df_bruto.get("Agent Name", "").astype(str).str.strip().replace("nan", "")
    df["data_importacao"] = datetime.now()
    if df["contact_creation_time"].dt.tz is not None:
        df["contact_creation_time"] = df["contact_creation_time"].dt.tz_localize(None)
    try:
        if df["contact_resolution_time"].dt.tz is not None:
            df["contact_resolution_time"] = df["contact_resolution_time"].dt.tz_localize(None)
    except Exception:
        pass
    return df


def extrair_agent_calls_do_zip(zip_bytes: io.BytesIO):
    """
    Abre o zip e retorna (BytesIO do CSV agent-calls, nome_arquivo) ou (None, None) se não achar.
    """
    import zipfile
    with zipfile.ZipFile(zip_bytes, "r") as z:
        for name in z.namelist():
            if "agent-calls" in name.lower() and name.lower().endswith(".csv"):
                return io.BytesIO(z.read(name)), name
    return None, None


# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_multi360
# ==========================================

def processar_csv_multi360(arquivo: io.BytesIO) -> pd.DataFrame:
    try:
        df_bruto = ler_arquivo_dinamico(arquivo)
        df_limpo = pd.DataFrame()

        if 'PROTOCOLO' in df_bruto.columns:
            df_limpo['protocolo'] = pd.to_numeric(df_bruto['PROTOCOLO'], errors='coerce').astype('Int64')
            
        if 'ORIGEM' in df_bruto.columns:
            df_limpo['origem'] = df_bruto['ORIGEM'].apply(padronizar_texto)
            
        if 'STATUS' in df_bruto.columns:
            df_limpo['status'] = df_bruto['STATUS'].apply(padronizar_texto)
            
        if 'ATENDENTE' in df_bruto.columns:
            df_limpo['atendente'] = df_bruto['ATENDENTE'].astype(str).str.strip().replace('nan', '')
            
        if 'DEPARTAMENTO' in df_bruto.columns:
            df_limpo['departamento'] = df_bruto['DEPARTAMENTO'].astype(str).str.strip().replace('nan', '')
            
        # LGPD: Anonimização de Nomes
        if 'NOME' in df_bruto.columns:
            df_limpo['nome_contato'] = df_bruto['NOME'].apply(lambda x: mascarar_dado_lgpd(x, "nome"))
            
        # LGPD: Hashing e Mascaramento de Telefones do WhatsApp
        if 'NUMERO' in df_bruto.columns:
            num_raw = df_bruto['NUMERO'].apply(extrair_apenas_numeros)
            df_limpo['telefone_hash'] = num_raw.apply(gerar_hash_lgpd)
            df_limpo['numero_telefone'] = num_raw.apply(lambda x: mascarar_dado_lgpd(x, "telefone"))
            
        if 'DATA' in df_bruto.columns:
            df_limpo['data_inicio'] = pd.to_datetime(df_bruto['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'DATAFINALIZACAO' in df_bruto.columns:
            df_limpo['data_finalizacao'] = pd.to_datetime(df_bruto['DATAFINALIZACAO'], format='%d/%m/%Y %H:%M', errors='coerce')
        
        # --- BLOCO DE DATAS NO SEU processador_csv.py ---
        if 'DATA' in df_bruto.columns:
            df_limpo['data_inicio'] = pd.to_datetime(df_bruto['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'DATAFINALIZACAO' in df_bruto.columns:
            df_limpo['data_finalizacao'] = pd.to_datetime(df_bruto['DATAFINALIZACAO'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        
        if 'DATAULTIMAMENSAGEM' in df_bruto.columns:
            # Tenta converter a data da última mensagem
            df_limpo['data_ultima_mensagem'] = pd.to_datetime(df_bruto['DATAULTIMAMENSAGEM'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'AVALIACAO' in df_bruto.columns:
            df_limpo['avaliacao'] = pd.to_numeric(df_bruto['AVALIACAO'], errors='coerce').astype('Int64')
            
        df_limpo['data_importacao'] = datetime.now()

        return df_limpo
    except Exception as e:
        raise ValueError(f"Falha estrutural ao processar o CSV do Multi360. Detalhes: {e}")