import logging
from modules.robo_tecnuv import OraculoBot

# ==========================================
# IDENTIDADE VISUAL DO TERMINAL (ASCII ART)
# ==========================================
PSY_ASCII = """
       _____  _______     __
      |  __ \\/ ____\\ \\   / /
      | |__) | (___  \\ \\_/ / 
      |  ___/ \\___ \\  \\   /  
      | |     ____) |  | |   
      |_|    |_____/   |_|   
      
   [Analista de dados e guardião de métricas do suporte]
"""

if __name__ == "__main__":
    # Imprime o rosto/nome do PSY no terminal antes de começar os logs
    print(PSY_ASCII)
    
    logging.info("🚀 Iniciando a rotina do Epsy Central V4.0 sob supervisão do PSY...")
    
    bot = OraculoBot()
    
    # Arquitetura de 3 Fases
    if bot.login():
        if bot.configurar_filtros():
            bot.varrer_tabela()             # Fase 1 e 2
            bot.recuperar_falhas_raspagem() # Fase 3 (Auto-Cura)
    else:
        logging.error("A rotina foi abortada porque o login falhou.")
        
    bot.encerrar()

if __name__ == "__main__":
    """
    Epsy Central V4.0 - Oráculo Bot
    --------------------------------
    Este é o ponto de entrada para a rotina do Oráculo Bot, responsável por:
1. Realizar login seguro e confiável no sistema.
2. Configurar filtros de busca para otimizar a coleta de dados.
3. Varrer a tabela de chamados para coletar informações relevantes.
4. Raspagem de dados com tratamento de exceções para garantir a robustez.
5. Auto-cura de falhas de raspagem, focando nos 19 chamados mais
    problemáticos.
    O código foi estruturado em uma arquitetura de 3 fases para garantir
    eficiência e facilidade de manutenção. Cada fase é modular, permitindo
    melhorias futuras sem impactar o fluxo geral.
    
    """
    logging.info("Iniciando a rotina do Epsy Central V4.0...")
    
    bot = OraculoBot()
    
    
    if bot.login():
        if bot.configurar_filtros():
            bot.varrer_tabela()             # Fase 1 e 2 
            bot.recuperar_falhas_raspagem() # Fase 3
    else:
        logging.error("A rotina foi abortada porque o login falhou.")
        
    bot.encerrar()