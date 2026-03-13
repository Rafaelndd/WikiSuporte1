"""
Extrai texto dos PDFs de manuais (MANUAL_HELPDESK) e atualiza base_conhecimento.conteudo.
Fluxo:
- Lê registros de base_conhecimento com origem='MANUAL_HELPDESK' cujo conteudo começa com 'URL_DOCUMENTO:'.
- Faz download do PDF, extrai texto com pypdf.
- Se extrair algum texto, grava em conteudo (mantendo a URL no topo para referência).
- Se não extrair texto (apenas imagem), registra no log para tratamento futuro (OCR externo).

Uso:
    python scripts/extrair_texto_manuais_pdf.py

Rode em lotes ao longo de 3 dias até zerar a fila.
"""
import os
import sys
import logging
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from sqlalchemy import text
from pypdf import PdfReader

from modules.database import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def _engine():
    return get_connection()


def _baixar_pdf(url: str, timeout: int = 30) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            return resp.content
        logging.warning("Falha ao baixar PDF (%s): HTTP %s", url, resp.status_code)
    except Exception as e:
        logging.warning("Erro ao baixar PDF (%s): %s", url, e)
    return None


def _extrair_texto_pdf(raw: bytes) -> str:
    try:
        from io import BytesIO

        reader = PdfReader(BytesIO(raw))
        partes: list[str] = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt.strip():
                partes.append(txt)
        return "\n\n".join(partes).strip()
    except Exception as e:
        logging.warning("Erro ao processar PDF em memória: %s", e)
        return ""


def main(batch_size: int = 50):
    engine = _engine()
    # Busca manuais cujo conteudo é apenas a URL (formato atual do OraculoLogistica)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, nr_documento, titulo, conteudo
                FROM base_conhecimento
                WHERE origem = 'MANUAL_HELPDESK'
                  AND conteudo LIKE 'URL_DOCUMENTO:%'
                ORDER BY id
                LIMIT :lim
                """
            ),
            {"lim": batch_size},
        ).fetchall()
    if not rows:
        print("Nenhum manual pendente de extração de texto.")
        return

    logging.info("Iniciando extração de texto para %s manuais...", len(rows))
    processados = 0
    vazios = 0
    for row in rows:
        bc_id, nr_doc, titulo, conteudo = row
        url = str(conteudo or "").replace("URL_DOCUMENTO:", "").strip()
        if not url:
            logging.warning("Manual id=%s nr=%s sem URL_DOCUMENTO válida.", bc_id, nr_doc)
            continue

        # Se a URL for relativa, prefixe com o domínio padrão do helpdesk
        if url.startswith("/"):
            base = os.getenv("TECNUV_BASE_URL", "https://postogestor.com.br")
            url_final = urljoin(base, url)
        else:
            url_final = url

        logging.info("Manual %s (%s) -> %s", nr_doc, titulo, url_final)

        raw = _baixar_pdf(url_final)
        if not raw:
            continue

        texto = _extrair_texto_pdf(raw)
        if not texto:
            vazios += 1
            logging.info("Manual %s: PDF sem texto extraível (imagem / scan).", nr_doc)
            continue

        novo_conteudo = f"URL_DOCUMENTO: {url_final}\n\n[TEXTO_EXTRAIDO_PDF]:\n{texto}"
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE base_conhecimento
                    SET conteudo = :cont, atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {"cont": novo_conteudo, "id": bc_id},
            )
        processados += 1

    logging.info(
        "Extração concluída. Processados: %s, PDFs sem texto (imagem): %s",
        processados,
        vazios,
    )


if __name__ == "__main__":
    main()

