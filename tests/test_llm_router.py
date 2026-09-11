"""Testes do roteador LLM (fallback Groq)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import services.llm_router as lr


def test_gerar_resposta_usa_groq_quando_gemini_indisponivel(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "  Resposta do Groq  "}}],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        },
    }

    with patch.object(lr, "_tentar_gemini", return_value=None):
        with patch("requests.post", return_value=fake_resp) as post:
            out = lr.gerar_resposta("Qual é o passo 1?", contexto="")

    assert out.provedor == "groq"
    assert out.modelo == "llama-3.3-70b-versatile"
    assert out.texto == "Resposta do Groq"
    assert post.called


def test_gerar_resposta_offline_sem_chaves(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with patch.object(lr, "_tentar_gemini", return_value=None):
        out = lr.gerar_resposta("teste", contexto="")

    assert out.provedor == "nenhum"
    assert "não está disponível" in out.texto.lower()
