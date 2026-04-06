"""
Ingestão inteligente de manuais para a Base de Conhecimento.

Objetivo:
- Ler manuais da tabela base_conhecimento (origem MANUAL_HELPDESK) que hoje têm só URL.
- Baixar os arquivos, armazenar localmente e extrair texto.
- Enriquecer o conteúdo com tópicos/assuntos identificados.
- Persistir no banco para que o sistema "conheça" o manual.
- Opcionalmente indexar no pgvector para busca semântica RAG.

Uso:
    python scripts/ingestao_manuais_base_conhecimento.py
    python scripts/ingestao_manuais_base_conhecimento.py --limit 200 --force
    python scripts/ingestao_manuais_base_conhecimento.py --skip-embedding
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from pypdf import PdfReader
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.database import get_connection
from services.vector_db import criar_extensao_e_tabela, indexar_documento

BASE_HELPDESK_PADRAO = os.getenv("TECNUV_BASE_URL", "https://postogestor.com.br")
PASTA_DESTINO = Path("uploads_wiki/manuais_ingestao")
MARCADOR_TEXTO = "[TEXTO_EXTRAIDO_MANUAL]"
MARCADOR_ASSUNTOS = "[ASSUNTOS_IDENTIFICADOS]"

STOPWORDS_PT = {
    "para",
    "como",
    "com",
    "sem",
    "por",
    "uma",
    "uns",
    "umas",
    "que",
    "dos",
    "das",
    "nos",
    "nas",
    "aos",
    "aas",
    "ser",
    "ter",
    "sua",
    "seu",
    "seus",
    "suas",
    "cada",
    "apos",
    "sobre",
    "desde",
    "entre",
    "quando",
    "onde",
    "qual",
    "quais",
    "este",
    "esta",
    "esse",
    "essa",
    "isso",
    "tambem",
    "mais",
    "menos",
    "muito",
    "pouco",
    "manual",
    "sistema",
    "usuario",
    "usuarios",
    "pagina",
    "tela",
    "menu",
}


def _normalizar_texto(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt or "")
    t = t.replace("\x00", " ")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _extrair_url(registro_conteudo: str | None, caminho_anexo: str | None) -> str | None:
    conteudo = (registro_conteudo or "").strip()
    if conteudo:
        m = re.search(r"URL_DOCUMENTO:\s*(\S+)", conteudo, flags=re.I)
        if m:
            return m.group(1).strip()
        m_any = re.search(r"https?://\S+", conteudo)
        if m_any:
            return m_any.group(0).strip()

    anexo = (caminho_anexo or "").strip()
    if anexo and (anexo.startswith("http://") or anexo.startswith("https://")):
        return anexo
    return None


def _url_absoluta(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(BASE_HELPDESK_PADRAO, url)


def _inferir_extensao(url: str, content_type: str | None) -> str:
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return ".pdf"
    if "text/plain" in ct:
        return ".txt"
    if "html" in ct:
        return ".html"
    p = urlparse(url).path.lower()
    if "." in p:
        ext = "." + p.rsplit(".", 1)[-1]
        if len(ext) <= 6:
            return ext
    return ".bin"


def _baixar_arquivo(url: str, timeout: int) -> tuple[bytes | None, str]:
    try:
        r = requests.get(url, timeout=timeout)
    except Exception as ex:
        return None, f"erro de conexão: {ex}"
    if r.status_code != 200:
        return None, f"http {r.status_code}"
    if not r.content:
        return None, "resposta vazia"
    return r.content, (r.headers.get("content-type") or "")


def _extrair_texto_pdf(raw: bytes, max_pages: int = 120) -> str:
    from io import BytesIO

    partes: list[str] = []
    reader = PdfReader(BytesIO(raw))
    for page in reader.pages[: max(1, int(max_pages))]:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            partes.append(txt)
    return "\n\n".join(partes).strip()


def _extrair_texto_generico(raw: bytes, ext: str, max_pages: int = 120) -> str:
    ext = (ext or "").lower()
    if ext == ".pdf":
        return _extrair_texto_pdf(raw, max_pages=max_pages)
    if ext in {".txt", ".md", ".csv", ".sql", ".xml", ".json", ".html"}:
        return raw.decode("utf-8", errors="ignore").replace("\x00", " ").strip()
    return ""


def _sanitizar_para_banco(txt: str) -> str:
    """
    Remove caracteres inválidos para persistência no PostgreSQL.
    O principal é NUL (0x00), que causa ValueError no driver.
    """
    if not txt:
        return ""
    return txt.replace("\x00", " ").strip()


def _topicos_relevantes(texto: str, limite: int = 12) -> list[str]:
    limpo = _normalizar_texto(texto).lower()
    tokens = re.findall(r"[a-z0-9]{4,}", limpo)
    filtrados = [t for t in tokens if t not in STOPWORDS_PT and not t.isdigit()]
    if not filtrados:
        return []
    freq = Counter(filtrados)
    return [t for t, _ in freq.most_common(limite)]


def _resumo_inicial(texto: str, tamanho: int = 1200) -> str:
    base = _normalizar_texto(texto)
    if len(base) <= tamanho:
        return base
    return base[: tamanho - 3].rstrip() + "..."


def _montar_conteudo_enriquecido(
    url: str,
    texto_extraido: str,
    assuntos: Iterable[str],
) -> str:
    assuntos_fmt = ", ".join(assuntos) if assuntos else "não identificados automaticamente"
    texto_limpo = _sanitizar_para_banco(texto_extraido)
    resumo = _resumo_inicial(texto_limpo, 1400)
    return (
        f"URL_DOCUMENTO: {url}\n\n"
        f"{MARCADOR_ASSUNTOS}:\n{assuntos_fmt}\n\n"
        f"[RESUMO_MANUAL]:\n{resumo}\n\n"
        f"{MARCADOR_TEXTO}:\n{texto_limpo}"
    )


def executar(
    limit: int,
    force: bool,
    skip_embedding: bool,
    timeout: int,
    max_pages: int,
    after_id: int,
) -> None:
    engine = get_connection()
    PASTA_DESTINO.mkdir(parents=True, exist_ok=True)

    if not skip_embedding:
        try:
            criar_extensao_e_tabela()
        except Exception:
            pass

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, nr_documento, titulo, conteudo, caminho_anexo
                FROM base_conhecimento
                WHERE origem = 'MANUAL_HELPDESK'
                  AND status = 'APROVADO'
                  AND id > :after_id
                  AND (
                    :force = TRUE
                    OR conteudo IS NULL
                    OR conteudo = ''
                    OR conteudo LIKE 'URL_DOCUMENTO:%'
                    OR conteudo NOT LIKE :marcador
                  )
                ORDER BY id
                LIMIT :lim
                """
            ),
            {
                "lim": int(limit),
                "force": bool(force),
                "marcador": f"%{MARCADOR_TEXTO}%",
                "after_id": max(0, int(after_id)),
            },
        ).fetchall()

    if not rows:
        print("Nenhum manual elegível para ingestão.")
        return

    total = len(rows)
    ok = 0
    sem_texto = 0
    falhas = 0
    indexados = 0

    try:
        for row in rows:
            bc_id = int(row[0])
            nr_doc = row[1]
            titulo = str(row[2] or f"Manual {bc_id}")
            conteudo = row[3]
            caminho_anexo = row[4]

            print(f"[{bc_id}] iniciando ingestão (nr={nr_doc})...", flush=True)

            url_raw = _extrair_url(conteudo, caminho_anexo)
            if not url_raw:
                falhas += 1
                print(f"[{bc_id}] sem URL detectável em conteudo/caminho_anexo", flush=True)
                continue

            url = _url_absoluta(url_raw)
            print(f"[{bc_id}] baixando arquivo...", flush=True)
            raw, info = _baixar_arquivo(url, timeout=timeout)
            if not raw:
                falhas += 1
                print(f"[{bc_id}] falha no download ({info}) -> {url}", flush=True)
                continue

            ext = _inferir_extensao(url, info)
            pasta_item = PASTA_DESTINO / str(bc_id)
            pasta_item.mkdir(parents=True, exist_ok=True)
            nome_arquivo = f"manual_{bc_id}{ext}"
            caminho_local = pasta_item / nome_arquivo
            caminho_local.write_bytes(raw)
            print(f"[{bc_id}] arquivo salvo em {caminho_local}", flush=True)

            print(f"[{bc_id}] extraindo texto...", flush=True)
            texto_extraido = _extrair_texto_generico(raw, ext, max_pages=max_pages)
            if not texto_extraido.strip():
                sem_texto += 1
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            UPDATE base_conhecimento
                            SET caminho_anexo = :ax,
                                atualizado_em = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {"ax": str(caminho_local), "id": bc_id},
                    )
                print(f"[{bc_id}] arquivo salvo, mas sem texto extraível ({ext})", flush=True)
                continue

            assuntos = _topicos_relevantes(texto_extraido)
            novo_conteudo = _montar_conteudo_enriquecido(url, texto_extraido, assuntos)

            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE base_conhecimento
                        SET conteudo = :cont,
                            caminho_anexo = :ax,
                            atualizado_em = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"cont": novo_conteudo, "ax": str(caminho_local), "id": bc_id},
                )
            ok += 1
            print(
                f"[{bc_id}] ok | nr={nr_doc} | assuntos={', '.join(assuntos[:6]) if assuntos else '-'}",
                flush=True,
            )

            if not skip_embedding:
                try:
                    print(f"[{bc_id}] indexando embedding (RAG)...", flush=True)
                    indexar_documento(
                        id_conhecimento=bc_id,
                        titulo=titulo,
                        origem="MANUAL_HELPDESK",
                        conteudo=novo_conteudo,
                        usar_gemini=True,
                    )
                    indexados += 1
                    print(f"[{bc_id}] embedding concluído.", flush=True)
                except Exception as ex:
                    print(f"[{bc_id}] aviso: não indexado no vetor ({ex})", flush=True)
    except KeyboardInterrupt:
        print("\nInterrompido pelo utilizador (Ctrl+C). Finalizando com segurança...", flush=True)

    print("\n=== RESUMO DA INGESTÃO ===")
    print(f"Registros avaliados: {total}")
    print(f"Manuais enriquecidos no banco: {ok}")
    print(f"Sem texto extraível: {sem_texto}")
    print(f"Falhas: {falhas}")
    if not skip_embedding:
        print(f"Indexados no pgvector: {indexados}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingestão inteligente de manuais para Base de Conhecimento."
    )
    parser.add_argument("--limit", type=int, default=200, help="Quantidade máxima por execução.")
    parser.add_argument("--force", action="store_true", help="Reprocessa mesmo já extraídos.")
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Não indexa no pgvector nesta execução.",
    )
    parser.add_argument(
        "--with-embedding",
        action="store_true",
        help="Ativa indexação vetorial durante a ingestão (pode aumentar bastante o tempo de execução).",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Timeout de download em segundos.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=120,
        help="Limite de páginas por PDF para extração nesta execução.",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Processa apenas registros com id maior que este valor (retomada de execução).",
    )
    args = parser.parse_args()

    skip_embedding = bool(args.skip_embedding or not args.with_embedding)
    if skip_embedding:
        print(
            "Modo padrão: ingestão sem embeddings (mais rápido). "
            "Use --with-embedding para indexar no pgvector durante o processo.",
            flush=True,
        )

    executar(
        limit=max(1, int(args.limit)),
        force=bool(args.force),
        skip_embedding=skip_embedding,
        timeout=max(5, int(args.timeout)),
        max_pages=max(1, int(args.max_pages)),
        after_id=max(0, int(args.after_id)),
    )


if __name__ == "__main__":
    main()

