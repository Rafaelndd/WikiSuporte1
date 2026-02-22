import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES DO BANCO DE DADOS ---
DB_USER = os.getenv("DB_USER", "postgres")   
DB_PASS = os.getenv("DB_PASS", "19983101")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5455")   
DB_NAME = os.getenv("DB_NAME", "central_chamados")

def get_connection():
    """
    Cria e retorna uma conexão com o banco de dados usando SQLAlchemy.
    A string de conexão é construída a partir das variáveis de ambiente.
    """
    # Monta a string de conexão no padrão exigido pelo SQLAlchemy
    connection_string = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        engine = create_engine(connection_string)
        return engine
    except Exception as e:
        print(f"Erro ao configurar a conexão com o banco: {e}")
        raise e

def carregar_dados_sql(query):
    """
    Função utilitária para carregar dados do banco usando uma query SQL.
    Retorna um DataFrame do Pandas com os resultados.
    """
    engine = get_connection()
    try:
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        print(f"Erro ao ler dados do banco: {e}")
        return pd.DataFrame() 