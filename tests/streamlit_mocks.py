"""
Stubs mínimos do Streamlit e da base de dados para carregar páginas sem `streamlit run`.

Uso em subprocesso para não contaminar `sys.modules` entre testes.
"""

from __future__ import annotations

import sys
from datetime import date, time
from unittest.mock import MagicMock

import pandas as pd


class StreamlitStop(Exception):
    """
    Simula o fim do script após st.stop().
    O runner captura esta exceção e trata como conclusão válida do smoke test.
    """


def install_streamlit_stub(session_state: dict | None = None) -> MagicMock:
    if session_state is None:
        session_state = {
            "autenticado": True,
            "perfil": "dev",
            "usuario_id": 1,
            "usuario_nome": "QA Gate",
            "notificacoes_lidas": [],
        }

    st = MagicMock()
    st.session_state = session_state

    def passthrough_cache(*_a, **_k):
        def deco(fn):
            return fn

        return deco

    st.cache_data = passthrough_cache
    st.cache_resource = passthrough_cache

    def _tabs(names):
        return tuple(MagicMock() for _ in names)

    st.tabs = MagicMock(side_effect=_tabs)

    def _columns(*args, **_kwargs):
        # Repete o próprio `st` para que `col.date_input` seja o mesmo stub de `st.date_input`.
        if not args:
            return (st, st)
        first = args[0]
        if isinstance(first, int):
            return tuple(st for _ in range(first))
        if isinstance(first, (list, tuple)):
            return tuple(st for _ in first)
        return (st, st)

    st.columns = MagicMock(side_effect=_columns)

    def _ctx():
        m = MagicMock()
        m.__enter__ = MagicMock(return_value=m)
        m.__exit__ = MagicMock(return_value=False)
        return m

    ctx = _ctx()
    st.sidebar = ctx
    st.form = MagicMock(return_value=_ctx())
    st.status = MagicMock(return_value=_ctx())
    st.expander = MagicMock(return_value=_ctx())
    st.container = MagicMock(return_value=_ctx())

    st.set_page_config = MagicMock()
    st.switch_page = MagicMock()
    st.stop = MagicMock(side_effect=StreamlitStop)
    st.rerun = MagicMock()
    st.balloons = MagicMock()
    st.snow = MagicMock()

    st.title = MagicMock()
    st.header = MagicMock()
    st.subheader = MagicMock()
    st.markdown = MagicMock()
    st.caption = MagicMock()
    st.write = MagicMock()
    st.error = MagicMock()
    st.warning = MagicMock()
    st.success = MagicMock()
    st.info = MagicMock()
    st.metric = MagicMock()
    st.divider = MagicMock()

    def _selectbox(*args, **kwargs):
        opts = kwargs.get("options")
        if opts is None and len(args) >= 2:
            opts = args[1]
        if opts is not None and len(opts) > 0:
            return opts[0]
        return ""

    st.selectbox = MagicMock(side_effect=_selectbox)
    st.multiselect = MagicMock(return_value=[])
    st.text_input = MagicMock(return_value="")
    st.text_area = MagicMock(return_value="")
    st.number_input = MagicMock(return_value=0)
    st.slider = MagicMock(return_value=60)
    st.toggle = MagicMock(return_value=False)
    st.checkbox = MagicMock(return_value=False)
    st.button = MagicMock(return_value=False)
    st.download_button = MagicMock(return_value=False)
    st.form_submit_button = MagicMock(return_value=False)
    st.file_uploader = MagicMock(return_value=None)
    def _date_input(*args, **kwargs):
        v = kwargs.get("value")
        if isinstance(v, (tuple, list)) and len(v) == 2:
            return (v[0], v[1])
        return date.today()

    st.date_input = MagicMock(side_effect=_date_input)
    st.time_input = MagicMock(return_value=time(12, 0))
    st.radio = MagicMock(return_value="")
    st.color_picker = MagicMock(return_value="#000000")
    st.dataframe = MagicMock()
    st.table = MagicMock()
    st.plotly_chart = MagicMock()
    st.pyplot = MagicMock()
    st.image = MagicMock()
    st.map = MagicMock()
    st.json = MagicMock()
    st.code = MagicMock()
    st.link_button = MagicMock()
    st.toast = MagicMock()
    st.spinner = MagicMock()
    st.progress = MagicMock()

    comp = MagicMock()
    v1 = MagicMock()
    v1.html = MagicMock()
    comp.v1 = v1

    sys.modules["streamlit"] = st
    sys.modules["streamlit.components"] = comp
    sys.modules["streamlit.components.v1"] = v1
    return st


def fake_get_connection():
    """Motor SQLAlchemy-falso: sem rede; suporta `with engine.begin()` usado em DDL."""
    eng = MagicMock()
    conn = MagicMock()
    conn.execute = MagicMock(return_value=MagicMock())
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    eng.begin = MagicMock(return_value=ctx)
    eng.connect = MagicMock(return_value=ctx)
    return eng


def empty_read_sql(*_args, **_kwargs):
    return pd.DataFrame()
