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


def test_slug_para_nome_arquivo_perfil():
    assert cu.slug_para_nome_arquivo_perfil("maria.silva", 1) == "maria.silva"
    assert cu.slug_para_nome_arquivo_perfil("", 42) == "id42"
    assert cu.slug_para_nome_arquivo_perfil("a" * 100, 1).startswith("a")


def test_validar_bytes_imagem_perfil_png():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    ok, ext = cu.validar_bytes_imagem_perfil(png)
    assert ok and ext == ".png"


def test_validar_bytes_imagem_perfil_jpeg():
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 30
    ok, ext = cu.validar_bytes_imagem_perfil(jpg)
    assert ok and ext == ".jpg"


def test_validar_bytes_imagem_perfil_rejeita_exe():
    ok, msg = cu.validar_bytes_imagem_perfil(b"MZ\x90\x00" + b"x" * 100)
    assert not ok
