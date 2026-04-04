"""Testes do HTML de avatar circular (fallback e PNG válido)."""

from __future__ import annotations

from pathlib import Path

from services import ui_avatar as ua


def test_html_avatar_fallback_sem_caminho():
    h = ua.html_avatar_perfil_circular(None)
    assert "👤" in h
    assert "Avatar padrão" in h


def test_html_avatar_fallback_caminho_inexistente():
    h = ua.html_avatar_perfil_circular("/nao/existe/foto.png")
    assert "👤" in h


def test_html_avatar_png_pequeno(tmp_path: Path):
    p = tmp_path / "x.png"
    # Assinatura mínima PNG 1x1
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p.write_bytes(png)
    h = ua.html_avatar_perfil_circular(str(p), tamanho_px=40)
    assert "data:image/png;base64," in h
    assert "<img " in h


def test_html_avatar_emoji_personalizado():
    h = ua.html_avatar_perfil_circular(None, fallback_emoji="🧑‍💻")
    assert "🧑‍💻" in h
