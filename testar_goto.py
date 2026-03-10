import os
import requests
import base64
import pandas as pd
import re
import io
import datetime

from sqlalchemy import text
from modules.database import get_connection
from datetime import datetime, timedelta
from dotenv import load_dotenv


load_dotenv()

def renovar_token_acesso():
    """Usa o Refresh Token vitalício para gerar um novo Access Token"""
    client_id = os.getenv("GOTO_CLIENT_ID")
    client_secret = os.getenv("GOTO_CLIENT_SECRET")
    refresh_token = os.getenv("GOTO_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("Credenciais do GoTo ausentes no arquivo .env!")

    url_token = "https://authentication.logmeininc.com/oauth/token"
    credenciais = f"{client_id}:{client_secret}"
    credenciais_b64 = base64.b64encode(credenciais.encode()).decode('utf-8')

    headers = {
        "Authorization": f"Basic {credenciais_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    resposta = requests.post(url_token, headers=headers, data=payload)

    if resposta.status_code == 200:
        return resposta.json().get("access_token")
    else:
        raise Exception(f"Falha ao renovar token. Status: {resposta.status_code}. Detalhe: {resposta.text}")

def verificar_conectividade(client_id=None, client_secret=None):
    """Testa se o motor consegue gerar um token novo"""
    try:
        token = renovar_token_acesso()
        if token:
            return True, "✅ Conexão estabelecida com sucesso usando o Refresh Token!"
    except Exception as e:
        return False, str(e)

# (Aqui abaixo entrarão as suas funções de buscar os atendimentos: buscar_atendimentos_goto, etc.)
# Se quiser que eu monte a função exata que busca a lista de chamadas para você, me avise!