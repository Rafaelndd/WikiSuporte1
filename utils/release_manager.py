"""
Gestão do catálogo de releases (Release da versão) em arquivo JSON local.

Arquivo: ``releases/releases_catalog.json`` (junto à documentação em Markdown).

Esquema de cada entrada
------------------------
- ``versao``: identificador legível (ex.: ``v1.2.0`` ou ``1.2.0``).
- ``data_lancamento``: data ISO ``YYYY-MM-DD``.
- ``como_era`` / ``como_ficou``: texto livre para comparativo na UI.
- ``dias_notificacao``: quantos dias corridos a notificação na Home fica ativa,
  **incluindo** o dia de lançamento (ex.: ``7`` = do dia do lançamento até
  ``lançamento + 6 dias``, ambos inclusive).
- ``notificacao_ate``: último dia inclusive do aviso na Home (calculado na gravação).

O módulo é independente do Streamlit para facilitar testes e reutilização.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final

# Catálogo ao lado do Markdown histórico
_CATALOG_PATH: Final[Path] = Path(__file__).resolve().parent.parent / "releases" / "releases_catalog.json"

# Valores legados (banner estático antigo) — usados só para bootstrap se não existir JSON
_LEGACY_VERSION: Final[str] = "1.0.1"
_LEGACY_DATE: Final[str] = "2026-04-04"
_LEGACY_SUMMARY: Final[str] = (
    "Login mais estável no navegador, página Release da versão e reforço de segurança nos bastidores."
)


@dataclass
class ReleaseRecord:
    versao: str
    data_lancamento: str  # YYYY-MM-DD
    como_era: str
    como_ficou: str
    dias_notificacao: int
    notificacao_ate: str  # YYYY-MM-DD (último dia inclusive do banner na Home)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ReleaseRecord:
        return cls(
            versao=str(raw.get("versao", "")).strip(),
            data_lancamento=str(raw.get("data_lancamento", "")).strip(),
            como_era=str(raw.get("como_era", "")),
            como_ficou=str(raw.get("como_ficou", "")),
            dias_notificacao=int(raw.get("dias_notificacao", 1)),
            notificacao_ate=str(raw.get("notificacao_ate", "")).strip(),
        )


def catalog_path() -> Path:
    return _CATALOG_PATH


def _parse_iso_date(s: str) -> date:
    return date.fromisoformat(s.strip()[:10])


def compute_notificacao_ate(data_lancamento: date, dias_notificacao: int) -> date:
    """
    Último dia (inclusive) em que o aviso na Home deve aparecer.
    ``dias_notificacao`` conta o dia de lançamento como dia 1.
    """
    d = max(1, int(dias_notificacao))
    return data_lancamento + timedelta(days=d - 1)


def _normalize_versao(v: str) -> str:
    t = (v or "").strip()
    if not t:
        return ""
    return t if t.lower().startswith("v") else f"v{t.lstrip('vV')}"


def _legacy_bootstrap_records() -> list[ReleaseRecord]:
    dl = _parse_iso_date(_LEGACY_DATE)
    dias = 14
    return [
        ReleaseRecord(
            versao=_normalize_versao(_LEGACY_VERSION),
            data_lancamento=dl.isoformat(),
            como_era="Versão anterior sem catálogo centralizado de releases.",
            como_ficou=_LEGACY_SUMMARY,
            dias_notificacao=dias,
            notificacao_ate=compute_notificacao_ate(dl, dias).isoformat(),
        )
    ]


def load_catalog(*, create_if_missing: bool = True) -> list[ReleaseRecord]:
    """
    Lê todas as releases (mais recente primeiro após normalização).
    Se o arquivo não existir e ``create_if_missing``, cria um com entrada legada.
    """
    if not _CATALOG_PATH.is_file():
        if create_if_missing:
            recs = _legacy_bootstrap_records()
            save_catalog(recs)
            return list(recs)
        return []

    try:
        raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    items = raw.get("releases") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []

    out: list[ReleaseRecord] = []
    for it in items:
        if isinstance(it, dict):
            try:
                out.append(ReleaseRecord.from_dict(it))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda r: _parse_iso_date(r.data_lancamento), reverse=True)
    return out


def save_catalog(records: list[ReleaseRecord]) -> None:
    """Grava o catálogo completo (substitui o arquivo)."""
    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"releases": [r.to_dict() for r in records]}
    _CATALOG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_release(
    versao: str,
    data_lancamento: date,
    como_era: str,
    como_ficou: str,
    dias_notificacao: int,
) -> ReleaseRecord:
    """
    Adiciona uma release no topo do catálogo (mais recente).
    Valida campos mínimos; devolve o registo gravado.
    """
    v = _normalize_versao(versao)
    if len(v) < 2 or not v.lower().startswith("v"):
        raise ValueError("Versão inválida: use algo como v1.2.0")

    dias = max(1, min(int(dias_notificacao), 365))
    fim = compute_notificacao_ate(data_lancamento, dias)
    rec = ReleaseRecord(
        versao=v,
        data_lancamento=data_lancamento.isoformat(),
        como_era=(como_era or "").strip(),
        como_ficou=(como_ficou or "").strip(),
        dias_notificacao=dias,
        notificacao_ate=fim.isoformat(),
    )
    existing = load_catalog(create_if_missing=True)
    # Remove duplicado exacto de versão (substitui)
    filtered = [r for r in existing if r.versao.lower() != rec.versao.lower()]
    save_catalog([rec] + filtered)
    return rec


def get_latest_release(records: list[ReleaseRecord] | None = None) -> ReleaseRecord | None:
    """Última release por data de lançamento."""
    r = records if records is not None else load_catalog(create_if_missing=False)
    return r[0] if r else None


def is_home_notification_active(
    today: date | None = None,
    records: list[ReleaseRecord] | None = None,
) -> bool:
    """True se a última release ainda estiver dentro da janela de notificação na Home."""
    latest = get_latest_release(records)
    if latest is None:
        return False
    hoje = today or date.today()
    try:
        fim = _parse_iso_date(latest.notificacao_ate)
    except ValueError:
        return False
    return hoje <= fim


def release_for_home_banner(records: list[ReleaseRecord] | None = None) -> ReleaseRecord | None:
    """Última release só se a notificação na Home ainda for válida."""
    latest = get_latest_release(records)
    if latest is None:
        return None
    if not is_home_notification_active(records=records):
        return None
    return latest
