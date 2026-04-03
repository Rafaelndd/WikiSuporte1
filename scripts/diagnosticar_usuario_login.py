"""
Diagnóstico de login (homolog/local): confere se o usuário existe no PostgreSQL,
se está ativo e se o hash de senha é compatível com bcrypt (streamlit-authenticator).

Uso (PowerShell):
  cd pasta-do-projeto
  $env:WIKI_TEST_PASSWORD = "sua_senha_aqui"
  python scripts/diagnosticar_usuario_login.py dev

Não commite senhas nem cole este comando em tickets com a senha real.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
load_dotenv()

_BCRYPT_RE = re.compile(r"^\$2[aby]\$\d+\$.{53}$")

# Igual a `services/wiki_authenticator.py` — se falhar aqui, o Streamlit não carrega credenciais.
_FILTRO_ATIVO = """(
    ativo IS NULL
    OR LOWER(TRIM(CAST(ativo AS TEXT))) IN ('true', 't', '1', 'sim', 'yes')
)"""


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/diagnosticar_usuario_login.py <login>")
        return 2
    login = sys.argv[1].strip().lower()
    pwd = (os.environ.get("WIKI_TEST_PASSWORD") or "").strip()

    try:
        from modules.database import get_connection
    except Exception as e:
        print(f"Erro ao importar conexão: {e}")
        return 1

    engine = get_connection()
    sql_try = text("""
        SELECT id, nome, username, perfil, ativo, password_hash
        FROM usuarios
        WHERE lower(trim(nome)) = :u
           OR lower(trim(username)) = :u
        LIMIT 1
    """)
    sql_fallback = text("""
        SELECT id, nome, perfil, ativo, password_hash
        FROM usuarios
        WHERE lower(trim(nome)) = :u
        LIMIT 1
    """)

    try:
        with engine.connect() as conn:
            try:
                row = conn.execute(sql_try, {"u": login}).mappings().first()
            except ProgrammingError:
                conn.rollback()
                row = conn.execute(sql_fallback, {"u": login}).mappings().first()
    except Exception as e:
        print(f"Erro SQL: {e}")
        return 1

    if row is None:
        print(f"Nenhuma linha em `usuarios` com login (username ou nome) = {login!r}.")
        return 1

    ph = row.get("password_hash")
    if isinstance(ph, bytes):
        phs = ph.decode("utf-8", errors="replace").strip()
    else:
        phs = (str(ph) if ph is not None else "").strip()

    print("id:", row.get("id"))
    print("nome:", row.get("nome"))
    print("username:", row.get("username", "(coluna ausente)"))
    print("perfil:", row.get("perfil"))
    print("ativo:", row.get("ativo"))
    print("hash vazio:", not phs)
    print("prefixo hash:", (phs[:7] + "…") if len(phs) > 7 else phs)
    print("parece bcrypt ($2a/$2b/$2y):", bool(_BCRYPT_RE.match(phs)))

    if pwd and phs:
        try:
            import bcrypt

            ok = bcrypt.checkpw(pwd.encode("utf-8"), phs.encode("utf-8"))
            print("bcrypt.checkpw com WIKI_TEST_PASSWORD:", ok)
        except Exception as e:
            print("bcrypt.checkpw falhou:", e)

    if not pwd:
        print("(defina WIKI_TEST_PASSWORD para testar a senha sem alterar o banco)")

    # Mesmo critério que load_credentials / fetch (utilizador visível para login)
    try:
        with engine.connect() as conn:
            ok_login = conn.execute(
                text(
                    f"""
                    SELECT 1 FROM usuarios
                    WHERE (lower(trim(nome)) = :u OR lower(trim(username)) = :u)
                      AND {_FILTRO_ATIVO}
                      AND password_hash IS NOT NULL
                      AND trim(coalesce(nome, '')) <> ''
                    LIMIT 1
                    """
                ),
                {"u": login},
            ).scalar()
    except ProgrammingError:
        with engine.connect() as conn:
            ok_login = conn.execute(
                text(
                    f"""
                    SELECT 1 FROM usuarios
                    WHERE lower(trim(nome)) = :u
                      AND {_FILTRO_ATIVO}
                      AND password_hash IS NOT NULL
                      AND trim(coalesce(nome, '')) <> ''
                    LIMIT 1
                    """
                ),
                {"u": login},
            ).scalar()
    except Exception as e:
        ok_login = None
        print("Aviso: não foi possível avaliar filtro de login:", e)

    print(
        "Aparece para o Streamlit (ativo + hash + nome):",
        "sim" if ok_login else "NÃO — ajuste `ativo` ou preencha password_hash",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
