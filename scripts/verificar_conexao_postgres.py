"""
Verifica conexão PostgreSQL com as mesmas variáveis de `modules/database.py`.

Uso: na raiz do projeto, com `.env` configurado:
  python scripts/verificar_conexao_postgres.py

Não imprime senhas nem URLs com credenciais.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def _env_status(name: str) -> str:
    import os

    v = os.getenv(name)
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return "ausente ou vazio"
    return "definido"


def main() -> int:
    import os

    from sqlalchemy import text

    keys = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASS")
    print("Variáveis (sem valores):")
    for k in keys:
        print(f"  {k}: {_env_status(k)}")

    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "central_chamados")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS")

    if db_pass is None or (isinstance(db_pass, str) and db_pass.strip() == ""):
        print("\nERRO: DB_PASS é obrigatório para conectar ao PostgreSQL.")
        return 1

    print(f"\nTentando conectar em {db_host}:{db_port} / banco={db_name} / usuário={db_user} …")

    try:
        from sqlalchemy import create_engine

        conn_str = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        eng = create_engine(conn_str, connect_args={"connect_timeout": 10})
        with eng.connect() as conn:
            one = conn.execute(text("SELECT 1 AS ok")).scalar()
            ver = conn.execute(text("SELECT version()")).scalar()
        print("Conexão: OK (SELECT 1 retornou", one, ")")
        if ver:
            vline = (ver or "").split("\n")[0][:120]
            print("Servidor:", vline)
        # Tabela usada no login
        with eng.connect() as conn:
            n = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'usuarios'"
                )
            ).scalar()
        print("Tabela public.usuarios existe:", "sim" if n else "não")
        return 0
    except Exception as e:
        print("Conexão: FALHOU")
        print("Tipo:", type(e).__name__)
        print("Mensagem:", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
