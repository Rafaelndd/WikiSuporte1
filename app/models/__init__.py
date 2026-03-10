from .usuario import Base, Setor, Role, Usuario, Permissao, RolePermissao
from .tarefa import Espaco, Pasta, Lista, StatusConfig, Tarefa, TarefaResponsavel, TarefaLista, TarefaDependencia, Checklist, ChecklistItem, TarefaComentario, Automacao
from .crm import Cliente, Prospeccao, PedidoVenda, Produto, PedidoItem
from .suporte import Atendimento, Chamado, Plantao, Importacao
from .auditoria import Auditoria

__all__ = [
    "Base",
    "Setor", "Role", "Usuario", "Permissao", "RolePermissao",
    "Espaco", "Pasta", "Lista", "StatusConfig", "Tarefa", "TarefaResponsavel",
    "TarefaLista", "TarefaDependencia", "Checklist", "ChecklistItem",
    "TarefaComentario", "Automacao",
    "Cliente", "Prospeccao", "PedidoVenda", "Produto", "PedidoItem",
    "Atendimento", "Chamado", "Plantao", "Importacao",
    "Auditoria",
]
