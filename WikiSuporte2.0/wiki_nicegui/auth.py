"""
Autenticação: verificação de login contra PostgreSQL (paridade com app.py).

Mantém a mesma query e crypt() no banco; apenas adaptado para uso fora do Streamlit.
"""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy import text

# Assume que o chamador já adicionou o parent (WikiSuporte1) ao sys.path
from modules.database import get_connection


def verificar_login(username: str, senha_digitada: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Verifica credenciais delegando a validação de hash ao PostgreSQL (crypt).
    Retorna (sucesso, user_id, perfil).
    """
    if not (username and username.strip()) or not senha_digitada:
        return False, None, None
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT id, perfil
                FROM usuarios
                WHERE nome ILIKE :u
                  AND password_hash = crypt(:p, password_hash)
                  AND ativo = TRUE
            """)
            row = conn.execute(
                query, {"u": username.strip(), "p": senha_digitada}
            ).fetchone()
            if row:
                return True, int(row[0]), str(row[1]) if row[1] else None
    except Exception:
        pass
    return False, None, None
