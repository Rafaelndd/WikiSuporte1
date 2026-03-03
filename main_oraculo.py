import logging
import sys
from modules.selenium_raspagem import OraculoBot
from dotenv import load_dotenv

# Carrega variáveis de ambiente logo no início
load_dotenv()

# ==========================================
# IDENTIDADE VISUAL DO TERMINAL (ASCII ART)
# ==========================================
# 🛡️ BLINDAGEM DE INFRAESTRUTURA DOS LOGS
# ==========================================
# 1. Força o terminal do Windows a aceitar Emojis (UTF-8) sem dar erro de encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 2. Configura o Logger com force=True para destruir handlers duplicados e evitar o "Eco"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True,  # 👈 Isto é a mágica que mata as mensagens repetidas!
    handlers=[
        logging.StreamHandler(sys.stdout)
        # Se você salva em arquivo também, adicione a linha abaixo:
        # logging.FileHandler("oraculo_log.txt", encoding='utf-8') 
    ]
)


def executar_oraculo():
    """
    Executa a rotina principal do robô seguindo a arquitetura de 3 fases:
    Fase 1: Coleta de Metadados (RAM)
    Fase 2: Raspagem Profunda (Deep Scrape)
    Fase 3: Auto-Cura e Varredura Retroativa (Versões e Falhas)
    """
    
    logging.info("Iniciando a rotina do Epsy Central V4.0 sob supervisão do PSY...")
    
    # Instancia o bot
    bot = OraculoBot()
    
    try:
        # TENTATIVA DE LOGIN
        if not bot.login():
            logging.error("A rotina foi abortada porque o login falhou.")
            return

        # CONFIGURAÇÃO DE FILTROS (STATUS INDIVIDUAIS)
        if not bot.configurar_filtros():
            logging.error("Falha ao configurar filtros de busca. Abortando.")
            return

        # EXECUÇÃO DAS FASES
        logging.info("Iniciando Fase 1 e 2 (Varrer Tabela e Deep Scrape)...")
        bot.varrer_tabela()
        
        logging.info("Iniciando Fase 3 (Auto-Cura e Captura de Versões)...")
        bot.recuperar_falhas_raspagem()
        
        logging.info("Rotina concluída com sucesso!")

    except Exception as e:
        logging.critical(f"Ocorreu um erro inesperado durante a execução: {e}")
    
    finally:
        # O bloco finally garante que o navegador FECHE mesmo se o código crashar
        logging.info("Encerrando recursos e fechando ChromeDriver...")
        bot.encerrar()

if __name__ == "__main__":
    executar_oraculo()