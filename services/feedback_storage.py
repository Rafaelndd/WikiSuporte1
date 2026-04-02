"""
Persistência local de feedbacks em WikiFeedbacks/<data>__<tipo>__<assunto>/.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PASTA_FEEDBACKS = "WikiFeedbacks"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _slug_assunto(texto: str, max_len: int = 45) -> str:
    t = (texto or "").strip().lower()
    t = re.sub(r"[^\w\s\u00C0-\u024F-]", "", t, flags=re.UNICODE)
    t = re.sub(r"[-\s_]+", "_", t).strip("_")
    if not t:
        t = "sem_assunto"
    return t[:max_len]


def _slug_tipo(tipo: str) -> str:
    t = (tipo or "feedback").strip()
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t, flags=re.UNICODE).strip("_")
    return (t or "feedback")[:35]


@dataclass
class FeedbackRecord:
    criado_em: str
    tipo: str
    assunto: str
    mensagem: str
    email_retorno: str
    usuario_nome: str
    usuario_id: Optional[int]
    pasta: str


def save_feedback_to_disk(
    *,
    tipo_feedback: str,
    assunto: str,
    mensagem: str,
    email_retorno: str = "",
    usuario_nome: str = "",
    usuario_id: Optional[int] = None,
    base_dir: Optional[Path] = None,
) -> Tuple[bool, str, Optional[Path]]:
    """
    Grava feedback em disco. Retorna (ok, mensagem, caminho_da_pasta_criada).
    """
    root = base_dir or _project_root()
    pasta_raiz = root / PASTA_FEEDBACKS
    try:
        pasta_raiz.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Não foi possível criar a pasta {PASTA_FEEDBACKS}: {e}", None

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    nome_pasta = f"{stamp}__{_slug_tipo(tipo_feedback)}__{_slug_assunto(assunto)}"
    destino = pasta_raiz / nome_pasta
    suffix = 0
    while destino.exists():
        suffix += 1
        destino = pasta_raiz / f"{nome_pasta}_{suffix}"

    try:
        destino.mkdir(parents=False)
    except OSError as e:
        return False, f"Não foi possível criar a pasta do feedback: {e}", None

    record = FeedbackRecord(
        criado_em=datetime.now().isoformat(timespec="seconds"),
        tipo=tipo_feedback,
        assunto=assunto.strip(),
        mensagem=mensagem.strip(),
        email_retorno=(email_retorno or "").strip(),
        usuario_nome=(usuario_nome or "").strip(),
        usuario_id=usuario_id,
        pasta=str(destino.relative_to(root)),
    )
    payload: Dict[str, Any] = asdict(record)

    json_path = destino / "feedback.json"
    txt_path = destino / "feedback.txt"
    try:
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        linhas = [
            f"Data: {record.criado_em}",
            f"Tipo: {record.tipo}",
            f"Assunto: {record.assunto}",
            f"Usuário: {record.usuario_nome or '-'} (id {record.usuario_id if record.usuario_id is not None else '-'})",
            f"E-mail para retorno: {record.email_retorno or '(não informado)'}",
            "",
            "--- Descrição ---",
            record.mensagem,
            "",
        ]
        txt_path.write_text("\n".join(linhas), encoding="utf-8")
    except OSError as e:
        return False, f"Falha ao gravar arquivos: {e}", None

    rel = destino.relative_to(root)
    return True, f"Feedback salvo em `{rel}`", destino
