"""
Atualiza em lote motivo_abertura_html e assunto_html em chamados_tecnuv:
remove HTML e aplica Title Case (mesma lógica do dashboard).

Uso:
  python scripts/normalizar_html_chamados_tecnuv.py
  python scripts/normalizar_html_chamados_tecnuv.py --dry-run --limit 20
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from modules.database import get_connection
from modules.html_texto import html_para_exibicao


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Não grava no banco")
    ap.add_argument("--limit", type=int, default=0, help="Máx. linhas (0 = todas)")
    args = ap.parse_args()

    engine = get_connection()
    lim = f"LIMIT {int(args.limit)}" if args.limit > 0 else ""

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT nr_chamado, motivo_abertura_html, assunto_html
                FROM chamados_tecnuv
                WHERE (motivo_abertura_html IS NOT NULL AND TRIM(motivo_abertura_html) <> '')
                   OR (assunto_html IS NOT NULL AND TRIM(assunto_html) <> '')
                ORDER BY nr_chamado
                {lim}
            """)
        ).fetchall()

    atualizados = 0
    for nr, mot, ass in rows:
        nm = html_para_exibicao(mot, title_case=True)
        na = html_para_exibicao(ass, title_case=True)
        if nm == (mot or "").strip() and na == (ass or "").strip():
            if "<" not in str(mot or "") + str(ass or ""):
                continue
        if args.dry_run:
            print(nr, "|", (nm or "")[:80], "...")
            atualizados += 1
            continue
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE chamados_tecnuv
                    SET motivo_abertura_html = :m, assunto_html = :a
                    WHERE nr_chamado = :nr
                """),
                {"nr": nr, "m": nm or None, "a": na or nm or None},
            )
        atualizados += 1
        if atualizados % 200 == 0:
            print(f"  ... {atualizados} registros")

    print(f"Concluído. {'(dry-run) ' if args.dry_run else ''}Processados: {atualizados}")


if __name__ == "__main__":
    main()
