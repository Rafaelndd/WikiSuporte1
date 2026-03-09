from sqlalchemy.orm import Query
from ..models.usuario import Usuario


def filtrar_por_permissao(query: Query, usuario: Usuario, campo_usuario_id=None, campo_setor_id=None) -> Query:
    """
    Aplica filtro hierárquico à query conforme o role do usuário:
    - CEO / admin: sem filtro (visão global)
    - gestor: filtra pelo setor do usuário
    - analista / viewer: filtra por usuario_id

    Args:
        query: SQLAlchemy Query a ser filtrada.
        usuario: Usuário autenticado.
        campo_usuario_id: Coluna do modelo referente ao id do usuário responsável.
        campo_setor_id: Coluna do modelo referente ao setor (opcional).
    """
    if usuario.role is None:
        # Sem role: retorna apenas dados do próprio usuário
        if campo_usuario_id is not None:
            return query.filter(campo_usuario_id == usuario.id)
        return query

    role_nome = usuario.role.nome.lower()

    if role_nome in ("ceo", "admin"):
        # Visão global — sem filtro
        return query

    if role_nome == "gestor":
        # Filtra pelo setor, se o campo estiver disponível
        if campo_setor_id is not None and usuario.setor_id is not None:
            return query.filter(campo_setor_id == usuario.setor_id)
        return query

    # analista, viewer e outros: visão restrita ao próprio usuário
    if campo_usuario_id is not None:
        return query.filter(campo_usuario_id == usuario.id)

    return query
