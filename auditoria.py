import os
import sys
from sqlalchemy.orm import sessionmaker

# Garante que o Python encontre a raiz do projeto Epsy Central V4.0
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Agora as importações absolutas funcionarão perfeitamente
from models import LogAuditoria 
from modules.database import get_connection

def registrar_log_auditoria(usuario_id: int, acao: str, detalhes: str = None) -> None:
    """
    Registra uma ação no banco de dados para fins de auditoria e segurança.
    Utiliza a conexão padrão (get_connection) para manter a integridade da arquitetura.
    
    Parâmetros:
    - usuario_id (int): ID do usuário logado realizando a ação.
    - acao (str): Nome da ação (ex: 'LOGIN', 'ACEITE_TERMOS').
    - detalhes (str, opcional): Contexto extra (ex: 'Aba de CSV acessada').
    """
    # 1. Obtém o motor de conexão central do projeto
    engine = get_connection()
    
    # 2. Cria a fábrica de sessões e abre uma conversa com o banco
    Session = sessionmaker(bind=engine)
    session = Session() 
    
    try:
        # 3. Monta o objeto do log
        novo_log = LogAuditoria(
            usuario_id=usuario_id,
            acao=acao,
            detalhes=detalhes
        )
        
        # 4. Salva no banco de dados
        session.add(novo_log)
        session.commit()
        print(f"✅ [Oráculo Log] Salvo com sucesso: User {usuario_id} | {acao}")
        
    except Exception as e:
        # 5. Em caso de erro, desfaz a transação para evitar travamento
        session.rollback()
        print(f"❌ [Oráculo Erro] Falha ao salvar log de auditoria: {e}")
        
    finally:
        # 6. OBRIGATÓRIO: Fecha a sessão para liberar a memória do servidor
        session.close()
        
if __name__ == "__main__":
    # Teste rápido para validar a função de log
    registrar_log_auditoria(usuario_id=1, acao="TESTE_LOG", detalhes="Log de auditoria funcionando corretamente.")
    