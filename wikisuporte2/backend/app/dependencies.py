from typing import Generator, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import SessionLocal
from .services.auth_service import decode_token
from .models.usuario import Usuario

bearer_scheme = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    """Dependency que fornece uma sessão do banco de dados."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """Extrai e valida o JWT do header Authorization, retorna o usuário autenticado."""
    token = credentials.credentials
    token_data = decode_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    usuario = db.query(Usuario).filter(
        Usuario.id == token_data.usuario_id,
        Usuario.ativo == True,
    ).first()
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def require_role(*roles: str):
    """Dependency factory que verifica se o usuário possui uma das roles permitidas."""
    def _check(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        if current_user.role is None or current_user.role.nome not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Roles permitidas: {list(roles)}",
            )
        return current_user
    return _check
