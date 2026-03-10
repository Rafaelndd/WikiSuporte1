from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from ..dependencies import get_db, get_current_user
from ..models.usuario import Usuario
from ..models.tarefa import (
    Espaco, Pasta, Lista, StatusConfig, Tarefa,
    TarefaResponsavel, TarefaLista, Checklist, ChecklistItem, TarefaComentario
)
from ..schemas.tarefa import (
    EspacoCreate, EspacoResponse,
    PastaCreate, PastaResponse,
    ListaCreate, ListaResponse,
    StatusConfigCreate, StatusConfigResponse,
    TarefaCreate, TarefaUpdate, TarefaResponse,
    ChecklistCreate, ChecklistResponse,
    ChecklistItemCreate, ChecklistItemResponse,
    ComentarioCreate, ComentarioResponse,
)

router = APIRouter()


# --- Espaços ---

@router.get("/espacos", response_model=List[EspacoResponse])
def listar_espacos(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Espaco).filter(Espaco.ativo == True).all()


@router.post("/espacos", response_model=EspacoResponse, status_code=status.HTTP_201_CREATED)
def criar_espaco(payload: EspacoCreate, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    espaco = Espaco(**payload.model_dump())
    db.add(espaco)
    db.commit()
    db.refresh(espaco)
    return espaco


@router.delete("/espacos/{espaco_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_espaco(espaco_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    espaco = db.query(Espaco).filter(Espaco.id == espaco_id).first()
    if not espaco:
        raise HTTPException(status_code=404, detail="Espaço não encontrado")
    espaco.ativo = False
    db.commit()


# --- Pastas ---

@router.get("/pastas", response_model=List[PastaResponse])
def listar_pastas(
    espaco_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = db.query(Pasta).filter(Pasta.ativo == True)
    if espaco_id:
        q = q.filter(Pasta.espaco_id == espaco_id)
    return q.all()


@router.post("/pastas", response_model=PastaResponse, status_code=status.HTTP_201_CREATED)
def criar_pasta(payload: PastaCreate, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    pasta = Pasta(**payload.model_dump())
    db.add(pasta)
    db.commit()
    db.refresh(pasta)
    return pasta


# --- Listas ---

@router.get("/listas", response_model=List[ListaResponse])
def listar_listas(
    pasta_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = db.query(Lista).filter(Lista.ativo == True)
    if pasta_id:
        q = q.filter(Lista.pasta_id == pasta_id)
    return q.all()


@router.post("/listas", response_model=ListaResponse, status_code=status.HTTP_201_CREATED)
def criar_lista(payload: ListaCreate, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    lista = Lista(**payload.model_dump())
    db.add(lista)
    db.commit()
    db.refresh(lista)
    return lista


# --- Status Config ---

@router.get("/status", response_model=List[StatusConfigResponse])
def listar_status(
    espaco_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    q = db.query(StatusConfig)
    if espaco_id:
        q = q.filter(StatusConfig.espaco_id == espaco_id)
    return q.order_by(StatusConfig.ordem).all()


@router.post("/status", response_model=StatusConfigResponse, status_code=status.HTTP_201_CREATED)
def criar_status(payload: StatusConfigCreate, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    sc = StatusConfig(**payload.model_dump())
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return sc


# --- Tarefas ---

@router.get("/", response_model=List[TarefaResponse])
def listar_tarefas(
    lista_id: Optional[int] = Query(None),
    status_id: Optional[int] = Query(None),
    responsavel_id: Optional[int] = Query(None),
    apenas_raiz: bool = Query(False, description="Retornar apenas tarefas sem pai"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Tarefa)
    if lista_id:
        q = q.join(TarefaLista).filter(TarefaLista.lista_id == lista_id)
    if status_id:
        q = q.filter(Tarefa.status_id == status_id)
    if responsavel_id:
        q = q.join(TarefaResponsavel).filter(TarefaResponsavel.usuario_id == responsavel_id)
    if apenas_raiz:
        q = q.filter(Tarefa.tarefa_pai_id == None)
    return q.order_by(Tarefa.criado_em.desc()).all()


@router.get("/{tarefa_id}", response_model=TarefaResponse)
def obter_tarefa(tarefa_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    tarefa = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return tarefa


@router.post("/", response_model=TarefaResponse, status_code=status.HTTP_201_CREATED)
def criar_tarefa(
    payload: TarefaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    tarefa_data = payload.model_dump(exclude={"responsaveis_ids", "lista_ids"})
    tarefa = Tarefa(**tarefa_data, criado_por_id=current_user.id)
    db.add(tarefa)
    db.flush()

    if payload.responsaveis_ids:
        for uid in payload.responsaveis_ids:
            db.add(TarefaResponsavel(tarefa_id=tarefa.id, usuario_id=uid))

    if payload.lista_ids:
        for lid in payload.lista_ids:
            db.add(TarefaLista(tarefa_id=tarefa.id, lista_id=lid))

    db.commit()
    db.refresh(tarefa)
    return tarefa


@router.put("/{tarefa_id}", response_model=TarefaResponse)
def atualizar_tarefa(
    tarefa_id: int,
    payload: TarefaUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    tarefa = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tarefa, key, value)
    db.commit()
    db.refresh(tarefa)
    return tarefa


@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_tarefa(tarefa_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    tarefa = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    db.delete(tarefa)
    db.commit()


# --- Checklists ---

@router.post("/{tarefa_id}/checklists", response_model=ChecklistResponse, status_code=status.HTTP_201_CREATED)
def criar_checklist(
    tarefa_id: int,
    payload: ChecklistCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    checklist = Checklist(tarefa_id=tarefa_id, titulo=payload.titulo)
    db.add(checklist)
    db.commit()
    db.refresh(checklist)
    return checklist


@router.post("/checklists/{checklist_id}/itens", response_model=ChecklistItemResponse, status_code=status.HTTP_201_CREATED)
def criar_checklist_item(
    checklist_id: int,
    payload: ChecklistItemCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    item = ChecklistItem(checklist_id=checklist_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# --- Comentários ---

@router.get("/{tarefa_id}/comentarios", response_model=List[ComentarioResponse])
def listar_comentarios(tarefa_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(TarefaComentario).filter(TarefaComentario.tarefa_id == tarefa_id).all()


@router.post("/{tarefa_id}/comentarios", response_model=ComentarioResponse, status_code=status.HTTP_201_CREATED)
def criar_comentario(
    tarefa_id: int,
    payload: ComentarioCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    comentario = TarefaComentario(
        tarefa_id=tarefa_id,
        usuario_id=current_user.id,
        conteudo=payload.conteudo,
    )
    db.add(comentario)
    db.commit()
    db.refresh(comentario)
    return comentario
