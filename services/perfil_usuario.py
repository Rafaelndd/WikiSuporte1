"""
Perfis canônicos alinhados ao PostgreSQL: somente `admin` e `analista`.

Valores desconhecidos (qualquer coisa fora dos dois canônicos e dos aliases
abaixo) caem em `analista` por padrão — o normalizador nunca concede admin
implicitamente a um valor não reconhecido.
"""

from __future__ import annotations

# Texto exato recomendado em `usuarios.perfil` (como no seu banco hoje)
PERFIL_ADMIN = "admin"
PERFIL_ANALISTA = "analista"

# Restrito aos valores realmente em uso (confirmado por introspecção em
# `usuarios.perfil`: só existem 'admin' e 'analista' hoje). Antes incluía
# aliases legados (dev, coordenador, master, supervisor...) que concediam
# admin completo a qualquer um desses valores — nenhum usuário real os
# utiliza, e mantê-los era uma via de escalonamento de privilégio silencioso
# caso alguém definisse perfil='dev' manualmente no banco no futuro.
_ALIASES_ADMIN = frozenset(
    {
        "admin",
        "administrador",
    }
)

_ALIASES_ANALISTA = frozenset(
    {
        "analista",
        "analista de suporte",
        "tecnico",
        "técnico",
        "suporte",
    }
)


def normalizar_perfil_para_sessao(raw: str | None) -> str:
    """Retorna sempre `admin` ou `analista` (nunca `master` nem outros)."""
    if not raw:
        return PERFIL_ANALISTA
    r = str(raw).strip().lower()
    if r in _ALIASES_ADMIN:
        return PERFIL_ADMIN
    if r in _ALIASES_ANALISTA:
        return PERFIL_ANALISTA
    return PERFIL_ANALISTA


def perfil_valido_para_gravar(canonico: str) -> str | None:
    """Aceita apenas os dois valores que existem no banco."""
    c = (canonico or "").strip().lower()
    if c == PERFIL_ADMIN:
        return PERFIL_ADMIN
    if c == PERFIL_ANALISTA:
        return PERFIL_ANALISTA
    return None


def eh_admin(perfil_canonico: str | None) -> bool:
    return normalizar_perfil_para_sessao(perfil_canonico) == PERFIL_ADMIN
