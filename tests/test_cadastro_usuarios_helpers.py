"""Testes auxiliares de cadastro_usuarios (sem PostgreSQL)."""

from __future__ import annotations

import cadastro_usuarios as cu


def test_mapear_perfil_cli():
    assert cu.mapear_perfil_cli("analista") == "analista"
    assert cu.mapear_perfil_cli("admin") == "admin"
    assert cu.mapear_perfil_cli("coordenador") == "admin"
    assert cu.mapear_perfil_cli("dev") == "admin"


def test_validar_senha_forte_ok():
    ok, _ = cu.validar_senha_forte("Abcd1234!")
    assert ok


def test_validar_senha_forte_curta():
    ok, msg = cu.validar_senha_forte("A1!")
    assert not ok
    assert "8" in msg


def test_atualizar_usuario_sem_alteracoes():
    ok, msg = cu.atualizar_usuario("x", None, None)
    assert not ok
    assert "Nada a atualizar" in msg


def test_atualizar_usuario_senha_vazia_string():
    """Senha '' não conta como alteração de hash."""
    ok, msg = cu.atualizar_usuario("x", "", None)
    assert not ok
