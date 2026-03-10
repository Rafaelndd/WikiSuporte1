from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..dependencies import get_db, get_current_user
from ..models.usuario import Usuario
from ..schemas.auth import LoginRequest, TokenResponse, RefreshRequest, UsuarioMeResponse
from ..services.auth_service import (
    verify_password, create_access_token, create_refresh_token, decode_token
)
from ..config import settings

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Autentica o usuário e retorna os tokens JWT."""
    usuario = db.query(Usuario).filter(
        Usuario.email == payload.email,
        Usuario.ativo == True,
    ).first()

    if not usuario or not verify_password(payload.senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
        )

    role_nome = usuario.role.nome if usuario.role else None
    access_token = create_access_token(usuario.id, usuario.email, role_nome)
    refresh_token = create_refresh_token(usuario.id, usuario.email)

    # Atualiza último login
    usuario.ultimo_login = datetime.utcnow()
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    """Renova o access token usando um refresh token válido."""
    token_data = decode_token(payload.refresh_token)
    if token_data is None or token_data.tipo != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        )

    usuario = db.query(Usuario).filter(
        Usuario.id == token_data.usuario_id,
        Usuario.ativo == True,
    ).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )

    role_nome = usuario.role.nome if usuario.role else None
    new_access = create_access_token(usuario.id, usuario.email, role_nome)
    new_refresh = create_refresh_token(usuario.id, usuario.email)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UsuarioMeResponse)
def me(current_user: Usuario = Depends(get_current_user)):
    """Retorna os dados do usuário autenticado."""
    return UsuarioMeResponse(
        id=current_user.id,
        nome=current_user.nome,
        email=current_user.email,
        role=current_user.role.nome if current_user.role else None,
        setor=current_user.setor.nome if current_user.setor else None,
        ativo=current_user.ativo,
        ultimo_login=current_user.ultimo_login,
    )
