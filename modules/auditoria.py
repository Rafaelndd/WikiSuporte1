import logging
from typing import Optional
from sqlalchemy.orm import sessionmaker

# Importação absoluta e limpa (padrão de projeto estruturado)
from modules.models import LogAuditoria 
from modules.database import get_connection

# Configura o logger específico para este módulo
logger = logging.getLogger(__name__)

def registrar_log_auditoria(usuario_id: int, acao: str, detalhes: Optional[str] = None) -> None:
    """
    Registra uma ação no banco de dados para fins de auditoria e segurança.
    Utiliza a conexão padrão (get_connection) para manter a integridade da arquitetura.
    
    Parâmetros:
    - usuario_id (int): ID do usuário logado realizando a ação.
    - acao (str): Nome da ação (ex: 'LOGIN', 'ACEITE_TERMOS').
    - detalhes (str, opcional): Contexto extra (ex: 'Aba de CSV acessada').
    """
    # 1. Obtém o motor de conexão central e a sessão
    try:
        engine = get_connection()
        Session = sessionmaker(bind=engine)
        session = Session() 
    except Exception as e:
        logger.error(f"[Auditoria] Falha catastrófica ao conectar com o banco: {e}")
        return # Aborta silenciosamente para não travar a navegação do usuário
    
    try:
        # 2. Monta o objeto do log
        novo_log = LogAuditoria(
            usuario_id=usuario_id,
            acao=acao,
            detalhes=detalhes
        )
        
        # 3. Salva no banco de dados
        session.add(novo_log)
        session.commit()
        logger.info(f"[Auditoria] Salvo com sucesso | User ID: {usuario_id} | Ação: {acao}")
        
    except Exception as e:
        # 4. Em caso de erro, desfaz a transação imediatamente para evitar travamento da tabela
        session.rollback()
        logger.error(f"[Auditoria] Falha ao registrar log no banco: {e}")
        
    finally:
        # 5. OBRIGATÓRIO: Fecha a sessão para liberar o "Pool" de conexões
        session.close()