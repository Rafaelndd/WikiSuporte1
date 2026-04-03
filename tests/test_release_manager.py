"""Testes do catálogo de releases (ficheiro JSON / datas)."""

from __future__ import annotations

from datetime import date

import pytest

from utils import release_manager as rm
from utils.release_manager import (
    ReleaseRecord,
    append_release,
    compute_notificacao_ate,
    is_home_notification_active,
    release_for_home_banner,
)


def test_compute_notificacao_ate_inclui_lancamento() -> None:
    d0 = date(2026, 4, 1)
    assert compute_notificacao_ate(d0, 1) == d0
    assert compute_notificacao_ate(d0, 7) == date(2026, 4, 7)


def test_is_home_notification_active(monkeypatch: pytest.MonkeyPatch) -> None:
    recs = [
        ReleaseRecord(
            versao="v1.0.0",
            data_lancamento="2026-01-01",
            como_era="a",
            como_ficou="b",
            dias_notificacao=3,
            notificacao_ate="2026-01-03",
        )
    ]
    assert is_home_notification_active(today=date(2026, 1, 2), records=recs) is True
    assert is_home_notification_active(today=date(2026, 1, 3), records=recs) is True
    assert is_home_notification_active(today=date(2026, 1, 4), records=recs) is False


def test_release_for_home_banner_respeita_expiracao() -> None:
    recs = [
        ReleaseRecord(
            versao="v9.9.9",
            data_lancamento="2020-01-01",
            como_era="x",
            como_ficou="y",
            dias_notificacao=1,
            notificacao_ate="2020-01-01",
        )
    ]
    assert release_for_home_banner(records=recs) is None  # hoje > 2020-01-01


def test_append_release_grava_e_substitu(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    p = tmp_path / "releases_catalog.json"
    monkeypatch.setattr(rm, "_CATALOG_PATH", p)
    r1 = append_release(
        "1.0.0",
        date(2026, 5, 1),
        "antes",
        "depois",
        5,
    )
    assert r1.versao == "v1.0.0"
    assert r1.notificacao_ate == "2026-05-05"
    r2 = append_release(
        "1.0.0",
        date(2026, 6, 1),
        "antes2",
        "depois2",
        2,
    )
    assert r2.data_lancamento == "2026-06-01"
    cat = rm.load_catalog(create_if_missing=False)
    assert len([x for x in cat if x.versao == "v1.0.0"]) == 1
