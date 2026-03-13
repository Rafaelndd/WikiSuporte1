"""
Script para classificar chamados antigos (sem embedding/categoria_ia) em lote.
Categorias: Erro, Melhoria, Adequação Fiscal.
Uso: python scripts/classificar_chamados_antigos.py
Requer: migracao_vector_chamados.sql aplicada e GEMINI_API_KEY ou OPENAI_API_KEY no .env.
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

from sqlalchemy import text
from modules.database import get_connection
from services.classificacao_chamados import classificar_chamado

BATCH_SIZE = 100


def main():
    engine = get_connection()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT nr_chamado
                FROM chamados_tecnuv
                WHERE (embedding IS NULL OR categoria_ia IS NULL)
                  AND (assunto_html IS NOT NULL OR motivo_abertura_html IS NOT NULL)
                  AND TRIM(COALESCE(assunto_html, '') || ' ' || COALESCE(motivo_abertura_html, '')) != ''
                ORDER BY nr_chamado
                LIMIT :lim
                """
            ),
            {"lim": BATCH_SIZE},
        ).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        print("Nenhum chamado pendente de classificação.")
        return
    print(f"Classificando {len(ids)} chamados (lote de até {BATCH_SIZE})...")
    ok_count = 0
    for nr in ids:
        try:
            sucesso, categoria, dist = classificar_chamado(nr)
            if sucesso:
                ok_count += 1
                print(f"  {nr}: {categoria} (dist={dist:.4f})")
        except Exception as e:
            logging.warning("Chamado %s: %s", nr, e)
    print(f"Concluído: {ok_count}/{len(ids)} classificados.")


if __name__ == "__main__":
    main()
