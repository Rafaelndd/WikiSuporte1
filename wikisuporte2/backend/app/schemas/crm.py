from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel
from ..models.crm import StatusProspeccaoEnum, StatusPedidoEnum


# --- Cliente ---
class ClienteBase(BaseModel):
    razao_social: str
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: bool = True


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    observacoes: Optional[str] = None
    ativo: Optional[bool] = None


class ClienteResponse(ClienteBase):
    id: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Prospecção ---
class ProspeccaoCreate(BaseModel):
    cliente_id: int
    status: StatusProspeccaoEnum = StatusProspeccaoEnum.prospectando
    descricao: Optional[str] = None
    data_contato: Optional[datetime] = None
    proximo_contato: Optional[datetime] = None


class ProspeccaoUpdate(BaseModel):
    status: Optional[StatusProspeccaoEnum] = None
    descricao: Optional[str] = None
    data_contato: Optional[datetime] = None
    proximo_contato: Optional[datetime] = None


class ProspeccaoResponse(ProspeccaoCreate):
    id: int
    analista_id: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Produto ---
class ProdutoCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    preco: Optional[Decimal] = None
    ativo: bool = True


class ProdutoResponse(ProdutoCreate):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


# --- Pedido Item ---
class PedidoItemCreate(BaseModel):
    produto_id: int
    quantidade: int = 1
    preco_unitario: Optional[Decimal] = None
    desconto: Optional[Decimal] = None


class PedidoItemResponse(PedidoItemCreate):
    id: int

    model_config = {"from_attributes": True}


# --- Pedido de Venda ---
class PedidoVendaCreate(BaseModel):
    cliente_id: int
    status: StatusPedidoEnum = StatusPedidoEnum.rascunho
    observacoes: Optional[str] = None
    itens: List[PedidoItemCreate] = []


class PedidoVendaUpdate(BaseModel):
    status: Optional[StatusPedidoEnum] = None
    observacoes: Optional[str] = None


class PedidoVendaResponse(BaseModel):
    id: int
    cliente_id: int
    analista_id: int
    status: StatusPedidoEnum
    valor_total: Optional[Decimal] = None
    observacoes: Optional[str] = None
    itens: List[PedidoItemResponse] = []
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    model_config = {"from_attributes": True}
