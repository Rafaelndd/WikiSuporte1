"""
Teste manual: uma única execução da raspagem de Releases (Home Helpdesk).

Uso (na raiz do projeto):
  python scripts/test_raspagem_releases.py

Requisitos:
  - .env com TECNUV_USER / TECNUV_PASS (via config.Config)
  - Chrome instalado; webdriver_manager baixa o driver se precisar
"""
import os
import sys

# Raiz do projeto no path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


def main():
    from motor_extracao import MotorExtracao

    print("=== Teste raspagem Releases (uma vez) ===")
    m = MotorExtracao()
    try:
        m.iniciar_navegador()
        if not m.fazer_login():
            print("❌ Login falhou. Verifique TECNUV_USER / TECNUV_PASS no .env")
            return 1
        m.raspar_releases()
        print("✅ Raspagem finalizada. Confira o console acima e o banco (releases / ciclos_homologacao).")
        return 0
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        try:
            m.fechar()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main() or 0)
