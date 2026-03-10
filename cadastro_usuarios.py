import re
import bcrypt
from modules.database import get_connection
from sqlalchemy import text

def validar_senha_forte(senha):
    """Valida: Mínimo 8 caracteres, 1 Maiúscula, 1 Número, 1 Caractere Especial."""
    if len(senha) < 8: return False, "A senha deve ter pelo menos 8 caracteres."
    if not re.search(r"[A-Z]", senha): return False, "A senha deve ter pelo menos 1 letra maiúscula."
    if not re.search(r"[0-9]", senha): return False, "A senha deve ter pelo menos 1 número."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", senha): return False, "A senha deve ter pelo menos 1 caractere especial."
    return True, "Senha válida."

def criar_usuario(username, senha, perfil):
    valida, msg = validar_senha_forte(senha)
    if not valida:
        print(f"Erro: {msg}")
        return

    # Criptografa a senha antes de salvar
    salt = bcrypt.gensalt()
    senha_hash = bcrypt.hashpw(senha.encode('utf-8'), salt).decode('utf-8')

    try:
        engine = get_connection()
        with engine.begin() as conn:
            # Query atualizada para incluir a coluna 'perfil'
            query = text("INSERT INTO usuarios (username, password_hash, perfil) VALUES (:u, :h, :p)")
            # O .lower() garante a padronização no banco de dados
            conn.execute(query, {"u": username, "h": senha_hash, "p": perfil.lower()})
        print(f"✅ Usuário '{username}' criado com sucesso sob o perfil de '{perfil.lower()}'!")
    except Exception as e:
        print(f"Erro ao criar usuário (já existe?): {e}")

if __name__ == "__main__":
    print("=== CRIAÇÃO DE USUÁRIO DO DASHBOARD ===")
    user = input("Digite o nome de usuário: ")
    senha = input("Digite a senha forte: ")
    
    print("\n=== SELECIONE O PERFIL DE ACESSO ===")
    print("1 - Analista de Suporte (Acesso restrito à fila de chamados)")
    print("2 - Coordenação (Acesso a métricas e relatórios gerenciais)")
    # SuperAdmin removido por segurança (Apenas via banco de dados diretamente)
    
    opcao = input("\nDigite o número correspondente ao perfil: ").strip()
    
    if opcao == '1':
        perfil = "analista de suporte"
    elif opcao == '2':
        perfil = "coordenação"
    else:
        print("⚠️ Opção inválida ou restrita. Atribuindo perfil padrão: analista de suporte.")
        perfil = "analista de suporte"
        
    criar_usuario(user, senha, perfil)