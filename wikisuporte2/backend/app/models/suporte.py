import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Text, Numeric, Enum
)
from sqlalchemy.orm import relationship
from ..database import Base


class TipoAtendimentoEnum(str, enum.Enum):
    telefone = "telefone"
    email = "email"
    chat = "chat"
    presencial = "presencial"


class StatusChamadoEnum(str, enum.Enum):
    aberto = "aberto"
    em_andamento = "em_andamento"
    aguardando_cliente = "aguardando_cliente"
    resolvido = "resolvido"
    fechado = "fechado"


class Atendimento(Base):
    """Registro de atendimento realizado por um analista."""
    __tablename__ = "atendimentos"

    id = Column(Integer, primary_key=True, index=True)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    cliente_nome = Column(String(200), nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True, index=True)
    tipo = Column(Enum(TipoAtendimentoEnum), default=TipoAtendimentoEnum.telefone, nullable=False)
    duracao_minutos = Column(Integer, nullable=True)
    descricao = Column(Text, nullable=True)
    resolucao = Column(Text, nullable=True)
    data_atendimento = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    importado = Column(Boolean, default=False, nullable=False)  # True se veio de CSV/API
    fonte = Column(String(50), nullable=True)  # multi360, goto, manual
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    analista = relationship("Usuario", back_populates="atendimentos")
    cliente = relationship("Cliente")


class Chamado(Base):
    """Chamado técnico de suporte."""
    __tablename__ = "chamados"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(300), nullable=False)
    descricao = Column(Text, nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True, index=True)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    status = Column(Enum(StatusChamadoEnum), default=StatusChamadoEnum.aberto, nullable=False)
    prioridade = Column(String(20), default="normal", nullable=False)
    categoria = Column(String(100), nullable=True)
    data_abertura = Column(DateTime, default=datetime.utcnow, nullable=False)
    data_fechamento = Column(DateTime, nullable=True)
    sla_horas = Column(Integer, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    cliente = relationship("Cliente")
    analista = relationship("Usuario")


class Plantao(Base):
    """Registro de plantão de suporte."""
    __tablename__ = "plantoes"

    id = Column(Integer, primary_key=True, index=True)
    analista_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    data_inicio = Column(DateTime, nullable=False)
    data_fim = Column(DateTime, nullable=True)
    tipo = Column(String(50), nullable=True)  # diurno, noturno, fim_de_semana
    observacoes = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    analista = relationship("Usuario")


class Importacao(Base):
    """Registro de importação de dados (CSV, API GoTo, Multi360, etc.)."""
    __tablename__ = "importacoes"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    tipo = Column(String(50), nullable=False)  # multi360_csv, goto_api, chamados_bot
    nome_arquivo = Column(String(255), nullable=True)
    status = Column(String(30), default="pendente", nullable=False)  # pendente, processando, concluido, erro
    total_registros = Column(Integer, default=0, nullable=True)
    registros_importados = Column(Integer, default=0, nullable=True)
    registros_erro = Column(Integer, default=0, nullable=True)
    log_erros = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    concluido_em = Column(DateTime, nullable=True)

    # Relacionamentos
    usuario = relationship("Usuario")
