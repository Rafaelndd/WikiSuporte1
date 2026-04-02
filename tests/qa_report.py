"""
Relatório de falhas do gate de qualidade para ambientes em produção.

Registra eventos graves (falhas de teste, erros de sintaxe em lote, etc.) em
`logs/qa_production_gate.log`, separado de `logs/sistema.log`, para análise
com o serviço parado. O arquivo segue o padrão *.log no .gitignore.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

_LOGGER: Optional[logging.Logger] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _log_path() -> Path:
    log_dir = _project_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "qa_production_gate.log"


def get_qa_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("wikisuporte.qa_gate")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fh = logging.FileHandler(_log_path(), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(fh)
    logger.propagate = False
    _LOGGER = logger
    return logger


def log_grave(
    message: str,
    *,
    component: str = "qa_gate",
    level: int = logging.ERROR,
    exc_info: Any = None,
) -> None:
    """Registra um evento considerado grave para revisão manual."""
    log = get_qa_logger()
    log.log(level, f"[{component}] {message}", exc_info=exc_info)


def log_compile_aggregated(failures: list[tuple[Path, str]]) -> None:
    """Único registro agregado para muitos ficheiros com erro de sintaxe."""
    if not failures:
        return
    lines = "\n".join(f"  - {p}: {err}" for p, err in failures[:200])
    more = f"\n  ... e mais {len(failures) - 200} ocorrências." if len(failures) > 200 else ""
    log_grave(
        f"Falha agregada de parse/AST em {len(failures)} ficheiro(s).\n{lines}{more}",
        component="source_parse",
        level=logging.CRITICAL,
    )


def log_pytest_failure(nodeid: str, longrepr: str) -> None:
    log_grave(
        f"pytest failure | nodeid={nodeid}\n{longrepr}",
        component="pytest",
        level=logging.ERROR,
    )


__all__ = [
    "get_qa_logger",
    "log_grave",
    "log_compile_aggregated",
    "log_pytest_failure",
]
