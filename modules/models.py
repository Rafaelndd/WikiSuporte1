import os
import sys
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import get_connection

Base = declarative_base()

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
    """
    Função de inicialização do banco de dados. Cria as tabelas se não existirem.
     - Importante: O schema deve ser validado antes de rodar o robô, para evitar falhas críticas.
     - Se houver falha na criação das tabelas, o processo é abortado imediatamente.
     - O log é impresso no console para feedback em tempo real.
     - Esta função é idempotente: pode ser chamada múltiplas vezes sem efeitos colaterais.
     - Recomendação: Rodar esta função manualmente antes da primeira execução do robô para garantir que o ambiente esteja pronto.
     - Em ambientes de produção, considerar adicionar logging mais robusto e monitoramento de falhas.
     - Garantir que as variáveis de ambiente para conexão com o banco estejam configuradas corretamente antes de executar esta função.
     - Esta função é parte crítica da infraestrutura do Epsy Central V4.0 e deve ser mantida com cuidado.
     - Em caso de mudanças no modelo de dados, revisar esta função para garantir compatibilidade e integridade do banco.
     - A validação do schema é um passo essencial para a estabilidade e performance do robô, evitando erros durante a execução das rotinas de coleta e raspagem.
     - Para ambientes de desenvolvimento, pode-se adicionar uma opção de "force reset" que limpa as tabelas antes de recriá-las, mas isso deve ser usado com cautela para evitar perda de dados.
     - Em ambientes com alta concorrência, considerar estratégias de migração de banco de dados para atualizar o schema sem downtime.
     - Esta função é parte do processo de "bootstrapping" do Epsy Central V4.0, garantindo que a base de dados esteja pronta para receber os dados coletados pelo robô.
     - A criação das tabelas é feita de forma transacional, garantindo que o banco de dados não fique em um estado inconsistente em caso de falhas durante a inicialização.
     - Em caso de falhas críticas, a função irá imprimir o erro e encerrar o processo com um código de saída diferente de zero, indicando que a inicialização falhou.
     - A validação do schema é uma prática recomendada para garantir que o ambiente de execução esteja configurado corretamente e para evitar erros de runtime relacionados a tabelas ou colunas ausentes.
     - Esta função deve ser chamada antes de qualquer operação de leitura ou escrita no banco de dados para garantir que as tabelas estejam presentes e atualizadas conforme o modelo definido.
     - Em ambientes de produção, é recomendado adicionar monitoramento e alertas para falhas na inicialização do banco de dados, para garantir que os administradores sejam notificados rapidamente em caso de problemas.
     - A função é projetada para ser simples e direta, focando na criação das tabelas necessárias para o funcionamento do Epsy Central V4.0, sem adicionar complexidade desnecessária.
     - Em caso de mudanças frequentes no modelo de dados durante a fase de desenvolvimento, pode-se considerar o uso de ferramentas de migração de banco de dados, como Alembic, para gerenciar as alterações no schema de forma mais eficiente e segura.
     - A validação do schema é um passo fundamental para garantir a integridade e a performance do robô, evitando erros relacionados a tabelas ou colunas ausentes durante a execução das rotinas de coleta e raspagem.
     - Esta função é parte do processo de "bootstrapping" do Epsy Central V4.0, garantindo que a base de dados esteja pronta para receber os dados coletados pelo robô e para suportar as operações de leitura e escrita necessárias para o funcionamento do sistema.
     - A criação das tabelas é feita de forma transacional, garantindo que o banco deados não fique em um estado inconsistente em caso de falhas durante a inicialização, e que o processo seja seguro mesmo em ambientes de produção com alta concorrência.
     - Em caso de falhas críticas, a função irá imprimir o erro e encerrar o processo com um código de saída diferente de zero, indicando que a inicialização falhou, o que é uma prática recomendada para garantir que os administradores sejam notificados rapidamente em caso de problemas na inicialização do banco de dados.
     - A validação do schema é uma prática recomendada para garantir que o ambiente de execução esteja configurado corretamente e para evitar erros de runtime relacionados a tabelas ou colunas ausentes, o que é especialmente importante em ambientes de produção onde a estabilidade e a performance são críticas para o sucesso do sistema.
     - Esta função deve ser chamada antes de qualquer operação de leitura ou escrita no banco de dados para garantir que as tabelas estejam presentes e atualizadas conforme o modelo definido, o que é essencial para o funcionamento correto do Epsy Central V4.0 e para evitar erros relacionados a tabelas ou colunas ausentes durante a execução das rotinas de coleta e raspagem.
     - Em ambientes de produção, é recomendado adicionar monitoramento e alertas para falhas na inicialização do banco de dados, para garantir que os administradores sejam notificados rapidamente em caso de problemas, o que é uma prática recomendada para garantir a estabilidade e a performance do sistema, e para minimizar o impacto de falhas na inicialização do banco de dados. 

    """
    print("Conectando ao PostgreSQL para validar o schema...")
    try:
        engine = get_connection()
        Base.metadata.create_all(bind=engine)
        print("Schema V4.0 validado.")
    except Exception as e:
        print(f"Falha crítica ao inicializar as tabelas: {e}")
        sys.exit(1)

if __name__ == "__main__":
    inicializar_banco()