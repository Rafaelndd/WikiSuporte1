from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from ..models.tarefa import PrioridadeEnum


# --- Espaço ---
class EspacoCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    cor: Optional[str] = None
    icone: Optional[str] = None
    ativo: bool = True


class EspacoResponse(EspacoCreate):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Pasta ---
class PastaCreate(BaseModel):
    espaco_id: int
    nome: str
    descricao: Optional[str] = None
    ativo: bool = True


class PastaResponse(PastaCreate):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Lista ---
class ListaCreate(BaseModel):
    pasta_id: int
    nome: str
    descricao: Optional[str] = None
    cor: Optional[str] = None
    ativo: bool = True


class ListaResponse(ListaCreate):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- StatusConfig ---
class StatusConfigCreate(BaseModel):
    espaco_id: int
    nome: str
    cor: Optional[str] = None
    ordem: int = 0
    tipo: str = "personalizado"


class StatusConfigResponse(StatusConfigCreate):
    id: int

    model_config = {"from_attributes": True}


# --- Checklist ---
class ChecklistItemCreate(BaseModel):
    descricao: str
    concluido: bool = False
    ordem: int = 0


class ChecklistItemResponse(ChecklistItemCreate):
    id: int

    model_config = {"from_attributes": True}


class ChecklistCreate(BaseModel):
    tarefa_id: int
    titulo: str


class ChecklistResponse(ChecklistCreate):
    id: int
    itens: List[ChecklistItemResponse] = []
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Tarefa ---
class TarefaCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    status_id: Optional[int] = None
    prioridade: PrioridadeEnum = PrioridadeEnum.normal
    data_inicio: Optional[datetime] = None
    data_vencimento: Optional[datetime] = None
    tarefa_pai_id: Optional[int] = None
    recorrente: bool = False
    intervalo_recorrencia: Optional[str] = None
    responsaveis_ids: Optional[List[int]] = None
    lista_ids: Optional[List[int]] = None


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    status_id: Optional[int] = None
    prioridade: Optional[PrioridadeEnum] = None
    data_inicio: Optional[datetime] = None
    data_vencimento: Optional[datetime] = None
    concluida: Optional[bool] = None
    recorrente: Optional[bool] = None
    intervalo_recorrencia: Optional[str] = None


class TarefaResponse(BaseModel):
    id: int
    titulo: str
    descricao: Optional[str] = None
    status_id: Optional[int] = None
    prioridade: PrioridadeEnum
    data_inicio: Optional[datetime] = None
    data_vencimento: Optional[datetime] = None
    concluida: bool
    tarefa_pai_id: Optional[int] = None
    recorrente: bool
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Comentário ---
class ComentarioCreate(BaseModel):
    tarefa_id: int
    conteudo: str


class ComentarioResponse(ComentarioCreate):
    id: int
    usuario_id: int
    criado_em: datetime

    model_config = {"from_attributes": True}
