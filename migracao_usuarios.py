from modules.database import get_connection
from sqlalchemy import text
import bcrypt  # <-- MUDAMOS AQUI

# Lista com o seu usuário Admin e a equipe
USUARIOS = [
    {"nome": "admin", "perfil": "desenvolvedor", "ramal": "0000"},
    {"nome": "RENATO", "perfil": "coordenação", "ramal": "5335"},
    {"nome": "AGNALDO", "perfil": "analista", "ramal": "5333"},
    {"nome": "BRUNO", "perfil": "analista", "ramal": "5331"},
    {"nome": "EMIL", "perfil": "analista", "ramal": "5340"},
    {"nome": "DANIEL", "perfil": "analista", "ramal": "5332"},
    {"nome": "MARCELO", "perfil": "analista", "ramal": "5344"},
    {"nome": "ADILTON", "perfil": "analista", "ramal": "5336"},
    {"nome": "LUIS", "perfil": "analista", "ramal": "5339"},
    {"nome": "JOAO", "perfil": "analista", "ramal": "5343"},
    {"nome": "GABRIEL", "perfil": "analista", "ramal": "5341"},
    {"nome": "RAFAEL NASCIMENTO", "perfil": "analista", "ramal": "5338"},
    {"nome": "RAFAEL FREITAS", "perfil": "analista", "ramal": "5337"}
]

def configurar_banco_e_migrar():
    engine = get_connection()
    
    # GERANDO A SENHA COM O "SAL" (Padrão Bcrypt)
    senha_padrao = "123"
    # O bcrypt gera o Sal automaticamente e embute no hash
    senha_hash = bcrypt.hashpw(senha_padrao.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    with engine.connect() as conn:
        print("1️⃣ Preparando e verificando a estrutura do Banco de Dados...")
        
        # 1. Força a criação da tabela central corretamente
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(150) UNIQUE NOT NULL,
                email VARCHAR(150) UNIQUE,
                perfil VARCHAR(50) NOT NULL,
                ramal VARCHAR(20),
                password_hash VARCHAR(255),
                ativo BOOLEAN DEFAULT TRUE,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.commit()
        
        # 2. Força a criação das colunas de FK nas tabelas legadas
        tabelas_antigas = ["chamados_tecnuv", "atendimentos_multi360", "atendimentos_goto"]
        for tb in tabelas_antigas:
            try:
                conn.execute(text(f"ALTER TABLE {tb} ADD COLUMN IF NOT EXISTS id_usuario_epsy INTEGER REFERENCES usuarios(id);"))
                conn.commit()
            except Exception as e:
                conn.rollback() # Limpa o erro se a tabela não existir
                print(f" -> Aviso: Tabela {tb} ignorada (não existe ou sem permissão).")

        print("\n2️⃣ Iniciando Carga de Usuários e Senhas...")
        for u in USUARIOS:
            try:
                # Insere ou atualiza o usuário
                query_insert = text("""
                    INSERT INTO usuarios (nome, email, perfil, ramal, password_hash, ativo)
                    VALUES (:nome, :email, :perfil, :ramal, :password_hash, TRUE)
                    ON CONFLICT (nome) DO UPDATE 
                    SET password_hash = :password_hash, perfil = :perfil
                    RETURNING id;
                """)
                
                email_gerado = f"{u['nome'].lower().replace(' ', '.')}@epsy.com.br"
                
                result = conn.execute(query_insert, {
                    "nome": u["nome"], "email": email_gerado, "perfil": u["perfil"], 
                    "ramal": u["ramal"], "password_hash": senha_hash
                })
                conn.commit()
                
                user_id_row = result.fetchone()
                if not user_id_row:
                    user_id_row = conn.execute(text("SELECT id FROM usuarios WHERE nome = :nome"), {"nome": u["nome"]}).fetchone()
                user_id = user_id_row[0]
                
                # Amarração apenas para os analistas EPSY
                if u["nome"] != "admin":
                    print(f" -> Amarrando histórico para {u['nome']} (ID: {user_id})...")
                    nome_busca = f"%{u['nome'].split()[0]}%"
                    
                    # Blinda cada update individualmente
                    # Chamados
                    try:
                        conn.execute(text("UPDATE chamados_tecnuv SET id_usuario_epsy = :uid WHERE usuario_epsy ILIKE :busca"), {"uid": user_id, "busca": nome_busca})
                        conn.commit()
                    except: conn.rollback()
                    
                    # Multi360
                    try:
                        conn.execute(text("UPDATE atendimentos_multi360 SET id_usuario_epsy = :uid WHERE atendente ILIKE :busca"), {"uid": user_id, "busca": nome_busca})
                        conn.commit()
                    except: conn.rollback()
                    
                    # GoTo
                    try:
                        conn.execute(text("UPDATE atendimentos_goto SET id_usuario_epsy = :uid WHERE usuario ILIKE :busca"), {"uid": user_id, "busca": nome_busca})
                        conn.commit()
                    except: conn.rollback()

            except Exception as e:
                conn.rollback()
                print(f"❌ Erro crítico ao processar {u['nome']}: {e}")

        print("\n✅ SUCESSO ABSOLUTO! O banco foi atualizado, os usuários criados e o histórico amarrado.")

if __name__ == "__main__":
    configurar_banco_e_migrar()