"""
Integração com a API GoTo Connect para o WikiSuporte 2.0.
Migração e adaptação da lógica original de goto_api.py (v1.0).
"""
import httpx
import logging
from typing import Optional, Dict, Any
from ..config import settings

logger = logging.getLogger(__name__)

GOTO_TOKEN_URL = "https://authentication.logmeininc.com/oauth/token"
GOTO_API_BASE = "https://api.goto.com"


async def get_access_token() -> Optional[str]:
    """
    Obtém um access token da GoTo Connect usando o fluxo refresh_token.
    Requer GOTO_CLIENT_ID, GOTO_CLIENT_SECRET e GOTO_REFRESH_TOKEN no .env
    """
    if not all([settings.GOTO_CLIENT_ID, settings.GOTO_CLIENT_SECRET, settings.GOTO_REFRESH_TOKEN]):
        logger.warning("Credenciais GoTo não configuradas. Pulando integração.")
        return None

    data = {
        "grant_type": "refresh_token",
        "refresh_token": settings.GOTO_REFRESH_TOKEN,
        "client_id": settings.GOTO_CLIENT_ID,
        "client_secret": settings.GOTO_CLIENT_SECRET,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GOTO_TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()
            return token_data.get("access_token")
    except httpx.HTTPStatusError as exc:
        logger.error(f"Erro HTTP ao obter token GoTo: {exc.response.status_code} - {exc.response.text}")
        return None
    except Exception as exc:
        logger.error(f"Erro ao conectar à API GoTo: {exc}")
        return None


async def fetch_calls(
    data_inicio: str,
    data_fim: str,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca atendimentos telefônicos na API GoTo Connect.

    Args:
        data_inicio: Data de início no formato ISO 8601.
        data_fim: Data de fim no formato ISO 8601.
        access_token: Token JWT da GoTo (se None, obtém automaticamente).

    Returns:
        Dicionário com os dados retornados pela API ou dict vazio em caso de erro.
    """
    if access_token is None:
        access_token = await get_access_token()
    if access_token is None:
        return {}

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"startTime": data_inicio, "endTime": data_fim}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{GOTO_API_BASE}/call-reports/v1/accounts/calls",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(f"Erro HTTP ao buscar atendimentos GoTo: {exc.response.status_code}")
        return {}
    except Exception as exc:
        logger.error(f"Erro ao buscar atendimentos GoTo: {exc}")
        return {}


# Aliases em português para compatibilidade com código legado
obter_access_token = get_access_token
buscar_atendimentos = fetch_calls


async def check_connectivity() -> bool:
    """Verifica se a integração com a GoTo Connect está operacional."""
    token = await get_access_token()
    return token is not None


# Alias em português
verificar_conectividade = check_connectivity
