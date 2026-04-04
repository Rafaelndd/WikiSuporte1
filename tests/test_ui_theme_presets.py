"""Testes unitários para tema visual (funções puras, sem Streamlit)."""

from services.ui_theme_presets import (
    SESSION_THEME_KEY,
    VALID_THEMES,
    build_theme_stylesheet,
    normalize_theme,
)


def test_normalize_theme_known() -> None:
    assert normalize_theme("light") == "light"
    assert normalize_theme("dark") == "dark"


def test_normalize_theme_unknown_defaults() -> None:
    assert normalize_theme("") == "light"
    assert normalize_theme("nope") == "light"
    assert normalize_theme(None) == "light"


def test_build_theme_light_contains_brand_tokens() -> None:
    css = build_theme_stylesheet("light")
    assert "#f85001" in css
    assert "#15789a" in css
    assert 'html[data-theme="light"]' in css


def test_build_theme_dark_contains_brand_tokens() -> None:
    css = build_theme_stylesheet("dark")
    assert "#15789a" in css
    assert 'html[data-theme="dark"]' in css


def test_valid_themes_session_key_stable() -> None:
    assert SESSION_THEME_KEY == "ws_streamlit_theme"
    assert set(VALID_THEMES) == {"light", "dark"}
