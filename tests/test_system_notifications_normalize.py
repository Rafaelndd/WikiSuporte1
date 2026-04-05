"""Testes unitários para normalização de tipos de notificação."""

from __future__ import annotations

import pytest

from services.notificacao_tipos import TIPOS_VALIDOS, normalizar_tipo_notificacao


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("comunicado", "comunicado"),
        ("Comunicado", "comunicado"),
        ("aviso", "aviso"),
        ("Erro Crítico", "erro_critico"),
        ("erro_critico", "erro_critico"),
        ("Versão Bloqueada", "versao_bloqueada"),
        ("  versão  bloqueada  ", "versao_bloqueada"),
        ("Release WikiSuporte", "release_wikisuporte"),
        (" release   wikisuporte ", "release_wikisuporte"),
        ("invalid", None),
        ("", None),
    ],
)
def test_normalizar_tipo_notificacao(raw: str, expected: str | None):
    assert normalizar_tipo_notificacao(raw) == expected


def test_tipos_validos_coverage():
    for t in TIPOS_VALIDOS:
        assert normalizar_tipo_notificacao(t) == t
