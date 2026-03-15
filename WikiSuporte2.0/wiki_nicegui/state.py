"""
Estado de sessão do usuário no NiceGUI.

No Streamlit usamos st.session_state; no NiceGUI usamos app.storage.user
(por conexão/sessão) para manter autenticado, usuario_id, perfil, etc.
Este módulo centraliza leitura/escrita para manter paridade com o app original.
"""
from __future__ import annotations

from typing import Any, Optional

from nicegui import app


def get_user_storage() -> dict:
    """Retorna o dicionário de armazenamento do usuário (por sessão)."""
    if not hasattr(app.storage, "user"):
        app.storage.user = {}
    return app.storage.user


def is_authenticated() -> bool:
    return bool(get_user_storage().get("autenticado", False))


def get_usuario_id() -> Optional[int]:
    return get_user_storage().get("usuario_id")


def get_usuario_nome() -> str:
    return str(get_user_storage().get("usuario_nome", "") or "").strip()


def get_perfil() -> str:
    return str(get_user_storage().get("perfil", "analista") or "analista").strip().lower()


def get_perfil_normalizado() -> str:
    """Convenção: dev, coordenador, analista (igual auth_guard)."""
    p = get_perfil()
    if p in ("desenvolvedor", "dev"):
        return "dev"
    if p in ("coordenação", "coordenador"):
        return "coordenador"
    return p or "analista"


def set_login(user_id: int, nome: str, perfil: str) -> None:
    storage = get_user_storage()
    storage["autenticado"] = True
    storage["usuario_id"] = user_id
    storage["usuario_nome"] = nome
    storage["perfil"] = perfil
    storage["notificacoes_lidas"] = storage.get("notificacoes_lidas") or []


def logout() -> None:
    get_user_storage().clear()
    app.storage.user = {}


def notificacoes_lidas() -> list:
    return get_user_storage().get("notificacoes_lidas") or []


def marcar_notificacao_lida(notif_id: str) -> None:
    storage = get_user_storage()
    lst = storage.get("notificacoes_lidas") or []
    if notif_id not in lst:
        lst.append(notif_id)
    storage["notificacoes_lidas"] = lst


def remover_notificacao_lida(notif_id: str) -> None:
    storage = get_user_storage()
    lst = storage.get("notificacoes_lidas") or []
    if notif_id in lst:
        lst.remove(notif_id)
    storage["notificacoes_lidas"] = lst
