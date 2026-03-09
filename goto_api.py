"""
Módulo de Integração com a API do GoTo Connect.

Este módulo fornece todas as funcionalidades necessárias para autenticação
OAuth2 e busca de relatórios de chamadas diretamente da API do GoTo Connect,
eliminando a necessidade de exportar arquivos manualmente.

Plano Principal : Autenticação automática e busca de chamadas via API.
Plano B (Fallback): Caso a API esteja indisponível ou instável, o sistema
continua funcionando normalmente pelo upload manual de arquivos CSV/XLSX na
aba 'Importar Mensal / Relatórios' da página de Importação de Dados.

Referência da API:
    - Autenticação: https://authentication.logmeininc.com/oauth/token
    - Identidade:   https://api.goto.com/identity/v1/Users/me
    - Chamadas:     https://api.goto.com/call-reports/v1/accounts/{accountKey}/calls
"""

import os
import re
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URLs da API do GoTo Connect
# ---------------------------------------------------------------------------
GOTO_TOKEN_URL = "https://authentication.logmeininc.com/oauth/token"
GOTO_IDENTITY_URL = "https://api.goto.com/identity/v1/Users/me"
GOTO_CALLS_URL = "https://api.goto.com/call-reports/v1/accounts/{account_key}/calls"

# Quantidade máxima de registros por página (limite da API do GoTo)
GOTO_PAGE_SIZE = 1000

# Tempo máximo de espera por resposta da API (segundos)
GOTO_REQUEST_TIMEOUT = 30

# Chave de SALT para hashing LGPD – mesma usada no processador_csv.py
# APP_SALT_KEY deve estar definida no .env; o valor padrão é usado apenas como
# fallback de compatibilidade (idêntico ao comportamento do processador_csv.py).
SALT = os.getenv("APP_SALT_KEY", "chave_secreta_wiki_suporte_2026")
if not os.getenv("APP_SALT_KEY"):
    logger.warning(
        "APP_SALT_KEY não definida no .env. "
        "Defina esta variável para garantir a segurança dos dados LGPD."
    )


# ---------------------------------------------------------------------------
# Funções auxiliares de LGPD (replicadas aqui para manter o módulo autônomo)
# ---------------------------------------------------------------------------

def _gerar_hash_lgpd(texto: str) -> str:
    """Gera um hash SHA-256 irreversível do dado sensível."""
    if not texto or texto.strip() == "":
        return ""
    dado_com_salt = f"{texto}{SALT}".encode("utf-8")
    return hashlib.sha256(dado_com_salt).hexdigest()


def _mascarar_telefone(texto: str) -> str:
    """Mascara o telefone exibindo apenas os 4 últimos dígitos."""
    texto_str = str(texto).strip()
    if not texto_str:
        return ""
    return f"(**) *****-{texto_str[-4:]}" if len(texto_str) >= 4 else "****"


def _extrair_apenas_numeros(texto) -> str:
    """Remove tudo que não for dígito."""
    if pd.isna(texto):
        return ""
    return re.sub(r"\D", "", str(texto))


# ---------------------------------------------------------------------------
# Autenticação OAuth2
# ---------------------------------------------------------------------------

def obter_token_acesso(client_id: str, client_secret: str) -> dict:
    """
    Autentica na API do GoTo Connect usando o fluxo OAuth2 Client Credentials
    e retorna o token de acesso junto com suas informações.

    Args:
        client_id:     ID do cliente OAuth2 cadastrado no portal GoTo.
        client_secret: Senha/segredo do cliente OAuth2.

    Returns:
        Dicionário com chaves: 'access_token', 'token_type', 'expires_in'.

    Raises:
        ConnectionError: Se não for possível conectar ao servidor de autenticação.
        ValueError:      Se as credenciais forem inválidas ou a resposta inesperada.
    """
    # O GoTo usa Basic Auth com as credenciais codificadas em Base64
    credenciais = f"{client_id}:{client_secret}"
    credenciais_b64 = base64.b64encode(credenciais.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {credenciais_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    payload = {"grant_type": "client_credentials"}

    try:
        resposta = requests.post(
            GOTO_TOKEN_URL,
            headers=headers,
            data=payload,
            timeout=GOTO_REQUEST_TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()

        if "access_token" not in dados:
            raise ValueError(
                f"Resposta inesperada do servidor de autenticação: {dados}"
            )

        logger.info("Token GoTo obtido com sucesso. Expira em %s segundos.", dados.get("expires_in"))
        return dados

    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(
            "Não foi possível conectar ao servidor de autenticação do GoTo. "
            "Verifique a conexão com a Internet."
        ) from e
    except requests.exceptions.Timeout as e:
        raise ConnectionError(
            f"Tempo limite excedido ao tentar autenticar no GoTo ({GOTO_REQUEST_TIMEOUT}s)."
        ) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        corpo = e.response.text if e.response is not None else ""
        if status == 401:
            raise ValueError(
                "Credenciais GoTo inválidas (401 Unauthorized). "
                "Verifique GOTO_CLIENT_ID e GOTO_CLIENT_SECRET no arquivo .env."
            ) from e
        raise ValueError(
            f"Erro HTTP {status} ao autenticar no GoTo: {corpo}"
        ) from e


def obter_chave_conta(access_token: str) -> str:
    """
    Busca a chave de conta (accountKey) do usuário autenticado.
    Essa chave é necessária para acessar os relatórios de chamadas.

    Args:
        access_token: Token de acesso obtido via `obter_token_acesso()`.

    Returns:
        String com o accountKey do usuário.

    Raises:
        ValueError: Se não for possível obter a chave de conta.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    try:
        resposta = requests.get(
            GOTO_IDENTITY_URL,
            headers=headers,
            timeout=GOTO_REQUEST_TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()

        account_key = dados.get("accountKey")
        if not account_key:
            raise ValueError(
                f"Campo 'accountKey' não encontrado na resposta de identidade: {dados}"
            )

        logger.info("AccountKey obtido: %s", account_key)
        return str(account_key)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        corpo = e.response.text if e.response is not None else ""
        raise ValueError(
            f"Erro HTTP {status} ao buscar chave de conta GoTo: {corpo}"
        ) from e


# ---------------------------------------------------------------------------
# Busca de Relatórios de Chamadas
# ---------------------------------------------------------------------------

def buscar_chamadas(
    access_token: str,
    account_key: str,
    data_inicio: datetime,
    data_fim: datetime,
    callback_progresso=None,
) -> list[dict]:
    """
    Busca todas as chamadas num intervalo de datas, percorrendo todas as
    páginas automaticamente (paginação automática).

    Args:
        access_token:        Token de acesso Bearer.
        account_key:         Chave de conta GoTo.
        data_inicio:         Data/hora de início (objeto datetime, com ou sem fuso).
        data_fim:            Data/hora de fim (objeto datetime, com ou sem fuso).
        callback_progresso:  Função opcional chamada a cada página carregada,
                             recebendo (pagina_atual, total_registros).

    Returns:
        Lista de dicionários, cada um representando uma chamada.

    Raises:
        ValueError:      Se os parâmetros forem inválidos ou a API retornar erro.
        ConnectionError: Se houver falha de conexão.
    """
    if data_inicio >= data_fim:
        raise ValueError("data_inicio deve ser anterior a data_fim.")

    # Converte para UTC no formato ISO 8601 com sufixo 'Z'
    def para_iso_utc(dt: datetime) -> str:
        if dt.tzinfo is None:
            # Sem fuso: trata como horário de Brasília (UTC-3) e converte para UTC
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    inicio_str = para_iso_utc(data_inicio)
    fim_str = para_iso_utc(data_fim)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    url = GOTO_CALLS_URL.format(account_key=account_key)
    todas_chamadas: list[dict] = []
    pagina = 1

    logger.info(
        "Iniciando busca de chamadas: %s a %s (conta: %s)", inicio_str, fim_str, account_key
    )

    while True:
        params = {
            "startTime": inicio_str,
            "endTime": fim_str,
            "count": GOTO_PAGE_SIZE,
            "page": pagina,
        }

        try:
            resposta = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=GOTO_REQUEST_TIMEOUT,
            )
            resposta.raise_for_status()
            dados = resposta.json()

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            corpo = e.response.text if e.response is not None else ""
            raise ValueError(
                f"Erro HTTP {status} ao buscar chamadas GoTo (página {pagina}): {corpo}"
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                "Falha de conexão ao buscar chamadas na API GoTo. "
                "Verifique a conexão com a Internet."
            ) from e
        except requests.exceptions.Timeout as e:
            raise ConnectionError(
                f"Tempo limite excedido ao buscar chamadas (página {pagina})."
            ) from e

        itens = dados.get("items", [])
        todas_chamadas.extend(itens)
        total_registros = dados.get("totalCount", len(todas_chamadas))

        logger.info(
            "Página %d carregada: %d itens (total acumulado: %d / %d)",
            pagina, len(itens), len(todas_chamadas), total_registros,
        )

        if callback_progresso:
            callback_progresso(pagina, total_registros)

        # Verifica se há mais páginas
        if len(itens) < GOTO_PAGE_SIZE or len(todas_chamadas) >= total_registros:
            break

        pagina += 1

    logger.info("Busca concluída. Total de chamadas retornadas: %d", len(todas_chamadas))
    return todas_chamadas


# ---------------------------------------------------------------------------
# Transformação dos dados da API para o schema do banco de dados
# ---------------------------------------------------------------------------

def transformar_para_dataframe(chamadas: list[dict]) -> pd.DataFrame:
    """
    Transforma a lista de chamadas retornada pela API do GoTo em um DataFrame
    compatível com a tabela `atendimentos_goto` do banco de dados WikiSuporte.

    Campos mapeados da API  →  coluna no banco:
        id / callId          →  id_conversa
        startTime            →  data_chamada
        duration (segundos)  →  duracao_ms (convertido para ms)
        direction            →  direcao
        result / callResult  →  resultado
        callerNumber         →  telefone_origem (mascarado) + telefone_hash
        participants         →  participantes
        recorded             →  gravado

    Args:
        chamadas: Lista de dicionários retornada por `buscar_chamadas()`.

    Returns:
        DataFrame pronto para ser salvo na tabela `atendimentos_goto`.
    """
    if not chamadas:
        return pd.DataFrame()

    registros = []
    for chamada in chamadas:
        # --- ID da conversa ---
        id_conversa = str(
            chamada.get("id")
            or chamada.get("callId")
            or chamada.get("sessionId")
            or ""
        ).strip()

        # --- Data da chamada ---
        start_raw = chamada.get("startTime") or chamada.get("startDateTime") or ""
        try:
            data_chamada = pd.to_datetime(start_raw, errors="coerce")
            # Remove informação de fuso horário para compatibilidade com PostgreSQL (timezone-naive)
            if data_chamada is not pd.NaT and hasattr(data_chamada, "tzinfo") and data_chamada.tzinfo is not None:
                data_chamada = data_chamada.tz_localize(None)
        except Exception:
            data_chamada = pd.NaT

        # --- Duração em milissegundos ---
        duracao_segundos = chamada.get("duration") or chamada.get("talkTime") or 0
        try:
            duracao_ms = int(float(duracao_segundos) * 1000)
        except (ValueError, TypeError):
            duracao_ms = 0

        # --- Direção da chamada ---
        direcao_raw = (
            chamada.get("direction")
            or chamada.get("callDirection")
            or ""
        )
        direcao = str(direcao_raw).strip().upper()
        # Normaliza para o padrão já salvo pela importação CSV
        if direcao == "INBOUND":
            direcao = "RECEBIDA"
        elif direcao == "OUTBOUND":
            direcao = "EFETUADA"

        # --- Resultado da chamada ---
        resultado_raw = (
            chamada.get("result")
            or chamada.get("callResult")
            or chamada.get("disposition")
            or ""
        )
        resultado = str(resultado_raw).strip().upper()

        # --- Telefone de origem (LGPD) ---
        telefone_raw = _extrair_apenas_numeros(
            chamada.get("callerNumber")
            or chamada.get("from")
            or chamada.get("fromNumber")
            or ""
        )
        telefone_hash = _gerar_hash_lgpd(telefone_raw)
        telefone_origem = _mascarar_telefone(telefone_raw)

        # --- Participantes ---
        participantes_lista = chamada.get("participants", [])
        if isinstance(participantes_lista, list):
            participantes = ", ".join(str(p) for p in participantes_lista)
        else:
            participantes = str(participantes_lista)

        # Fallback: usa os campos from/to se participants estiver vazio
        if not participantes.strip():
            from_num = str(chamada.get("callerNumber") or chamada.get("from") or "")
            to_num = str(chamada.get("calleeNumber") or chamada.get("to") or "")
            participantes = f"{from_num} {to_num}".strip()

        # --- Gravação ---
        gravado = str(chamada.get("recorded", "false")).lower()

        # --- ID sintético para chamadas sem ID nativo ---
        if not id_conversa:
            # Usa SHA-256 (consistente com o restante do módulo) em vez de MD5
            data_str = data_chamada.isoformat() if pd.notna(data_chamada) else "SEM_DATA"
            assinatura = f"{data_str}_{telefone_hash}_{duracao_ms}"
            hash_sintetico = hashlib.sha256(assinatura.encode("utf-8")).hexdigest()
            id_conversa = f"SINTETICO_{hash_sintetico}"

        registros.append({
            "id_conversa": id_conversa,
            "data_chamada": data_chamada,
            "duracao_ms": duracao_ms,
            "direcao": direcao,
            "resultado": resultado,
            "telefone_hash": telefone_hash,
            "telefone_origem": telefone_origem,
            "participantes": participantes,
            "gravado": gravado,
            "data_importacao": datetime.now(),
        })

    df = pd.DataFrame(registros)

    # Garante o tipo correto para duracao_ms (Int64 aceita nulos)
    df["duracao_ms"] = pd.to_numeric(df["duracao_ms"], errors="coerce").astype("Int64")

    return df


# ---------------------------------------------------------------------------
# Função de alto nível: orquestra autenticação + busca + transformação
# ---------------------------------------------------------------------------

def buscar_atendimentos_goto(
    data_inicio: datetime,
    data_fim: datetime,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    callback_progresso=None,
) -> pd.DataFrame:
    """
    Função principal que orquestra toda a integração com a API do GoTo:
        1. Autentica e obtém o token de acesso.
        2. Busca a chave de conta (accountKey).
        3. Busca todas as chamadas no intervalo de datas informado.
        4. Transforma e retorna os dados em um DataFrame pronto para o banco.

    As credenciais são carregadas automaticamente das variáveis de ambiente
    GOTO_CLIENT_ID e GOTO_CLIENT_SECRET quando não fornecidas explicitamente.

    Args:
        data_inicio:      Data/hora de início do período (datetime).
        data_fim:         Data/hora de fim do período (datetime).
        client_id:        Opcional. Se None, usa GOTO_CLIENT_ID do .env.
        client_secret:    Opcional. Se None, usa GOTO_CLIENT_SECRET do .env.
        callback_progresso: Opcional. Função chamada a cada página carregada.

    Returns:
        DataFrame com as colunas do schema `atendimentos_goto`.

    Raises:
        ValueError:      Credenciais ausentes, inválidas, ou período inválido.
        ConnectionError: Falha de conexão com a API do GoTo.
    """
    # Carrega credenciais do .env se não fornecidas
    cid = client_id or os.getenv("GOTO_CLIENT_ID", "")
    csecret = client_secret or os.getenv("GOTO_CLIENT_SECRET", "")

    if not cid or not csecret:
        raise ValueError(
            "Credenciais GoTo não configuradas. "
            "Defina GOTO_CLIENT_ID e GOTO_CLIENT_SECRET no arquivo .env."
        )

    # 1. Autenticação
    token_dados = obter_token_acesso(cid, csecret)
    access_token = token_dados["access_token"]

    # 2. Chave de conta
    account_key = obter_chave_conta(access_token)

    # 3. Busca das chamadas
    chamadas = buscar_chamadas(
        access_token=access_token,
        account_key=account_key,
        data_inicio=data_inicio,
        data_fim=data_fim,
        callback_progresso=callback_progresso,
    )

    # 4. Transformação para DataFrame
    df = transformar_para_dataframe(chamadas)
    return df


# ---------------------------------------------------------------------------
# Verificação de conectividade / saúde da API
# ---------------------------------------------------------------------------

def verificar_conectividade(client_id: Optional[str] = None, client_secret: Optional[str] = None) -> tuple[bool, str]:
    """
    Testa a conectividade com a API do GoTo e valida as credenciais.

    Returns:
        Tupla (sucesso: bool, mensagem: str).
    """
    try:
        cid = client_id or os.getenv("GOTO_CLIENT_ID", "")
        csecret = client_secret or os.getenv("GOTO_CLIENT_SECRET", "")

        if not cid or not csecret:
            return False, "Credenciais GoTo não configuradas no arquivo .env."

        token_dados = obter_token_acesso(cid, csecret)
        account_key = obter_chave_conta(token_dados["access_token"])
        return True, f"✅ Conectado com sucesso! Conta GoTo: {account_key}"

    except ValueError as e:
        return False, f"❌ Erro de autenticação: {e}"
    except ConnectionError as e:
        return False, f"❌ Falha de conexão: {e}"
    except Exception as e:
        return False, f"❌ Erro inesperado: {e}"
