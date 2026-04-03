# Arquivo: config.py
import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv()

class Config:
    """Centraliza e tipa todas as variáveis de ambiente do sistema."""
    
    # --- CONFIGURAÇÕES DO BANCO DE DADOS ---
    DB_HOST = os.getenv("DB_HOST", "localhost")
    # Converte a porta para inteiro para evitar erros no driver de conexão (psycopg2, etc.)
    DB_PORT = int(os.getenv("DB_PORT", 5432)) 
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")

    # --- CREDENCIAIS DE ACESSO TECNUV / LGPD ---
    # Não levantar exceção na importação: o Streamlit (app.py) deve subir mesmo sem
    # Tecnuv configurado (homologação focada em login/UI). O motor de extração e o
    # robô validam credenciais ao executar.
    TECNUV_USER = os.getenv("TECNUV_USER", "").strip()
    TECNUV_PASS = os.getenv("TECNUV_PASS", "").strip()
    LGPD_SECRET_KEY = os.getenv("LGPD_SECRET_KEY", "").strip()

    # --- CREDENCIAIS DA API GOTO CONNECT (Plano Principal de Integração) ---
    # Estas credenciais são opcionais: o sistema funciona sem elas usando o
    # upload manual de arquivos como Plano B.
    GOTO_CLIENT_ID = os.getenv("GOTO_CLIENT_ID", "")
    GOTO_CLIENT_SECRET = os.getenv("GOTO_CLIENT_SECRET", "")

    # --- CONFIGURAÇÕES DO SISTEMA ---
    # Converte a string "True" ou "False" do .env para boolean: True = navegador oculto (headless)
    _headless_str = os.getenv("MODO_HEADLESS", "False").strip().lower()
    MODO_HEADLESS = _headless_str in ("true", "1", "yes")
# ... (outras configurações)
