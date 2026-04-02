"""
Executa uma página Streamlit em isolamento (subprocesso).

Não importa `modules.database` real (evita psycopg2 e Postgres no gate CI).

Uso:
  python tests/streamlit_page_runner.py path/to/page.py

Saída: imprime "OK" no stdout; qualquer exceção falha o processo com código != 0.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _install_fake_database_module():
    from tests.streamlit_mocks import fake_get_connection

    fake = types.ModuleType("modules.database")
    fake.get_connection = fake_get_connection
    fake.get_engine = fake_get_connection
    sys.modules["modules.database"] = fake


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: streamlit_page_runner.py <ficheiro.py>", file=sys.stderr)
        sys.exit(2)
    page = Path(sys.argv[1]).resolve()
    if not page.is_file():
        print(f"Ficheiro inexistente: {page}", file=sys.stderr)
        sys.exit(2)

    sys.path.insert(0, str(ROOT))

    from tests.streamlit_mocks import StreamlitStop, install_streamlit_stub

    install_streamlit_stub()
    _install_fake_database_module()

    import pandas as pd
    import runpy

    with (
        patch("pandas.read_sql", return_value=pd.DataFrame()),
        patch(
            "services.ui_realtime.render_global_notifications_listener",
            lambda *a, **k: None,
        ),
    ):
        try:
            runpy.run_path(str(page), run_name="__main__")
        except StreamlitStop:
            pass
    print("OK", flush=True)


if __name__ == "__main__":
    main()
