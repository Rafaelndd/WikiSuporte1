"""
Serviço: Roteador de LLM (Gemini + Groq).

Objetivo:
- Centralizar o uso de LLM para texto (pergunta + contexto) sem alterar
  o código existente.
- Usar GEMINI_API_KEY como provedora principal (google-genai).
- Usar GROQ_API_KEY como fallback (API OpenAI-compatible em api.groq.com).

Importante:
- Este módulo NÃO é importado automaticamente em nenhuma página.
- A integração é opcional e deve ser feita manualmente nos pontos de uso
  de IA (por exemplo, na aba do Assistente em `6_🤝_Contribuicoes_Suporte.py`),
  substituindo a chamada direta ao Gemini por uma chamada a `gerar_resposta()`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


try:
    # Carrega .env apenas quando este módulo é usado
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = lambda: None  # type: ignore


load_dotenv()


@dataclass
class LLMResposta:
    """
    Estrutura de retorno padrão para chamadas de LLM.

    - texto: resposta final em texto.
    - provedor: 'gemini', 'groq' ou 'nenhum'.
    - modelo: nome do modelo utilizado.
    - meta: dicionário opcional com metadados (tokens, etc.).
    """

    texto: str
    provedor: str
    modelo: str
    meta: Dict[str, Any]


def _get_gemini_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY")


def _get_groq_api_key() -> Optional[str]:
    return (os.getenv("GROQ_API_KEY") or "").strip() or None


def _tentar_gemini(prompt: str, modelo: str = "gemini-2.5-flash") -> Optional[LLMResposta]:
    """
    Tenta gerar resposta via Gemini.
    Retorna LLMResposta ou None em caso de erro (quota, auth, etc.).
    """
    api_key = _get_gemini_api_key()
    if not api_key:
        return None

    try:
        from google import genai
    except Exception:
        return None

    try:
        client = genai.Client(api_key=api_key)
        resposta = client.models.generate_content(
            model=modelo,
            contents=prompt,
        )

        texto = getattr(resposta, "text", "") or ""
        usage = getattr(resposta, "usage_metadata", None)
        meta: Dict[str, Any] = {}
        if usage is not None:
            meta["tokens_prompt"] = getattr(usage, "input_tokens", None) or getattr(
                usage, "prompt_token_count", None
            )
            meta["tokens_resposta"] = getattr(usage, "output_tokens", None) or getattr(
                usage, "candidates_token_count", None
            )
            meta["tokens_total"] = getattr(usage, "total_tokens", None)

        return LLMResposta(
            texto=texto.strip(),
            provedor="gemini",
            modelo=modelo,
            meta=meta,
        )
    except Exception:
        return None


def _tentar_groq(prompt: str, modelo: Optional[str] = None) -> Optional[LLMResposta]:
    """
    Tenta gerar resposta via Groq (API compatível com OpenAI).
    Documentação: https://console.groq.com/docs/overview
    """
    api_key = _get_groq_api_key()
    if not api_key:
        return None

    try:
        import requests  # já é dependência em vários módulos
    except Exception:
        return None

    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    modelo_final = modelo or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": modelo_final,
        "messages": [
            {
                "role": "system",
                "content": "Você é um assistente técnico da EPSY Sistemas. Responda de forma objetiva, sem inventar fatos que não estejam no contexto.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": float(os.getenv("GROQ_TEMPERATURE", "0.2")),
        "max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "512")),
    }

    try:
        resp = requests.post(url, json=data, headers=headers, timeout=60)
        if resp.status_code != 200:
            return None
        payload = resp.json()
        choices = payload.get("choices") or []
        if not choices:
            return None
        mensagem = choices[0].get("message", {}) or {}
        texto = (mensagem.get("content") or "").strip()

        usage = payload.get("usage") or {}
        meta: Dict[str, Any] = {
            "tokens_prompt": usage.get("prompt_tokens"),
            "tokens_resposta": usage.get("completion_tokens"),
            "tokens_total": usage.get("total_tokens"),
        }

        return LLMResposta(
            texto=texto,
            provedor="groq",
            modelo=modelo_final,
            meta=meta,
        )
    except Exception:
        return None


def gerar_resposta(pergunta: str, contexto: str = "") -> LLMResposta:
    """
    Roteia a chamada de LLM:
    1. Tenta Gemini, se GEMINI_API_KEY estiver configurado e o pacote existir.
    2. Se falhar ou estiver indisponível, tenta Groq se GROQ_API_KEY estiver configurado.
    3. Em último caso, retorna mensagem padrão sem chamar nenhuma API.

    Exemplo de uso na aba do Assistente (substituindo o bloco atual):

        from services.llm_router import gerar_resposta
        prompt = f\"Responda diretamente. DÚVIDA: {pergunta}\\n\\nCONTEXTO:\\n{texto_contexto}\"
        resp = gerar_resposta(pergunta=pergunta, contexto=texto_contexto)
        st.markdown(resp.texto)
        # meta de tokens em resp.meta
    """
    pergunta = (pergunta or "").strip()
    contexto = (contexto or "").strip()

    if contexto:
        prompt = f"Responda diretamente em português do Brasil.\n\nDÚVIDA: {pergunta}\n\nCONTEXTO (não cite literalmente, apenas use para fundamentar):\n{contexto}"
    else:
        prompt = f"Responda diretamente em português do Brasil à seguinte dúvida:\n\n{pergunta}"

    # 1) Tenta Gemini
    resposta = _tentar_gemini(prompt)
    if resposta and resposta.texto:
        return resposta

    # 2) Fallback: Groq
    resposta = _tentar_groq(prompt)
    if resposta and resposta.texto:
        return resposta

    # 3) Fallback final – sem LLM
    texto = (
        "Neste momento o motor de IA não está disponível. "
        "Use os resultados da busca nos manuais e wikis como referência."
    )
    return LLMResposta(
        texto=texto,
        provedor="nenhum",
        modelo="offline",
        meta={},
    )

