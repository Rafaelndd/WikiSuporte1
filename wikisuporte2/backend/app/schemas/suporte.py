from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from ..models.suporte import TipoAtendimentoEnum, StatusChamadoEnum


# --- Atendimento ---
class AtendimentoCreate(BaseModel):
    cliente_nome: Optional[str] = None
    cliente_id: Optional[int] = None
    tipo: TipoAtendimentoEnum = TipoAtendimentoEnum.telefone
    duracao_minutos: Optional[int] = None
    descricao: Optional[str] = None
    resolucao: Optional[str] = None
    data_atendimento: Optional[datetime] = None
    fonte: Optional[str] = None


class AtendimentoResponse(AtendimentoCreate):
    id: int
    analista_id: int
    importado: bool
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Chamado ---
class ChamadoCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    cliente_id: Optional[int] = None
    prioridade: str = "normal"
    categoria: Optional[str] = None
    sla_horas: Optional[int] = None


class ChamadoUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    analista_id: Optional[int] = None
    status: Optional[StatusChamadoEnum] = None
    prioridade: Optional[str] = None
    categoria: Optional[str] = None
    data_fechamento: Optional[datetime] = None


class ChamadoResponse(BaseModel):
    id: int
    titulo: str
    descricao: Optional[str] = None
    cliente_id: Optional[int] = None
    analista_id: Optional[int] = None
    status: StatusChamadoEnum
    prioridade: str
    categoria: Optional[str] = None
    data_abertura: datetime
    data_fechamento: Optional[datetime] = None
    sla_horas: Optional[int] = None
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Plantão ---
class PlantaoCreate(BaseModel):
    data_inicio: datetime
    data_fim: Optional[datetime] = None
    tipo: Optional[str] = None
    observacoes: Optional[str] = None


class PlantaoResponse(PlantaoCreate):
    id: int
    analista_id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Importação ---
class ImportacaoCreate(BaseModel):
    tipo: str
    nome_arquivo: Optional[str] = None


class ImportacaoResponse(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    tipo: str
    nome_arquivo: Optional[str] = None
    status: str
    total_registros: Optional[int] = None
    registros_importados: Optional[int] = None
    registros_erro: Optional[int] = None
    log_erros: Optional[str] = None
    criado_em: datetime
    concluido_em: Optional[datetime] = None

    model_config = {"from_attributes": True}
