"""
Carrega cada `pages/*.py` num subprocesso com Streamlit e BD falsos.

Objetivo: validar que o código de topo da página interpreta sem servidor Streamlit.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "streamlit_page_runner.py"
PAGES = sorted((ROOT / "pages").glob("*.py"))


@pytest.mark.streamlit_smoke
@pytest.mark.parametrize("page_path", PAGES, ids=lambda p: p.name)
def test_streamlit_page_executes_with_stubs(page_path: Path):
    proc = subprocess.run(
        [sys.executable, str(RUNNER), str(page_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env={
            **dict(__import__("os").environ),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    if proc.returncode != 0:
        from tests.qa_report import log_grave

        log_grave(
            f"Falha ao carregar página Streamlit | path={page_path}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
            component="streamlit_page_runner",
            level=logging.CRITICAL,
        )
    assert proc.returncode == 0, f"{page_path.name}:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
