"""
Modelo canônico do usuário WikiSuporte (tabela `public.usuarios`).

Mapeamento colunas ↔ conceito:
- nome: nome de exibição / identificador legado (único no sistema).
- username: login preferencial (minúsculas); se vazio no legado, usar o mesmo fluxo que `nome`.
- password_hash: senha apenas como hash bcrypt (nunca texto plano).
- perfil: somente ``admin`` ou ``analista`` na gravação de novos registos.
- ramal, ativo, em_ferias, em_atendimento_externo, caminho_foto_perfil: conforme negócio.

Executar `database/migrations/20260403_usuarios_modelo_gestao.sql` (ou o script Python)
antes de inserir linhas com os novos campos.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.perfil_usuario import perfil_valido_para_gravar

PERFIL_ADMIN = "admin"
PERFIL_ANALISTA = "analista"


@dataclass(frozen=True)
class UsuarioPersistencia:
    """Campos esperados para criar/atualizar um usuário no novo modelo."""

    nome: str
    username: str
    password_hash: str
    perfil: str
    ramal: str = ""
    ativo: bool = True
    em_ferias: bool = False
    em_atendimento_externo: bool = False
    caminho_foto_perfil: str = ""


def normalizar_username(valor: str | None) -> str:
    """Login canónico em minúsculas, sem espaços nas pontas."""
    return (valor or "").strip().lower()


def perfil_aceite_para_gravar(perfil: str) -> str | None:
    """Retorna ``admin`` ou ``analista`` ou None se inválido."""
    return perfil_valido_para_gravar(perfil)


def defaults_novo_usuario(
    nome: str,
    username_login: str | None,
    *,
    ramal: str = "",
    ativo: bool = True,
    em_ferias: bool = False,
    em_atendimento_externo: bool = False,
    caminho_foto_perfil: str = "",
) -> tuple[str, str]:
    """
    Deriva (nome_db, username_db) a partir do input.
    Se `username_login` for omitido, o username passa a ser `lower(nome)`.
    """
    nome_db = (nome or "").strip()
    if not nome_db:
        return "", ""
    un = normalizar_username(username_login) if username_login else normalizar_username(nome_db)
    return nome_db, un or normalizar_username(nome_db)
