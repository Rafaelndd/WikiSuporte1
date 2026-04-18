"""
Teste manual: uma execução do ciclo de chamados TecNuv (fila → comparação → banco → auto-cura).

Uso (na raiz do projeto):
  python scripts/test_raspagem_chamados.py

Requisitos:
  - .env com TECNUV_USER / TECNUV_PASS
  - PostgreSQL acessível (mesma config que o app)
  - Chrome instalado; webdriver_manager baixa o driver se precisar
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.chdir(ROOT)


def main():
    from modules.selenium_raspagem import _executar_ciclo_chamados

    print("=== Teste raspagem Chamados TecNuv (ciclo completo) ===")
    try:
        _executar_ciclo_chamados()
        print("✅ Ciclo concluído. Veja oraculo_engine.log e o banco (chamados_tecnuv, históricos).")
        return 0
    except KeyboardInterrupt:
        print("⚠️ Execução interrompida manualmente (Ctrl+C).")
        return 130
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
