from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from ..dependencies import get_db, get_current_user
from ..models.usuario import Usuario
from ..models.suporte import Atendimento, Chamado, Plantao
from ..models.crm import Prospeccao, PedidoVenda
from ..models.tarefa import Tarefa
from ..services.rbac import filtrar_por_permissao

router = APIRouter()


@router.get("/resumo")
def resumo_geral(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna KPIs gerais do sistema com filtro por role."""
    # Atendimentos
    q_atend = db.query(func.count(Atendimento.id))
    q_atend = filtrar_por_permissao(
        db.query(Atendimento), current_user, campo_usuario_id=Atendimento.analista_id
    )
    total_atendimentos = q_atend.count()

    # Chamados abertos
    q_chamados = filtrar_por_permissao(
        db.query(Chamado), current_user, campo_usuario_id=Chamado.analista_id
    )
    chamados_abertos = q_chamados.filter(Chamado.status == "aberto").count()

    # Tarefas pendentes
    q_tarefas = db.query(Tarefa).filter(Tarefa.concluida == False)
    total_tarefas_pendentes = q_tarefas.count()

    # Prospecções ativas
    q_prosp = filtrar_por_permissao(
        db.query(Prospeccao), current_user, campo_usuario_id=Prospeccao.analista_id
    )
    total_prospecções = q_prosp.filter(Prospeccao.status == "prospectando").count()

    return {
        "total_atendimentos": total_atendimentos,
        "chamados_abertos": chamados_abertos,
        "tarefas_pendentes": total_tarefas_pendentes,
        "prospecções_ativas": total_prospecções,
    }


@router.get("/atendimentos-por-analista")
def atendimentos_por_analista(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna quantidade de atendimentos agrupados por analista."""
    q = db.query(
        Usuario.id,
        Usuario.nome,
        func.count(Atendimento.id).label("total"),
    ).join(Atendimento, Atendimento.analista_id == Usuario.id, isouter=True)

    role_nome = current_user.role.nome.lower() if current_user.role else ""
    if role_nome not in ("ceo", "admin", "gestor"):
        q = q.filter(Usuario.id == current_user.id)
    elif role_nome == "gestor" and current_user.setor_id:
        q = q.filter(Usuario.setor_id == current_user.setor_id)

    q = q.group_by(Usuario.id, Usuario.nome).order_by(func.count(Atendimento.id).desc())
    rows = q.all()
    return [{"analista_id": r.id, "nome": r.nome, "total": r.total} for r in rows]


@router.get("/chamados-por-status")
def chamados_por_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna quantidade de chamados agrupados por status."""
    q = db.query(
        Chamado.status,
        func.count(Chamado.id).label("total"),
    )
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Chamado.analista_id)
    q = q.group_by(Chamado.status)
    rows = q.all()
    return [{"status": r.status, "total": r.total} for r in rows]


@router.get("/prospecções-por-status")
def prospecções_por_status(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Retorna funil de prospecções por status."""
    q = db.query(
        Prospeccao.status,
        func.count(Prospeccao.id).label("total"),
    )
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Prospeccao.analista_id)
    q = q.group_by(Prospeccao.status)
    rows = q.all()
    return [{"status": r.status, "total": r.total} for r in rows]


@router.get("/tarefas-por-prioridade")
def tarefas_por_prioridade(
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Retorna tarefas pendentes agrupadas por prioridade."""
    q = db.query(
        Tarefa.prioridade,
        func.count(Tarefa.id).label("total"),
    ).filter(Tarefa.concluida == False).group_by(Tarefa.prioridade)
    rows = q.all()
    return [{"prioridade": r.prioridade, "total": r.total} for r in rows]
