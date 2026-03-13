"""
Limpeza de HTML vindo do Helpdesk (motivo_abertura_html, assunto_html).
Uso: exibição no Streamlit e gravação limpa pelo bot / migração em lote.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore


def limpar_html_bruto(html: Optional[str]) -> str:
    """Remove tags e entidades; uma linha de texto com espaços normais."""
    if html is None or str(html).strip() == "":
        return ""
    s = str(html)
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(s, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            texto = soup.get_text(separator=" ")
        except Exception:
            texto = re.sub(r"<[^>]+>", " ", s)
    else:
        texto = re.sub(r"<[^>]+>", " ", s)
    # entidades comuns
    texto = (
        texto.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def para_title_case_pt(texto: str) -> str:
    """
    Title case legível: primeira letra de cada palavra maiúscula.
    (Não é camelCase de código; é formato de título para UI.)
    """
    if not texto:
        return ""
    # Normaliza unicode (ex.: ã)
    t = unicodedata.normalize("NFKC", texto.strip())
    partes = []
    for palavra in t.split():
        if not palavra:
            continue
        partes.append(palavra[0].upper() + palavra[1:].lower() if len(palavra) > 1 else palavra.upper())
    return " ".join(partes)


def html_para_exibicao(html: Optional[str], title_case: bool = True) -> str:
    """
    Pipeline: strip HTML → espaços → opcional Title Case.
    Use em dashboards e ao persistir texto vindo do innerHTML do bot.
    """
    t = limpar_html_bruto(html)
    if not t:
        return ""
    return para_title_case_pt(t) if title_case else t
