from modules.database import get_connection
from sqlalchemy import text

def adicionar_coluna():
    print("Iniciando atualização do Banco de Dados...")
    engine = get_connection()
    
    try:
        with engine.begin() as conn:
            # Comando SQL para adicionar a coluna na tabela existente
            query = text("ALTER TABLE atendimentos_multi360 ADD COLUMN data_ultima_mensagem TIMESTAMP;")
            conn.execute(query)
            print("✅ SUCESSO! A coluna 'data_ultima_mensagem' foi adicionada à tabela 'atendimentos_multi360'.")
    except Exception as e:
        print(f"⚠️ Aviso/Erro: {e}")
        print("Se o erro disser 'column already exists' ou similar, significa que a coluna já está pronta!")

if __name__ == "__main__":
    adicionar_coluna()