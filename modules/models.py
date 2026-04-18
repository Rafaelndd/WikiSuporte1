import os
import sys
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Date, Integer, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

# 1. Ajuste de Caminho: Garante que o Python encontre os módulos vizinhos
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 2. Importação correta (Verifique se o arquivo database.py está na mesma pasta)
try:
    from modules.database import get_connection as get_engine
except ImportError:
    # Caso o script seja rodado da raiz, tenta a importação absoluta
    from modules.database import get_engine

Base = declarative_base()

# ==========================================
# MODELOS DO HELP DESK (TECNUV)
# ==========================================

class ChamadoTecnuv(Base):
    __tablename__ = "chamados_tecnuv"

    id = Column(BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, unique=True, nullable=False, index=True)
    # Coluna real no banco atual: nome_cliente.
    # Mantemos o atributo Python como nome_cliente para consistência do código.
    nome_cliente = Column(Text, nullable=True)
    atendente_tecnuv = Column(Text, nullable=True)
    usuario_epsy = Column(Text, nullable=True)
    status_atual = Column(Text, nullable=True)
    ticket_vinculado = Column(Text, nullable=True)
    setor = Column(Text, nullable=True)
    situacao = Column(Text, nullable=True)
    prioridade = Column(Text, nullable=True)
    assunto_html = Column(Text, nullable=True)
    motivo_abertura_html = Column(Text, nullable=True)
    versao_sistema = Column(String(50), nullable=True)
    data_abertura = Column(DateTime, nullable=True)
    data_encerramento = Column(DateTime, nullable=True)
    data_cancelamento = Column(DateTime, nullable=True)
    usuario_cancelamento = Column(String(100), nullable=True)
    usuario_encerramento = Column(String(100), nullable=True)
    assunto_encerramento = Column(Text, nullable=True)
    previsao_conclusao = Column(Date, nullable=True)
    ultima_alteracao_tecnuv = Column(DateTime, nullable=True)
    ultima_verificacao_robo = Column(DateTime, default=datetime.now)
    atualizado_em = Column(DateTime, default=datetime.now)
    # RELACIONAMENTOS (Atualizados para incluir Cobranças e Clientes Vinculados)
    transicoes = relationship("HistoricoTransicaoStatus", back_populates="chamado", cascade="all, delete-orphan")
    interacoes = relationship("HistoricoInteracao", back_populates="chamado", cascade="all, delete-orphan")
    cobrancas = relationship("CobrancaChamado", back_populates="chamado", cascade="all, delete-orphan")
    clientes_vinculados = relationship("ClienteVinculadoChamado", back_populates="chamado", cascade="all, delete-orphan")


class HistoricoTransicaoStatus(Base):
    # DB usa nome no singular (historico_transicao_status).
    __tablename__ = "historico_transicao_status"

    # Mantemos atributo id_transicao, mapeando para coluna real id.
    id_transicao = Column("id", BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"))
    status_anterior = Column(Text, nullable=True)
    status_novo = Column(Text, nullable=False)
    # Mantemos atributo data_deteccao, mapeando para coluna real data_mudanca.
    data_deteccao = Column("data_mudanca", DateTime, default=datetime.now)

    chamado = relationship("ChamadoTecnuv", back_populates="transicoes")


class HistoricoInteracao(Base):
    __tablename__ = "historico_interacoes"

    # DB usa id_interacao; mantemos atributo id.
    id = Column("id_interacao", BigInteger, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"))
    usuario = Column(Text, nullable=False)
    data_interacao = Column(DateTime, nullable=False)
    # DB usa descricao_texto; mantemos atributo descricao_html para compatibilidade.
    descricao_html = Column("descricao_texto", Text, nullable=True)

    chamado = relationship("ChamadoTecnuv", back_populates="interacoes")

    __table_args__ = (
        UniqueConstraint('nr_chamado', 'data_interacao', 'usuario', name='uix_chamado_msg_autor'),
    )


# ==========================================
# NOVOS MODELOS: EXTRAS DO CHAMADO (VÍNCULOS E COBRANÇAS)
# ==========================================

class ClienteVinculadoChamado(Base):
    __tablename__ = "clientes_vinculados_chamado"

    id = Column(Integer, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"), nullable=False)
    nome_cliente = Column(String(255), nullable=False)
    cnpj_cliente = Column(String(25), nullable=True)
    criado_em = Column(DateTime, default=datetime.now)

    chamado = relationship("ChamadoTecnuv", back_populates="clientes_vinculados")


class CobrancaChamado(Base):
    __tablename__ = "cobrancas_chamados"

    id = Column(Integer, primary_key=True, index=True)
    nr_chamado = Column(BigInteger, ForeignKey("chamados_tecnuv.nr_chamado", ondelete="CASCADE"), nullable=False)
    data_cobranca = Column(DateTime, nullable=True)
    analista_epsy = Column(String(100), nullable=True)
    cliente_solicitante = Column(String(255), nullable=True)
    texto_bruto_cobranca = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.now)

    chamado = relationship("ChamadoTecnuv", back_populates="cobrancas")


# ==========================================
# MODELOS DE SEGURANÇA E AUDITORIA (LGPD)
# ==========================================

class UsuarioDashboard(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True)
    nome = Column(String(100), nullable=False)
    perfil = Column(Integer, nullable=False) # 1-Analista, 2-Coord, 3-Admin
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    ativo = Column(Integer, default=1) # 1 para Ativo, 0 para Inativo

class LogAuditoria(Base):
    __tablename__ = 'logs_auditoria_sistema'
    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=False)
    acao = Column(String(100), nullable=False)
    detalhes = Column(Text, nullable=True)
    data_hora = Column(DateTime, default=datetime.now)

# ==========================================
# INICIALIZAÇÃO
# ==========================================

def inicializar_banco():
    print("O PSY está inicializando o banco de dados... Verificando conexões e analisado o ambiente.")
    try:
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        print("O PSY concluiu a inicialização do banco de dados com sucesso! O ambiente está pronto para uso.")
    except Exception as e:
        print(f"O PSY encontrou um erro durante a inicialização do banco de dados:{e}")
        sys.exit(1)

if __name__ == "__main__":
    inicializar_banco()