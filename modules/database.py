import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
DB_USER = os.getenv("DB_USER", "postgres")   
DB_PASS = os.getenv("DB_PASS") 
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5455")   
DB_NAME = os.getenv("DB_NAME", "central_chamados")

# Monta a string de conexão no padrão exigido pelo SQLAlchemy
connection_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    # ⚠️ Performance: O motor (engine) agora é criado APENAS UMA VEZ 
    # quando este arquivo é lido. Ele gerencia as conexões automaticamente.
    engine_global = create_engine(connection_string)
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