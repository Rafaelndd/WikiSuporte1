"""
Configuração global do pytest: caminho do projeto e registo de falhas no relatório QA.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Valores dummy para variáveis que o app agora exige explicitamente
# (modules/database.py, services/wiki_authenticator.py) e que antes tinham
# fallback silencioso. Em CI (sem .env) os testes que só importam esses
# módulos, ou rodam páginas em subprocesso que herda os.environ, quebravam
# sem isso. setdefault: nunca sobrescreve um .env real já carregado.
os.environ.setdefault("DB_PASS", "test-dummy-nao-usar-em-producao")
os.environ.setdefault("WS_SESSION_SECRET", "test-dummy-nao-usar-em-producao")


def pytest_runtest_logreport(report):
    if report.when != "call" or not report.failed:
        return
    try:
        from tests.qa_report import log_pytest_failure

        lr = getattr(report, "longreprtext", None) or str(getattr(report, "longrepr", ""))
        log_pytest_failure(report.nodeid, lr)
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    if exitstatus == 0:
        return
    try:
        from tests.qa_report import log_grave

        log_grave(
            f"Sessão pytest terminou com código {exitstatus}. "
            "Rever `logs/qa_production_gate.log` e corrigir antes de novo deploy.",
            component="pytest_session",
            level=logging.ERROR,
        )
    except Exception:
        pass
