from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from ..dependencies import get_db, get_current_user
from ..models.usuario import Usuario
from ..models.suporte import Atendimento, Chamado, Plantao, Importacao
from ..schemas.suporte import (
    AtendimentoCreate, AtendimentoResponse,
    ChamadoCreate, ChamadoUpdate, ChamadoResponse,
    PlantaoCreate, PlantaoResponse,
    ImportacaoCreate, ImportacaoResponse,
)
from ..services.rbac import filtrar_por_permissao

router = APIRouter()


# --- Atendimentos ---

@router.get("/atendimentos", response_model=List[AtendimentoResponse])
def listar_atendimentos(
    analista_id: Optional[int] = Query(None),
    fonte: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Atendimento)
    if analista_id:
        q = q.filter(Atendimento.analista_id == analista_id)
    if fonte:
        q = q.filter(Atendimento.fonte == fonte)
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Atendimento.analista_id)
    return q.order_by(Atendimento.data_atendimento.desc()).all()


@router.post("/atendimentos", response_model=AtendimentoResponse, status_code=status.HTTP_201_CREATED)
def registrar_atendimento(
    payload: AtendimentoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    atendimento = Atendimento(**payload.model_dump(), analista_id=current_user.id)
    db.add(atendimento)
    db.commit()
    db.refresh(atendimento)
    return atendimento


@router.get("/atendimentos/{atendimento_id}", response_model=AtendimentoResponse)
def obter_atendimento(
    atendimento_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    atendimento = db.query(Atendimento).filter(Atendimento.id == atendimento_id).first()
    if not atendimento:
        raise HTTPException(status_code=404, detail="Atendimento não encontrado")
    return atendimento


# --- Chamados ---

@router.get("/chamados", response_model=List[ChamadoResponse])
def listar_chamados(
    status_filtro: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Chamado)
    if status_filtro:
        q = q.filter(Chamado.status == status_filtro)
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Chamado.analista_id)
    return q.order_by(Chamado.data_abertura.desc()).all()


@router.post("/chamados", response_model=ChamadoResponse, status_code=status.HTTP_201_CREATED)
def criar_chamado(
    payload: ChamadoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    chamado = Chamado(**payload.model_dump())
    db.add(chamado)
    db.commit()
    db.refresh(chamado)
    return chamado


@router.put("/chamados/{chamado_id}", response_model=ChamadoResponse)
def atualizar_chamado(
    chamado_id: int,
    payload: ChamadoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    chamado = db.query(Chamado).filter(Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(chamado, key, value)
    db.commit()
    db.refresh(chamado)
    return chamado


# --- Plantões ---

@router.get("/plantoes", response_model=List[PlantaoResponse])
def listar_plantoes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Plantao)
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Plantao.analista_id)
    return q.order_by(Plantao.data_inicio.desc()).all()


@router.post("/plantoes", response_model=PlantaoResponse, status_code=status.HTTP_201_CREATED)
def registrar_plantao(
    payload: PlantaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    plantao = Plantao(**payload.model_dump(), analista_id=current_user.id)
    db.add(plantao)
    db.commit()
    db.refresh(plantao)
    return plantao


# --- Importações ---

@router.get("/importacoes", response_model=List[ImportacaoResponse])
def listar_importacoes(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    return db.query(Importacao).order_by(Importacao.criado_em.desc()).all()


@router.post("/importacoes", response_model=ImportacaoResponse, status_code=status.HTTP_201_CREATED)
def iniciar_importacao(
    payload: ImportacaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    importacao = Importacao(
        usuario_id=current_user.id,
        tipo=payload.tipo,
        nome_arquivo=payload.nome_arquivo,
        status="pendente",
    )
    db.add(importacao)
    db.commit()
    db.refresh(importacao)
    return importacao
