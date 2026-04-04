"""Avatar circular em HTML (data-URI) para uso em ``st.markdown(..., unsafe_allow_html=True)``."""

from __future__ import annotations

import base64
from pathlib import Path


def html_avatar_perfil_circular(
    caminho: str | None,
    tamanho_px: int = 76,
    *,
    fallback_emoji: str = "👤",
) -> str:
    """
    Retorna um ``<img>`` em base64 se o arquivo existir e for legível; caso contrário, um círculo
    com emoji (nunca string vazia, para não quebrar o layout).
    """
    if caminho:
        p = Path(str(caminho).strip())
        if p.is_file():
            try:
                raw = p.read_bytes()
            except OSError:
                pass
            else:
                b64 = base64.b64encode(raw).decode("ascii")
                ext = p.suffix.lower()
                mime = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }.get(ext, "image/jpeg")
                style = (
                    f"width:{tamanho_px}px;height:{tamanho_px}px;border-radius:50%;"
                    "object-fit:cover;border:3px solid #1e5fbf;display:block;margin:0 auto;"
                )
                return (
                    f'<img src="data:{mime};base64,{b64}" alt="Foto de perfil" '
                    f'style="{style}" />'
                )

    fs = max(int(tamanho_px * 0.45), 18)
    div_style = (
        f"width:{tamanho_px}px;height:{tamanho_px}px;border-radius:50%;"
        "background:linear-gradient(145deg,#2d5a8a,#1a3d66);display:flex;align-items:center;"
        f"justify-content:center;font-size:{fs}px;line-height:1;border:3px solid #1e5fbf;"
        "margin:0 auto;box-sizing:border-box;"
    )
    return (
        f'<div style="{div_style}" role="img" aria-label="Avatar padrão">{fallback_emoji}</div>'
    )
