"""Testes da lógica de chave de login (nome vs username legado)."""

from __future__ import annotations

from services.wiki_authenticator import credential_login_key, login_aliases_and_display


def test_credential_login_key_prefere_username_para_login():
    """Login curto em `username`; `nome` continua sendo o exibido na sessão."""
    ukey, display = credential_login_key("  Ana Silva ", "bob")
    assert ukey == "bob"
    assert display == "Ana Silva"


def test_credential_login_key_so_nome():
    ukey, display = credential_login_key("  Ana ", None)
    assert ukey == "ana"
    assert display == "Ana"


def test_credential_login_key_fallback_username():
    ukey, display = credential_login_key("", "carlos")
    assert ukey == "carlos"
    assert display == "carlos"


def test_credential_login_key_vazio():
    assert credential_login_key(None, None) == ("", "")
    assert credential_login_key("   ", "  ") == ("", "")


def test_login_aliases_inclui_nome_e_username_distintos():
    keys, display = login_aliases_and_display("Dev", "admin@epsy.com.br")
    assert keys == ["admin@epsy.com.br", "dev"]
    assert display == "Dev"
