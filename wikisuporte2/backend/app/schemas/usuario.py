from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class SetorBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    setor_pai_id: Optional[int] = None
    ativo: bool = True


class SetorCreate(SetorBase):
    pass


class SetorResponse(SetorBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class RoleBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    nivel: int = 0
    ativo: bool = True


class RoleCreate(RoleBase):
    pass


class RoleResponse(RoleBase):
    id: int

    model_config = {"from_attributes": True}


class UsuarioBase(BaseModel):
    nome: str
    email: str
    role_id: Optional[int] = None
    setor_id: Optional[int] = None
    ativo: bool = True


class UsuarioCreate(UsuarioBase):
    senha: str


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    role_id: Optional[int] = None
    setor_id: Optional[int] = None
    ativo: Optional[bool] = None
    senha: Optional[str] = None


class UsuarioResponse(UsuarioBase):
    id: int
    criado_em: datetime
    ultimo_login: Optional[datetime] = None
    role: Optional[RoleResponse] = None
    setor: Optional[SetorResponse] = None

    model_config = {"from_attributes": True}
