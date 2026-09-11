import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# Sempre carrega `.env` da raiz do repositório (não depende do cwd do Streamlit).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()

# --- CONFIGURAÇÕES DO BANCO DE DADOS (alinhado a config.py para produção) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "central_chamados")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS")

# Falha explícita em vez de montar silenciosamente uma connection string com
# "None" no lugar da senha (ex.: postgresql://postgres:None@...), que antes
# só se manifestava como um erro de autenticação confuso do driver.
if not DB_PASS:
    raise RuntimeError(
        "DB_PASS não configurada. Defina-a no .env antes de iniciar a aplicação "
        "— sem ela a conexão com o banco não pode ser estabelecida."
    )

# URL.create escapa automaticamente caracteres especiais na senha/usuário
# (ex.: '@', ':', '/'), o que a interpolação de f-string anterior não fazia.
connection_url = URL.create(
    "postgresql",
    username=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=int(DB_PORT),
    database=DB_NAME,
)

try:
    # Performance: O motor (engine) agora é criado APENAS UMA VEZ
    # quando este arquivo é lido. Ele gerencia as conexões automaticamente.
    engine_global = create_engine(connection_url)
except Exception as e:
    print(f"Erro ao configurar o motor do banco: {e}")
    raise e

def get_connection():
    """
    Retorna a conexão com o banco de dados usando o motor (engine) global do SQLAlchemy.
    Isso evita o esgotamento de conexões e vazamento de memória.
    """
    return engine_global

def carregar_dados_sql(query):
    """
    Função utilitária para carregar dados do banco usando uma query SQL.
    Retorna um DataFrame do Pandas com os resultados.
    """
    # Pega o motor que já está pronto e rodando
    engine = get_connection()
    try:
        # read_sql do Pandas cuida de abrir e fechar a conexão no motor sozinho
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        print(f"Erro ao ler dados do banco: {e}")
        return pd.DataFrame()  # Retorna um DataFrame vazio em caso de erro

def get_engine():
    return engine_global