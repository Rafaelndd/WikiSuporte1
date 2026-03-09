import logging
import sys
from modules.selenium_raspagem import OraculoBot  # ⚠️ Confirme o caminho
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)]
)


def executar_oraculo():
    """
    Fluxo principal reestruturado:
    1. Coleta TODOS os abertos no helpdesk (sem filtros)
    2. Compara com o banco e processa diferenças
    3. Auto-Cura para dados faltantes
    """
    logging.info("Iniciando a rotina do Epsy Central V4.0 sob supervisão do PSY...")

    bot = OraculoBot()

    try:
        if not bot.login():
            logging.error("A rotina foi abortada porque o login falhou.")
            return

        # Fase 1: Coleta todos os abertos no helpdesk
        logging.info("Fase 1: Coletando todos os chamados ativos no helpdesk...")
        chamados_helpdesk = bot.coletar_abertos_helpdesk()

        if not chamados_helpdesk:
            logging.warning("Nenhum chamado encontrado no helpdesk. Verifique a conexão.")
            return

        # Fase 2: Compara com banco e processa diferenças
        logging.info("Fase 2: Comparando helpdesk vs banco e processando diferenças...")
        bot.comparar_e_processar(chamados_helpdesk)

        # Fase 3: Auto-Cura
        logging.info("Fase 3: Auto-Cura para dados faltantes...")
        bot.recuperar_falhas_raspagem()

        logging.info("✅ Rotina concluída com sucesso!")

    except Exception as e:
        logging.critical(f"Ocorreu um erro inesperado durante a execução: {e}")

    finally:
        logging.info("Encerrando recursos e fechando ChromeDriver...")
        bot.encerrar()


if __name__ == "__main__":
    executar_oraculo()