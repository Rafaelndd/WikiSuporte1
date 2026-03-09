from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..dependencies import get_db, get_current_user, require_role
from ..models.usuario import Usuario, Setor, Role
from ..schemas.usuario import (
    UsuarioCreate, UsuarioUpdate, UsuarioResponse,
    SetorCreate, SetorResponse,
    RoleCreate, RoleResponse,
)
from ..services.auth_service import hash_password

router = APIRouter()


# --- Usuários ---

@router.get("/", response_model=List[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "gestor", "admin")),
):
    return db.query(Usuario).filter(Usuario.ativo == True).all()


@router.get("/{usuario_id}", response_model=UsuarioResponse)
def obter_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    return usuario


@router.post("/", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    payload: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "admin")),
):
    if db.query(Usuario).filter(Usuario.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado")
    usuario = Usuario(
        nome=payload.nome,
        email=payload.email,
        senha_hash=hash_password(payload.senha),
        role_id=payload.role_id,
        setor_id=payload.setor_id,
        ativo=payload.ativo,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.put("/{usuario_id}", response_model=UsuarioResponse)
def atualizar_usuario(
    usuario_id: int,
    payload: UsuarioUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "admin")),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    update_data = payload.model_dump(exclude_unset=True)
    if "senha" in update_data:
        update_data["senha_hash"] = hash_password(update_data.pop("senha"))
    for key, value in update_data.items():
        setattr(usuario, key, value)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "admin")),
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    usuario.ativo = False
    db.commit()


# --- Setores ---

@router.get("/setores/", response_model=List[SetorResponse])
def listar_setores(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Setor).filter(Setor.ativo == True).all()


@router.post("/setores/", response_model=SetorResponse, status_code=status.HTTP_201_CREATED)
def criar_setor(
    payload: SetorCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "admin")),
):
    setor = Setor(**payload.model_dump())
    db.add(setor)
    db.commit()
    db.refresh(setor)
    return setor


# --- Roles ---

@router.get("/roles/", response_model=List[RoleResponse])
def listar_roles(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Role).filter(Role.ativo == True).all()


@router.post("/roles/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def criar_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_role("ceo", "admin")),
):
    role = Role(**payload.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return role
