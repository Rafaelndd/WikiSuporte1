"""Testes unitários para tema visual (funções puras, sem Streamlit) — apenas escuro."""

from services.ui_theme_presets import (
    SESSION_THEME_KEY,
    VALID_THEMES,
    build_theme_stylesheet,
    normalize_theme,
)


def test_normalize_theme_always_dark() -> None:
    assert normalize_theme("light") == "dark"
    assert normalize_theme("dark") == "dark"
    assert normalize_theme("") == "dark"
    assert normalize_theme("nope") == "dark"
    assert normalize_theme(None) == "dark"


def test_build_theme_dark_contains_brand_tokens() -> None:
    css = build_theme_stylesheet()
    assert "#15789a" in css
    assert 'html[data-theme="dark"]' in css


def test_valid_themes_session_key_stable() -> None:
    assert SESSION_THEME_KEY == "ws_streamlit_theme"
    assert set(VALID_THEMES) == {"dark"}
