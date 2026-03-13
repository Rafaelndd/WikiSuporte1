"""
Serviço de embeddings para classificação semântica de chamados.
Suporta OpenAI (1536) e Gemini (768) via variável EMBEDDING_MODEL no .env.
Reutiliza vector_db quando usar Gemini.
"""
import os
import re
import logging
from typing import List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Dimensão por modelo (para compatibilidade com migração)
DIM_OPENAI = 1536
DIM_GEMINI = 768


def _limpar_html(html_text: Optional[str]) -> str:
    if not html_text or str(html_text).strip() == "":
        return ""
    try:
        from modules.html_texto import limpar_html_bruto

        return limpar_html_bruto(html_text)
    except Exception:
        soup = BeautifulSoup(str(html_text), "html.parser")
        texto = soup.get_text(separator=" ")
        return re.sub(r"\s+", " ", texto).strip()


def _texto_chamado(assunto_html: Optional[str], motivo_abertura: Optional[str]) -> str:
    """Concatena e limpa os campos usados para classificação."""
    a = _limpar_html(assunto_html or "")
    m = _limpar_html(motivo_abertura or "")
    return (a + " " + m).strip() or "Sem descrição"


def generate_embedding(texto: str, dimensao: Optional[int] = None) -> Optional[List[float]]:
    """
    Gera embedding para o texto.
    Modelo e dimensão vêm do .env: EMBEDDING_MODEL=openai|gemini.
    openai -> 1536 (text-embedding-3-small), gemini -> 768 (text-embedding-004).
    Retorna lista de floats ou None em caso de falha.
    """
    from dotenv import load_dotenv
    load_dotenv()
    modelo = (os.getenv("EMBEDDING_MODEL") or "gemini").strip().lower()
    dim = dimensao or (DIM_OPENAI if modelo == "openai" else DIM_GEMINI)

    if modelo == "openai":
        return _embedding_openai(texto, dim)
    return _embedding_gemini(texto)


def _embedding_openai(texto: str, dim: int = DIM_OPENAI) -> Optional[List[float]]:
    try:
        import openai
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY não configurada.")
            return None
        client = openai.OpenAI(api_key=api_key)
        # text-embedding-3-small retorna 1536
        resp = client.embeddings.create(
            model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            input=texto[:8191],
        )
        emb = resp.data[0].embedding
        if len(emb) != dim and dim == DIM_OPENAI:
            return emb  # aceita o que vier
        return emb
    except Exception as e:
        logger.exception("Erro ao gerar embedding OpenAI: %s", e)
        return None


def _embedding_gemini(texto: str) -> Optional[List[float]]:
    try:
        from services.vector_db import gerar_embedding_gemini
        return gerar_embedding_gemini(texto)
    except Exception as e:
        logger.exception("Erro ao gerar embedding Gemini: %s", e)
        return None


def get_embedding_dim() -> int:
    """Retorna a dimensão do embedding conforme .env (para chamados: 1536 ou 768)."""
    from dotenv import load_dotenv
    load_dotenv()
    modelo = (os.getenv("EMBEDDING_MODEL") or "gemini").strip().lower()
    return DIM_OPENAI if modelo == "openai" else DIM_GEMINI
