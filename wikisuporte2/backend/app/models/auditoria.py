from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..database import Base


class Auditoria(Base):
    """Registro de auditoria de ações no sistema."""
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    metodo = Column(String(10), nullable=False)         # GET, POST, PUT, DELETE
    endpoint = Column(String(300), nullable=False)
    status_code = Column(Integer, nullable=True)
    ip_origem = Column(String(50), nullable=True)
    dados_entrada = Column(Text, nullable=True)         # JSON do request body (truncado)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relacionamentos
    usuario = relationship("Usuario", back_populates="auditorias")
