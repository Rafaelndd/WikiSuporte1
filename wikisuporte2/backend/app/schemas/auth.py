from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: str
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenData(BaseModel):
    usuario_id: int
    email: str
    role: Optional[str] = None
    tipo: str = "access"  # access ou refresh


class UsuarioMeResponse(BaseModel):
    id: int
    nome: str
    email: str
    role: Optional[str] = None
    setor: Optional[str] = None
    ativo: bool
    ultimo_login: Optional[datetime] = None

    model_config = {"from_attributes": True}
