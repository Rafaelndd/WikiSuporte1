"""
Domínio: tipos de notificação (sem dependências de BD ou pandas).

Permite testes unitários e reuso sem carregar `system_notifications`.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

TIPOS_VALIDOS = frozenset({"comunicado", "aviso", "erro_critico", "versao_bloqueada"})


def normalizar_tipo_notificacao(raw: str) -> Optional[str]:
    """
    Converte rótulos de UI (ex.: 'Erro Crítico', 'Versão Bloqueada') para a chave
    persistida em `notificacoes_sistema.tipo`.
    """
    t = (raw or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"\s+", "_", t.strip())
    return t if t in TIPOS_VALIDOS else None
