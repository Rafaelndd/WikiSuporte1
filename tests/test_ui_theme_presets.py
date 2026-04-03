"""Testes unitários para presets de tema (funções puras, sem Streamlit)."""

from services.ui_theme_presets import (
    SESSION_PRESET_KEY,
    VALID_PRESETS,
    build_theme_stylesheet,
    normalize_preset,
)


def test_normalize_preset_known() -> None:
    assert normalize_preset("anthropic_light") == "anthropic_light"
    assert normalize_preset("spotify_dark") == "spotify_dark"
    assert normalize_preset("padrao") == "padrao"


def test_normalize_preset_unknown_defaults() -> None:
    assert normalize_preset("") == "padrao"
    assert normalize_preset("nope") == "padrao"
    assert normalize_preset(None) == "padrao"


def test_build_theme_padrao_empty() -> None:
    assert build_theme_stylesheet("padrao").strip() == ""


def test_build_theme_anthropic_contains_tokens() -> None:
    css = build_theme_stylesheet("anthropic_light")
    assert "#faf8f5" in css
    assert 'html[data-theme="light"]' in css


def test_build_theme_spotify_contains_tokens() -> None:
    css = build_theme_stylesheet("spotify_dark")
    assert "#121212" in css
    assert 'html[data-theme="dark"]' in css


def test_valid_presets_session_key_stable() -> None:
    assert SESSION_PRESET_KEY == "ws_ui_theme_preset"
    assert set(VALID_PRESETS) == {"padrao", "anthropic_light", "spotify_dark"}
