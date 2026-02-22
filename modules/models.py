import os
import sys
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


Base = declarative_base()

# Adicione isso ao final do seu models.py

class AtendimentoMulti360(Base):
    __tablename__ = "atendimentos_multi360"

    protocolo = Column(BigInteger, primary_key=True, index=True) # Impede duplicação de atendimentos
    origem = Column(String(50), nullable=True)
    status = Column(String(50), nullable=True)
    atendente = Column(String(100), nullable=True)
    departamento = Column(String(100), nullable=True)
    nome_contato = Column(String(200), nullable=True)
    numero_telefone = Column(String(50), nullable=True)
    data_inicio = Column(DateTime, nullable=False, index=True) # Indexado para buscas rápidas por mês
    data_finalizacao = Column(DateTime, nullable=True)
    avaliacao = Column(Integer, nullable=True) # Nota de 1 a 10
    
    data_importacao = Column(DateTime, default=datetime.now) # Auditoria de quando o arquivo subiu

class AtendimentoGoTo(Base):
    __tablename__ = "atendimentos_goto"

    id_conversa = Column(String(100), primary_key=True, index=True) # 'Conversation space id'
    data_chamada = Column(DateTime, nullable=False, index=True)
    duracao_ms = Column(BigInteger, nullable=True) # Em milissegundos, fácil de somar e tirar média
    direcao = Column(String(50), nullable=True) # 'Recebida', 'Realizada'
    resultado = Column(String(100), nullable=True)
    telefone_origem = Column(String(100), nullable=True)
    participantes = Column(Text, nullable=True)
    gravado = Column(String(10), nullable=True)
    
    data_importacao = Column(DateTime, default=datetime.now)

class ChamadoTecnuv(Base):
    __tablename__ = "chamados_tecnuv"

    id = Column(BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, unique=True, nullable=False, index=True)
    cliente_nome = Column(Text, nullable=True)
    atendente_tecnuv = Column(Text, nullable=True)
    usuario_epsy = Column(Text, nullable=True)
    status_atual = Column(Text, nullable=True)
    ticket_vinculado = Column(Text, nullable=True)
    setor = Column(Text, nullable=True)
    situacao = Column(Text, nullable=True)
    prioridade = Column(Text, nullable=True)
    assunto_html = Column(Text, nullable=True)
    motivo_abertura_html = Column(Text, nullable=True)
    data_abertura = Column(DateTime, nullable=True)
    
    ultima_alteracao_tecnuv = Column(DateTime, nullable=True)
    ultima_verificacao_robo = Column(DateTime, default=datetime.now)

    transicoes = relationship("HistoricoTransicaoStatus", back_populates="chamado", cascade="all, delete-orphan")
    interacoes = relationship("HistoricoInteracao", back_populates="chamado", cascade="all, delete-orphan")


class HistoricoTransicaoStatus(Base):
    __tablename__ = "historico_transicoes_status"

    id_transicao = Column(BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"))
    status_anterior = Column(Text, nullable=True)
    status_novo = Column(Text, nullable=False)
    data_deteccao = Column(DateTime, default=datetime.now)

    chamado = relationship("ChamadoTecnuv", back_populates="transicoes")


class HistoricoInteracao(Base):
    __tablename__ = "historico_interacoes"

    id = Column(BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"))
    usuario = Column(Text, nullable=False)
    data_interacao = Column(DateTime, nullable=False)
    descricao_html = Column(Text, nullable=True)

    chamado = relationship("ChamadoTecnuv", back_populates="interacoes")

    __table_args__ = (
        UniqueConstraint('nr_chamado', 'data_interacao', 'usuario', name='uix_chamado_msg_autor'),
    )

def inicializar_banco():

    print("Conectando ao PostgreSQL para validar o schema...")
    try:
        engine = get_connection()
        Base.metadata.create_all(bind=engine)
        print("Schema V4.0 validado.")
    except Exception as e:
        print(f"Falha crítica ao inicializar as tabelas: {e}")
        sys.exit(1)





# (Supondo que você já tenha a tabela de usuarios)
class UsuarioDashboard(Base):
    __tablename__ = 'usuarios_dashboard'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    perfil = Column(Integer, nullable=False) # 1-Analista, 2-Coord, 3-Admin
    # ... outros campos ...

# NOVA TABELA PARA ADEQUAÇÃO À LGPD
class LogAuditoria(Base):
    """
    Tabela responsável por registrar acessos, aceites de termos e ações críticas,
    garantindo a rastreabilidade exigida pela LGPD.
    """
    __tablename__ = 'logs_auditoria_sistema'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey('usuarios_dashboard.id'), nullable=False)
    acao = Column(String(100), nullable=False) # Ex: "LOGIN", "ACEITE_TERMOS", "ACESSO_ABA_CSV"
    detalhes = Column(Text, nullable=True)     # Informações extras (ex: IP, qual relatório exportou)
    data_hora = Column(DateTime, default=datetime.now)

if __name__ == "__main__":
    inicializar_banco()