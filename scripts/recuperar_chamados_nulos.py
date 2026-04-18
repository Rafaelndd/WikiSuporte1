"""
Executa somente a recuperação de chamados com dados faltantes (NULL/vazio).

Uso:
  python scripts/recuperar_chamados_nulos.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


def main() -> int:
    from modules.selenium_raspagem import OraculoBot

    print("=== Recuperação de chamados com dados faltantes ===")
    bot = None
    try:
        bot = OraculoBot()
        bot.recuperar_falhas_raspagem()
        print("✅ Recuperação concluída.")
        return 0
    except Exception as e:
        print(f"❌ Erro na recuperação: {e}")
        return 1
    finally:
        if bot:
            try:
                bot.encerrar()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
