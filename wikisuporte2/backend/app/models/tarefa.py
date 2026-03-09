import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Text, Enum, Float, Table
)
from sqlalchemy.orm import relationship
from ..database import Base


class PrioridadeEnum(str, enum.Enum):
    urgente = "urgente"
    alta = "alta"
    normal = "normal"
    baixa = "baixa"


class Espaco(Base):
    """Espaço de trabalho (nível mais alto da hierarquia)."""
    __tablename__ = "espacos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    descricao = Column(Text, nullable=True)
    cor = Column(String(10), nullable=True)
    icone = Column(String(50), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    pastas = relationship("Pasta", back_populates="espaco", cascade="all, delete-orphan")
    status_config = relationship("StatusConfig", back_populates="espaco", cascade="all, delete-orphan")


class Pasta(Base):
    """Pasta dentro de um Espaço."""
    __tablename__ = "pastas"

    id = Column(Integer, primary_key=True, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos.id"), nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    espaco = relationship("Espaco", back_populates="pastas")
    listas = relationship("Lista", back_populates="pasta", cascade="all, delete-orphan")


class Lista(Base):
    """Lista dentro de uma Pasta."""
    __tablename__ = "listas"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas.id"), nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    descricao = Column(Text, nullable=True)
    cor = Column(String(10), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    pasta = relationship("Pasta", back_populates="listas")
    tarefa_listas = relationship("TarefaLista", back_populates="lista")


class StatusConfig(Base):
    """Configuração de status para um Espaço (colunas do Kanban)."""
    __tablename__ = "status_config"

    id = Column(Integer, primary_key=True, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos.id"), nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    cor = Column(String(10), nullable=True)
    ordem = Column(Integer, default=0, nullable=False)
    tipo = Column(String(50), default="personalizado")  # nao_iniciado, ativo, concluido, cancelado

    # Relacionamentos
    espaco = relationship("Espaco", back_populates="status_config")
    tarefas = relationship("Tarefa", back_populates="status")


class Tarefa(Base):
    """Tarefa — bloco fundamental do gerenciamento de tarefas."""
    __tablename__ = "tarefas"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(300), nullable=False)
    descricao = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey("status_config.id"), nullable=True, index=True)
    prioridade = Column(Enum(PrioridadeEnum), default=PrioridadeEnum.normal, nullable=False)
    data_inicio = Column(DateTime, nullable=True)
    data_vencimento = Column(DateTime, nullable=True)
    concluida = Column(Boolean, default=False, nullable=False)
    tarefa_pai_id = Column(Integer, ForeignKey("tarefas.id"), nullable=True, index=True)  # subtarefa
    recorrente = Column(Boolean, default=False, nullable=False)
    intervalo_recorrencia = Column(String(50), nullable=True)  # diaria, semanal, mensal
    criado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    status = relationship("StatusConfig", back_populates="tarefas")
    criado_por = relationship("Usuario", foreign_keys=[criado_por_id])
    subtarefas = relationship("Tarefa", back_populates="tarefa_pai", foreign_keys=[tarefa_pai_id])
    tarefa_pai = relationship("Tarefa", back_populates="subtarefas", remote_side=[id], foreign_keys=[tarefa_pai_id])
    responsaveis = relationship("TarefaResponsavel", back_populates="tarefa", cascade="all, delete-orphan")
    tarefa_listas = relationship("TarefaLista", back_populates="tarefa", cascade="all, delete-orphan")
    dependencias = relationship("TarefaDependencia", back_populates="tarefa", foreign_keys="TarefaDependencia.tarefa_id", cascade="all, delete-orphan")
    checklists = relationship("Checklist", back_populates="tarefa", cascade="all, delete-orphan")
    comentarios = relationship("TarefaComentario", back_populates="tarefa", cascade="all, delete-orphan")


class TarefaResponsavel(Base):
    """Responsáveis por uma tarefa (muitos para muitos)."""
    __tablename__ = "tarefa_responsaveis"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)

    # Relacionamentos
    tarefa = relationship("Tarefa", back_populates="responsaveis")
    usuario = relationship("Usuario", back_populates="tarefas_responsavel")


class TarefaLista(Base):
    """Tarefa em múltiplas listas (sem duplicar a tarefa)."""
    __tablename__ = "tarefa_listas"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)
    lista_id = Column(Integer, ForeignKey("listas.id"), nullable=False, index=True)

    # Relacionamentos
    tarefa = relationship("Tarefa", back_populates="tarefa_listas")
    lista = relationship("Lista", back_populates="tarefa_listas")


class TarefaDependencia(Base):
    """Dependência entre tarefas."""
    __tablename__ = "tarefa_dependencias"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)
    depende_de_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)

    # Relacionamentos
    tarefa = relationship("Tarefa", back_populates="dependencias", foreign_keys=[tarefa_id])
    depende_de = relationship("Tarefa", foreign_keys=[depende_de_id])


class Checklist(Base):
    """Checklist dentro de uma tarefa."""
    __tablename__ = "checklists"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    tarefa = relationship("Tarefa", back_populates="checklists")
    itens = relationship("ChecklistItem", back_populates="checklist", cascade="all, delete-orphan")


class ChecklistItem(Base):
    """Item de um checklist."""
    __tablename__ = "checklist_itens"

    id = Column(Integer, primary_key=True, index=True)
    checklist_id = Column(Integer, ForeignKey("checklists.id"), nullable=False, index=True)
    descricao = Column(String(300), nullable=False)
    concluido = Column(Boolean, default=False, nullable=False)
    ordem = Column(Integer, default=0, nullable=False)

    # Relacionamentos
    checklist = relationship("Checklist", back_populates="itens")


class TarefaComentario(Base):
    """Comentário em uma tarefa."""
    __tablename__ = "tarefa_comentarios"

    id = Column(Integer, primary_key=True, index=True)
    tarefa_id = Column(Integer, ForeignKey("tarefas.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    conteudo = Column(Text, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    tarefa = relationship("Tarefa", back_populates="comentarios")
    usuario = relationship("Usuario")


class Automacao(Base):
    """Automação configurável para tarefas."""
    __tablename__ = "automacoes"

    id = Column(Integer, primary_key=True, index=True)
    espaco_id = Column(Integer, ForeignKey("espacos.id"), nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    gatilho = Column(String(100), nullable=False)   # ex: status_mudou
    condicao = Column(Text, nullable=True)           # JSON com condições
    acao = Column(Text, nullable=False)              # JSON com ações
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    espaco = relationship("Espaco")
