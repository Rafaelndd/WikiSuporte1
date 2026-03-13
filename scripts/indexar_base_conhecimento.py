"""
Indexa a base de conhecimento (base_conhecimento) no banco vetorial (pgvector).
Usa services.vector_db.indexar_base_conhecimento.

Uso:
    python scripts/indexar_base_conhecimento.py

Execute após:
- carregar manuais (OraculoLogistica) e
- extrair texto dos PDFs com extrair_texto_manuais_pdf.py.
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.vector_db import indexar_base_conhecimento

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    # Indexa apenas manuais e wikis por padrão; ajuste se quiser outras origens.
    origens = ["MANUAL_HELPDESK", "WIKI_HELPDESK"]
    total_chunks = indexar_base_conhecimento(origens=origens, limite=500)
    logging.info("Indexação concluída. Chunks indexados/atualizados: %s", total_chunks)
    print(f"Chunks indexados/atualizados: {total_chunks}")


if __name__ == "__main__":
    main()

