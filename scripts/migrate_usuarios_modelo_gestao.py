"""
Aplica a migração SQL dos campos de gestão de utilizadores na tabela `usuarios`.

Uso:
  python scripts/migrate_usuarios_modelo_gestao.py
  python scripts/migrate_usuarios_modelo_gestao.py --dry-run

Requisitos: variáveis de ambiente de PostgreSQL configuradas (mesmo fluxo que `modules.database`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.database import get_connection  # noqa: E402


def _sql_path() -> Path:
    return ROOT / "database" / "migrations" / "20260403_usuarios_modelo_gestao.sql"


def _statements() -> list[str]:
    """Ordem idempotente; um comando por execute (compatível com psycopg2/SQLAlchemy)."""
    return [
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS username VARCHAR(150)",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_ferias BOOLEAN DEFAULT FALSE",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS em_atendimento_externo BOOLEAN DEFAULT FALSE",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS caminho_foto_perfil VARCHAR(500) DEFAULT ''",
        (
            "UPDATE usuarios SET username = lower(trim(nome)) "
            "WHERE username IS NULL OR btrim(username) = ''"
        ),
        (
            "COMMENT ON COLUMN usuarios.username IS "
            "'Login curto (minúsculas recomendado); autenticação aceita também nome.'"
        ),
        "COMMENT ON COLUMN usuarios.em_ferias IS 'Indicador operacional; default false.'",
        (
            "COMMENT ON COLUMN usuarios.em_atendimento_externo IS "
            "'Indicador operacional; default false.'"
        ),
        (
            "COMMENT ON COLUMN usuarios.caminho_foto_perfil IS "
            "'Caminho ou URL da foto; vazio se não houver.'"
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas mostra o SQL que seria executado.",
    )
    args = parser.parse_args()

    path = _sql_path()
    if not path.is_file():
        print(f"Ficheiro em falta: {path}", file=sys.stderr)
        return 2

    stmts = _statements()
    if args.dry_run:
        print(path.read_text(encoding="utf-8"))
        print("-- Comandos executados pelo script (equivalente):")
        for s in stmts:
            print(s + ";")
        return 0

    engine = get_connection()
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
    print("Migração aplicada com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
