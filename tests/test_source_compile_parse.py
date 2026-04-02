"""
Validação estática de todo o código Python do repositório: AST + bytecode compile.
Não requer base de dados nem Streamlit em execução.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".cursor",
    "PostgreSQL",
    "uploads",
    "uploads_wiki",
    "documentacoes_sistema",
    "releases_tecnuv",
    "dist",
    "build",
    ".eggs",
    "WikiFeedbacks",
    "backups",
}


def _iter_py_files():
    for p in ROOT.rglob("*.py"):
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        if set(rel.parts) & SKIP_DIRS:
            continue
        yield p


def test_all_python_sources_parse_and_compile():
    failures: list[tuple[Path, str]] = []
    for path in sorted(_iter_py_files()):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
            ast.parse(src, filename=str(path))
            compile(src, str(path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            failures.append((path, f"{type(e).__name__}: {e}"))

    if failures:
        from tests.qa_report import log_compile_aggregated

        log_compile_aggregated(failures)

    assert not failures, "Erros de sintaxe:\n" + "\n".join(f"{p}: {err}" for p, err in failures)
