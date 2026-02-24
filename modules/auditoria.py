import sys
import io

# --- AJUSTE DE ENCODING (Para evitar o UnicodeEncodeError no Windows) ---
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- CORREÇÃO DE IMPORTS (Para evitar o ModuleNotFoundError via app.py) ---
try:
    from modules.models import LogAuditoria 
    from modules.database import get_connection
except ModuleNotFoundError:
    # Fallback para execução direta do script de auditoria
    from models import LogAuditoria 
    from database import get_connection

from sqlalchemy.orm import sessionmaker


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
        print(f"[PSY Log] Salvo com sucesso: User ID :{usuario_id} | {acao}")
        
    except Exception as e:
        # 5. Em caso de erro, desfaz a transação para evitar travamento
        session.rollback()
        print(f"[PSY Erro] Falha ao registrar log :{e}")
        
    finally:
        # 6. OBRIGATÓRIO: Fecha a sessão para liberar a memória do servidor
        session.close()
        