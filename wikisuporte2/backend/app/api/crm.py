from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from ..dependencies import get_db, get_current_user
from ..models.usuario import Usuario
from ..models.crm import Cliente, Prospeccao, PedidoVenda, PedidoItem, Produto
from ..schemas.crm import (
    ClienteCreate, ClienteUpdate, ClienteResponse,
    ProspeccaoCreate, ProspeccaoUpdate, ProspeccaoResponse,
    PedidoVendaCreate, PedidoVendaUpdate, PedidoVendaResponse,
    ProdutoCreate, ProdutoResponse,
)
from ..services.rbac import filtrar_por_permissao

router = APIRouter()


# --- Clientes ---

@router.get("/clientes", response_model=List[ClienteResponse])
def listar_clientes(
    busca: Optional[str] = Query(None, description="Buscar por nome ou CNPJ"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Cliente).filter(Cliente.ativo == True)
    if busca:
        q = q.filter(
            Cliente.razao_social.ilike(f"%{busca}%") |
            Cliente.cnpj.ilike(f"%{busca}%") |
            Cliente.nome_fantasia.ilike(f"%{busca}%")
        )
    return q.order_by(Cliente.razao_social).all()


@router.get("/clientes/{cliente_id}", response_model=ClienteResponse)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


@router.post("/clientes", response_model=ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(
    payload: ClienteCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    # Verificação de duplicidade por CNPJ
    if payload.cnpj:
        existente = db.query(Cliente).filter(Cliente.cnpj == payload.cnpj).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cliente com CNPJ {payload.cnpj} já cadastrado (ID: {existente.id})",
            )
    cliente = Cliente(**payload.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.put("/clientes/{cliente_id}", response_model=ClienteResponse)
def atualizar_cliente(
    cliente_id: int,
    payload: ClienteUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(cliente, key, value)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cliente(cliente_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    cliente.ativo = False
    db.commit()


# --- Prospecções ---

@router.get("/prospecções", response_model=List[ProspeccaoResponse])
def listar_prospecções(
    cliente_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(Prospeccao)
    if cliente_id:
        q = q.filter(Prospeccao.cliente_id == cliente_id)
    # Aplicar RBAC: analista vê apenas suas prospecções
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=Prospeccao.analista_id)
    return q.order_by(Prospeccao.criado_em.desc()).all()


@router.post("/prospecções", response_model=ProspeccaoResponse, status_code=status.HTTP_201_CREATED)
def criar_prospeccao(
    payload: ProspeccaoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Verificação de duplicidade: mesmo cliente já prospectado por outro analista
    existente = db.query(Prospeccao).filter(Prospeccao.cliente_id == payload.cliente_id).first()
    if existente:
        analista = existente.analista
        nome_analista = analista.nome if analista else "desconhecido"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este cliente já está sendo prospectado por {nome_analista}.",
        )

    prospeccao = Prospeccao(**payload.model_dump(), analista_id=current_user.id)
    db.add(prospeccao)
    db.commit()
    db.refresh(prospeccao)
    return prospeccao


@router.put("/prospecções/{prospeccao_id}", response_model=ProspeccaoResponse)
def atualizar_prospeccao(
    prospeccao_id: int,
    payload: ProspeccaoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    prospeccao = db.query(Prospeccao).filter(Prospeccao.id == prospeccao_id).first()
    if not prospeccao:
        raise HTTPException(status_code=404, detail="Prospecção não encontrada")
    # Somente o próprio analista ou gestor/ceo pode editar
    role_nome = current_user.role.nome if current_user.role else ""
    if prospeccao.analista_id != current_user.id and role_nome not in ("ceo", "gestor", "admin"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta prospecção")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(prospeccao, key, value)
    db.commit()
    db.refresh(prospeccao)
    return prospeccao


# --- Produtos ---

@router.get("/produtos", response_model=List[ProdutoResponse])
def listar_produtos(db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    return db.query(Produto).filter(Produto.ativo == True).all()


@router.post("/produtos", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
def criar_produto(
    payload: ProdutoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    produto = Produto(**payload.model_dump())
    db.add(produto)
    db.commit()
    db.refresh(produto)
    return produto


# --- Pedidos de Venda ---

@router.get("/pedidos", response_model=List[PedidoVendaResponse])
def listar_pedidos(
    cliente_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    q = db.query(PedidoVenda)
    if cliente_id:
        q = q.filter(PedidoVenda.cliente_id == cliente_id)
    q = filtrar_por_permissao(q, current_user, campo_usuario_id=PedidoVenda.analista_id)
    return q.order_by(PedidoVenda.criado_em.desc()).all()


@router.post("/pedidos", response_model=PedidoVendaResponse, status_code=status.HTTP_201_CREATED)
def criar_pedido(
    payload: PedidoVendaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    pedido = PedidoVenda(
        cliente_id=payload.cliente_id,
        analista_id=current_user.id,
        status=payload.status,
        observacoes=payload.observacoes,
    )
    db.add(pedido)
    db.flush()

    valor_total = 0
    for item_data in payload.itens:
        item = PedidoItem(pedido_id=pedido.id, **item_data.model_dump())
        db.add(item)
        if item_data.preco_unitario:
            desc = float(item_data.desconto or 0) / 100
            valor_total += float(item_data.preco_unitario) * item_data.quantidade * (1 - desc)

    pedido.valor_total = valor_total
    db.commit()
    db.refresh(pedido)
    return pedido


@router.put("/pedidos/{pedido_id}", response_model=PedidoVendaResponse)
def atualizar_pedido(
    pedido_id: int,
    payload: PedidoVendaUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    pedido = db.query(PedidoVenda).filter(PedidoVenda.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pedido, key, value)
    db.commit()
    db.refresh(pedido)
    return pedido
