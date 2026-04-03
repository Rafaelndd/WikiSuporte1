"""Perfis canônicos admin / analista."""

from __future__ import annotations

from services.perfil_usuario import (
    PERFIL_ADMIN,
    PERFIL_ANALISTA,
    eh_admin,
    normalizar_perfil_para_sessao,
    perfil_valido_para_gravar,
)


def test_normaliza_admin_e_analista_do_banco():
    assert normalizar_perfil_para_sessao("admin") == PERFIL_ADMIN
    assert normalizar_perfil_para_sessao("analista") == PERFIL_ANALISTA


def test_legado_vira_admin():
    assert normalizar_perfil_para_sessao("dev") == PERFIL_ADMIN
    assert normalizar_perfil_para_sessao("master") == PERFIL_ADMIN
    assert normalizar_perfil_para_sessao("coordenação") == PERFIL_ADMIN


def test_desconhecido_e_analista():
    assert normalizar_perfil_para_sessao("xyz") == PERFIL_ANALISTA
    assert normalizar_perfil_para_sessao(None) == PERFIL_ANALISTA


def test_perfil_valido_para_gravar():
    assert perfil_valido_para_gravar("admin") == PERFIL_ADMIN
    assert perfil_valido_para_gravar("master") is None


def test_eh_admin():
    assert eh_admin("admin") is True
    assert eh_admin("analista") is False
