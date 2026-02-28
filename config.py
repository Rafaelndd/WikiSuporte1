# Arquivo: config.py
import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env apenas uma vez
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

    # --- CREDENCIAIS DE ACESSO TECNUV ---
    try:
        TECNUV_USER = os.environ["TECNUV_USER"]
        TECNUV_PASS = os.environ["TECNUV_PASS"]
        LGPD_SECRET_KEY = os.environ["LGPD_SECRET_KEY"]
    except KeyError as e:
        raise ValueError(f"ERRO CRÍTICO: A variável obrigatória {e} não foi encontrada no arquivo .env.")

    # --- CONFIGURAÇÕES DO SISTEMA ---
    # Resolve o bug do booleano: Converte a string "True" ou "False" para o tipo Boolean real do Python
    _headless_str = os.getenv("MODO_HEADLESS", "False").lower()
    MODO_HEADLESS = _headless_str == "false"
# ... (outras configurações)
