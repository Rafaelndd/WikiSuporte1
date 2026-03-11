"""
Serviço: Guarda de Colaboração.
- Alerta diário: analistas (perfil analista) que não contribuíram na base_conhecimento no período.
- Filtro anti-duplicidade: ao aprovar contribuições, verificar se o tema já existe; permitir excluir ou substituir o registro antigo.
Uso: importar e chamar analistas_sem_contribuicao(), verificar_duplicidade_tema(), excluir_ou_substituir_antigo().
Não modifica arquivos originais do projeto.
"""
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text

try:
    from modules.database import get_connection
except ImportError:
    get_connection = None

# Perfil que deve ser alertado quando não contribui
PERFIL_ALVO = "analista"
# Dias sem contribuição para considerar "sem contribuição" (ajustável)
DIAS_SEM_CONTRIBUICAO = 30


def _engine():
    if get_connection is None:
        raise RuntimeError("modules.database.get_connection não disponível.")
    return get_connection()


def _normalizar_titulo(titulo: str) -> str:
    """Normaliza título para comparação de similaridade (minúsculas, sem acentos extras, espaços)."""
    if not titulo or not isinstance(titulo, str):
        return ""
    t = titulo.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t[:200]


def analistas_sem_contribuicao(dias: int = DIAS_SEM_CONTRIBUICAO) -> List[dict]:
    """
    Retorna lista de analistas (perfil analista) que não tiveram nenhuma contribuição
    aprovada na base_conhecimento nos últimos `dias` dias.
    Cada item: { id, nome, email, ultima_contribuicao }.
    """
    engine = _engine()
    data_limite = (datetime.now() - timedelta(days=dias)).date()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT u.id, u.nome, u.email,
                   (SELECT MAX(b.criado_em)::date
                    FROM base_conhecimento b
                    WHERE b.id_analista_autor = u.id AND b.status = 'APROVADO'
                      AND b.origem = 'CONHECIMENTO_SUPORTE') as ultima_contribuicao
            FROM usuarios u
            WHERE LOWER(TRIM(u.perfil)) = :perfil
              AND COALESCE(u.ativo, true) = true
        """), {"perfil": PERFIL_ALVO}).fetchall()

    resultado = []
    for row in rows:
        ultima = row[3]
        if ultima is None or (ultima if hasattr(ultima, "date") else ultima) < data_limite:
            resultado.append({
                "id": row[0],
                "nome": row[1],
                "email": row[2],
                "ultima_contribuicao": ultima,
            })
    return resultado


def obter_alertas_colaboracao_diarios(dias: int = DIAS_SEM_CONTRIBUICAO) -> List[str]:
    """
    Retorna mensagens de alerta prontas para exibição (ex.: painel ou e-mail).
    Uma string por analista sem contribuição.
    """
    analistas = analistas_sem_contribuicao(dias)
    msgs = []
    for a in analistas:
        ult = a.get("ultima_contribuicao")
        ult_str = str(ult) if ult else "nunca"
        msgs.append(f"[Colaboração] {a['nome']} (id={a['id']}) sem contribuição aprovada nos últimos {dias} dias. Última: {ult_str}.")
    return msgs


def verificar_duplicidade_tema(
    titulo: str,
    categoria: Optional[str] = None,
    subcategoria: Optional[str] = None,
    origem: str = "CONHECIMENTO_SUPORTE",
    excluir_id: Optional[int] = None,
) -> List[dict]:
    """
    Verifica se já existe contribuição na base_conhecimento com tema similar (titulo).
    Útil antes de aprovar uma nova contribuição para evitar duplicidade.
    Retorna lista de registros existentes: { id, titulo, categoria, subcategoria, criado_em }.
    excluir_id: se informado, exclui esse id da busca (ex.: o próprio registro sendo aprovado).
    """
    engine = _engine()
    tit_norm = _normalizar_titulo(titulo)
    if len(tit_norm) < 3:
        return []

    # Busca por similaridade: titulo normalizado contido ou similar (LIKE)
    with engine.connect() as conn:
        params = {"origem": origem, "titulo_like": f"%{tit_norm[:100]}%"}
        q = """
            SELECT id, titulo, categoria, subcategoria, criado_em, status
            FROM base_conhecimento
            WHERE origem = :origem
              AND LOWER(TRIM(titulo)) LIKE LOWER(:titulo_like)
        """
        if excluir_id is not None:
            q += " AND id <> :excluir_id"
            params["excluir_id"] = excluir_id
        if categoria:
            q += " AND LOWER(TRIM(categoria)) = LOWER(:cat)"
            params["cat"] = categoria
        q += " ORDER BY criado_em DESC"
        rows = conn.execute(text(q), params).fetchall()

    return [
        {"id": r[0], "titulo": r[1], "categoria": r[2], "subcategoria": r[3], "criado_em": r[4], "status": r[5]}
        for r in rows
    ]


def excluir_ou_substituir_antigo(
    id_antigo: int,
    acao: str = "excluir",
    id_novo: Optional[int] = None,
) -> bool:
    """
    Exclui o registro antigo da base_conhecimento ou marca para substituição.
    acao: 'excluir' (remove o registro id_antigo) ou 'substituir' (se id_novo informado, pode atualizar referências; aqui apenas exclui o antigo).
    Retorna True se a operação foi executada.
    """
    if acao != "excluir" and acao != "substituir":
        return False
    engine = _engine()
    with engine.begin() as conn:
        # Apenas excluir o registro antigo (origem CONHECIMENTO_SUPORTE para segurança)
        conn.execute(
            text("""
                DELETE FROM base_conhecimento
                WHERE id = :id AND origem = 'CONHECIMENTO_SUPORTE'
            """),
            {"id": id_antigo}
        )
    return True


def deve_alertar_duplicidade_ao_aprovar(titulo: str, categoria: Optional[str], id_atual: Optional[int]) -> Tuple[bool, List[dict]]:
    """
    Função de conveniência para a tela de aprovação.
    Retorna (True, lista_duplicados) se há tema similar já aprovado e o coordenador deve ser alertado.
    """
    duplicados = verificar_duplicidade_tema(titulo, categoria=categoria, excluir_id=id_atual)
    # Considerar apenas aprovados como "duplicidade" que importa
    aprovados = [d for d in duplicados if d.get("status") == "APROVADO"]
    return (len(aprovados) > 0, aprovados)
