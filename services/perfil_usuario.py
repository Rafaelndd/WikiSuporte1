"""
Perfis canônicos alinhados ao PostgreSQL: somente `admin` e `analista`.

Valores legados no banco ou na sessão (dev, coordenação, master, etc.)
são normalizados para um destes dois ao aplicar regras de acesso.
"""

from __future__ import annotations

# Texto exato recomendado em `usuarios.perfil` (como no seu banco hoje)
PERFIL_ADMIN = "admin"
PERFIL_ANALISTA = "analista"

# Tudo isto conta como administrador (acesso total), gravando `admin` em novas alterações
_ALIASES_ADMIN = frozenset(
    {
        "admin",
        "administrador",
        "master",
        "dev",
        "desenvolvedor",
        "coordenador",
        "coordenação",
        "coordenacao",
        "supervisor",
        "supervisão",
        "supervisao",
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
