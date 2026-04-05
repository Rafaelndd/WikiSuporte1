"""
Regras de qualidade para consultas SQL nas páginas Streamlit.
Objetivo:
1) impedir queries em aberto do tipo `SELECT *`
2) garantir foco de dados necessário para as páginas do frontend
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "pages").glob("*.py"))

_SELECT_STAR_RE = re.compile(r"(?i)SELECT\s+\*\s+FROM")


def _select_star_occurrences(path: Path) -> list[tuple[int, str]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    matches: list[tuple[int, str]] = []
    for match in _SELECT_STAR_RE.finditer(content):
        start = match.start()
        line = content.count("\n", 0, start) + 1
        snippet = content[max(0, start - 40) : min(len(content), match.end() + 20)]
        matches.append((line, snippet.replace("\n", " ").strip()))
    return matches


@pytest.mark.parametrize("page_path", PAGES, ids=lambda p: p.name)
def test_pages_nao_utilizam_select_asterisco_nao_projetado(page_path: Path) -> None:
    """
    Todas as páginas de frontend devem buscar colunas específicas.
    O padrão `SELECT *` é vetado para evitar transferência desnecessária de dados.
    """
    matches = _select_star_occurrences(page_path)
    assert not matches, f"Página {page_path.name} ainda usa SELECT *: {matches}"
