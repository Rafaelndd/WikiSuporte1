"""
Indexa a Base de Conhecimento no banco vetorial (pgvector).
Usa services.vector_db.indexar_base_conhecimento.

Uso:
    python scripts/indexar_base_conhecimento.py
    python scripts/indexar_base_conhecimento.py --limit 200 --after-id 79
"""
import os
import sys
import logging
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.vector_db import indexar_base_conhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="Indexação vetorial da Base de Conhecimento (pgvector).")
    parser.add_argument("--limit", type=int, default=500, help="Quantidade máxima de documentos por execução.")
    parser.add_argument("--after-id", type=int, default=0, help="Processa apenas IDs maiores que este valor.")
    parser.add_argument(
        "--origens",
        type=str,
        default="MANUAL_HELPDESK,WIKI_HELPDESK",
        help="Origens separadas por vírgula. Ex.: MANUAL_HELPDESK,WIKI_HELPDESK",
    )
    parser.add_argument(
        "--progress-step",
        type=int,
        default=10,
        help="Imprime progresso a cada N documentos (0 desativa).",
    )
    args = parser.parse_args()

    # Indexa apenas manuais e wikis por padrão; ajuste se quiser outras origens.
    origens = [o.strip() for o in str(args.origens).split(",") if o.strip()]
    logging.info(
        "Iniciando indexação vetorial | origens=%s | limit=%s | after_id=%s",
        origens,
        args.limit,
        args.after_id,
    )
    total_chunks = indexar_base_conhecimento(
        origens=origens,
        limite=max(1, int(args.limit)),
        after_id=max(0, int(args.after_id)),
        progress_step=max(0, int(args.progress_step)),
    )
    logging.info("Indexação concluída. Chunks indexados/atualizados: %s", total_chunks)
    print(f"Chunks indexados/atualizados: {total_chunks}")


if __name__ == "__main__":
    main()

