"""Testes do modelo de persistência de utilizadores (sem PostgreSQL)."""

from __future__ import annotations

from services.usuario_modelo import defaults_novo_usuario, normalizar_username, perfil_aceite_para_gravar


def test_normalizar_username():
    assert normalizar_username("  Ana.B ") == "ana.b"
    assert normalizar_username(None) == ""


def test_perfil_aceite_para_gravar():
    assert perfil_aceite_para_gravar("admin") == "admin"
    assert perfil_aceite_para_gravar("analista") == "analista"
    assert perfil_aceite_para_gravar("coordenador") is None


def test_defaults_novo_usuario_legado_so_login():
    n, u = defaults_novo_usuario("Meu.Login", None)
    assert n == "Meu.Login"
    assert u == "meu.login"


def test_defaults_novo_usuario_nome_e_login_distintos():
    n, u = defaults_novo_usuario("Maria Silva", "msilva")
    assert n == "Maria Silva"
    assert u == "msilva"


def test_defaults_novo_usuario_vazio():
    assert defaults_novo_usuario("", None) == ("", "")
