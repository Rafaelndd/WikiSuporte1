import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Text, Numeric, Enum
)
from sqlalchemy.orm import relationship
from ..database import Base


class StatusProspeccaoEnum(str, enum.Enum):
    prospectando = "prospectando"
    em_negociacao = "em_negociacao"
    convertido = "convertido"
    perdido = "perdido"


class StatusPedidoEnum(str, enum.Enum):
    rascunho = "rascunho"
    enviado = "enviado"
    aprovado = "aprovado"
    cancelado = "cancelado"


class Cliente(Base):
    """Cliente cadastrado no CRM."""
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    razao_social = Column(String(200), nullable=False)
    nome_fantasia = Column(String(200), nullable=True)
    cnpj = Column(String(20), nullable=True, unique=True, index=True)
    email = Column(String(200), nullable=True)
    telefone = Column(String(30), nullable=True)
    cidade = Column(String(100), nullable=True)
    estado = Column(String(2), nullable=True)
    observacoes = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    prospecções = relationship("Prospeccao", back_populates="cliente", cascade="all, delete-orphan")
    pedidos = relationship("PedidoVenda", back_populates="cliente", cascade="all, delete-orphan")


class Prospeccao(Base):
    """Prospecção de cliente pelo módulo Técnico Consultor."""
    __tablename__ = "prospeccoes"  # ASCII puro, sem acentos

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    status = Column(Enum(StatusProspeccaoEnum), default=StatusProspeccaoEnum.prospectando, nullable=False)
    descricao = Column(Text, nullable=True)
    data_contato = Column(DateTime, nullable=True)
    proximo_contato = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    cliente = relationship("Cliente", back_populates="prospecções")
    analista = relationship("Usuario", back_populates="prospecções")


class Produto(Base):
    """Produto ou serviço disponível para venda."""
    __tablename__ = "produtos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(String(50), nullable=True)  # modulo, treinamento, servico
    preco = Column(Numeric(12, 2), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    pedido_itens = relationship("PedidoItem", back_populates="produto")


class PedidoVenda(Base):
    """Pedido de venda registrado pelo Técnico Consultor."""
    __tablename__ = "pedidos_venda"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    status = Column(Enum(StatusPedidoEnum), default=StatusPedidoEnum.rascunho, nullable=False)
    valor_total = Column(Numeric(12, 2), nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    cliente = relationship("Cliente", back_populates="pedidos")
    analista = relationship("Usuario")
    itens = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan")


class PedidoItem(Base):
    """Item de um pedido de venda."""
    __tablename__ = "pedido_itens"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos_venda.id"), nullable=False, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False, index=True)
    quantidade = Column(Integer, default=1, nullable=False)
    preco_unitario = Column(Numeric(12, 2), nullable=True)
    desconto = Column(Numeric(5, 2), default=0, nullable=True)

    # Relacionamentos
    pedido = relationship("PedidoVenda", back_populates="itens")
    produto = relationship("Produto", back_populates="pedido_itens")
