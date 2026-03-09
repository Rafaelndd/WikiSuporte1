from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from ..database import Base


class Setor(Base):
    """Setor hierárquico da organização."""
    __tablename__ = "setores"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False, unique=True)
    descricao = Column(Text, nullable=True)
    setor_pai_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relacionamentos
    setor_pai = relationship("Setor", remote_side=[id], back_populates="sub_setores")
    sub_setores = relationship("Setor", back_populates="setor_pai")
    usuarios = relationship("Usuario", back_populates="setor")


class Role(Base):
    """Papel/função do usuário no sistema."""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(50), nullable=False, unique=True)  # ceo, gestor, analista, viewer
    descricao = Column(Text, nullable=True)
    nivel = Column(Integer, default=0, nullable=False)  # maior = mais permissões
    ativo = Column(Boolean, default=True, nullable=False)

    # Relacionamentos
    usuarios = relationship("Usuario", back_populates="role")
    role_permissoes = relationship("RolePermissao", back_populates="role")


class Usuario(Base):
    """Usuário do sistema."""
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(200), nullable=False, unique=True, index=True)
    senha_hash = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    setor_id = Column(Integer, ForeignKey("setores.id"), nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ultimo_login = Column(DateTime, nullable=True)

    # Relacionamentos
    role = relationship("Role", back_populates="usuarios")
    setor = relationship("Setor", back_populates="usuarios")
    tarefas_responsavel = relationship("TarefaResponsavel", back_populates="usuario")
    atendimentos = relationship("Atendimento", back_populates="analista")
    prospecções = relationship("Prospeccao", back_populates="analista")
    auditorias = relationship("Auditoria", back_populates="usuario")


class Permissao(Base):
    """Permissão granular do sistema."""
    __tablename__ = "permissoes"

    id = Column(Integer, primary_key=True, index=True)
    modulo = Column(String(100), nullable=False)  # tarefas, crm, suporte, dashboards
    acao = Column(String(50), nullable=False)     # ler, criar, editar, deletar
    descricao = Column(Text, nullable=True)

    # Relacionamentos
    role_permissoes = relationship("RolePermissao", back_populates="permissao")


class RolePermissao(Base):
    """Tabela de associação entre Role e Permissao."""
    __tablename__ = "role_permissoes"

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False, index=True)
    permissao_id = Column(Integer, ForeignKey("permissoes.id"), nullable=False, index=True)

    # Relacionamentos
    role = relationship("Role", back_populates="role_permissoes")
    permissao = relationship("Permissao", back_populates="role_permissoes")
