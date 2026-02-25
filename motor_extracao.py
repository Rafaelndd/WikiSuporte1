import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Importações do nosso ecossistema
from modules.OraculoLogistica import OraculoLogistica
from modules.utils import ler_estado_robo, salvar_estado_robo

# ==========================================
# CONFIGURAÇÕES DE ACESSO (CREDENCIAIS)
# ==========================================
URL_LOGIN = "https://postogestor.com.br/helpdesk/login"
URL_HOME = "https://postogestor.com.br/helpdesk/sistema/home/index"
URL_PLANTOES = "https://postogestor.com.br/helpdesk/sistema/plantao" 
URL_TICKETS = "https://postogestor.com.br/helpdesk/sistema/tickets" 
URL_MANUAIS = "https://postogestor.com.br/helpdesk/sistema/manuais" 
URL_WIKI = "https://postogestor.com.br/helpdesk/sistema/wiki"

# INSIRA AQUI AS CREDENCIAIS DE UM USUÁRIO COM ACESSO A TUDO NO HELPDESK
USUARIO_HELPDESK = "seu_usuario"
SENHA_HELPDESK = "sua_senha"

class MotorExtracao:
    def __init__(self):
        self.oraculo = OraculoLogistica()
        self.driver = None

    def iniciar_navegador(self):
        print("🌐 Iniciando Navegador Fantasma (Headless)...")
        chrome_options = Options()
        chrome_options.add_argument("--headless") # Roda oculto (sem abrir janela)
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)

    def fazer_login(self):
        print("🔐 Autenticando no PostoGestor HelpDesk...")
        self.driver.get(URL_LOGIN)
        
        # Ajuste os 'name' ou 'id' conforme o HTML real da tela de login do Tecnuv
        try:
            campo_usuario = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "usuario")) # Exemplo: name="usuario"
            )
            campo_senha = self.driver.find_element(By.NAME, "senha") # Exemplo: name="senha"
            btn_login = self.driver.find_element(By.TAG_NAME, "button")
            
            campo_usuario.send_keys(USUARIO_HELPDESK)
            campo_senha.send_keys(SENHA_HELPDESK)
            btn_login.click()
            
            # Aguarda a Home carregar para confirmar o login
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "panel-title"))
            )
            print("✅ Login realizado com sucesso!")
            return True
        except Exception as e:
            print(f"❌ Falha no login: {e}")
            return False

    def raspar_todas_as_fontes(self):
        try:
            # 1. Releases (Página Home)
            print("\n📥 Acessando Home (Releases)...")
            self.driver.get(URL_HOME)
            time.sleep(3) # Aguarda os scripts da página carregarem
            self.oraculo.processar_html_releases(self.driver.page_source)
            
            # 2. Plantões
            print("\n📥 Acessando Plantões...")
            self.driver.get(URL_PLANTOES)
            time.sleep(3)
            self.oraculo.processar_html_plantoes(self.driver.page_source)
            
            # 3. Tickets da EPSY
            print("\n📥 Acessando Fila de Tickets...")
            self.driver.get(URL_TICKETS)
            time.sleep(3)
            self.oraculo.processar_html_tickets(self.driver.page_source)
            
            # 4. Manuais
            print("\n📥 Acessando Biblioteca de Manuais...")
            self.driver.get(URL_MANUAIS)
            time.sleep(3)
            self.oraculo.processar_html_manuais(self.driver.page_source)
            
            # 5. Wikis (Com Paginação Básica)
            print("\n📥 Acessando Base de Wikis...")
            self.driver.get(URL_WIKI)
            time.sleep(3)
            # Para raspagem profunda de wikis (todas as páginas), você pode implementar um loop
            # Exemplo: for p in range(1, 4): self.driver.get(f"{URL_WIKI}?pg={p}") ...
            # Aqui enviamos a página atual para o Oráculo (Se você implementou processar_html_wikis)
            try:
                self.oraculo.processar_html_wikis(self.driver.page_source)
            except AttributeError:
                print("⚠️ Método processar_html_wikis ainda não implementado no OraculoLogistica.")
            
        except Exception as e:
            print(f"❌ Erro durante a navegação: {e}")
            
    def fechar(self):
        if self.driver:
            self.driver.quit()
            print("🛑 Navegador Fantasma encerrado.")

# ==========================================
# O DAEMON (MOTOR EM SEGUNDO PLANO)
# ==========================================
def iniciar_daemon():
    print("🤖 Daemon do WikiSuporte Iniciado. Aguardando ordens do painel de controlo...")
    
    while True:
        # Lê o painel de configurações que criámos no Streamlit
        config = ler_estado_robo()
        
        if config.get("auto_ativo", False):
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando ciclo de raspagem...")
            
            # Atualiza o status visual no painel para "A Executar"
            config["em_andamento"] = True
            salvar_estado_robo(config)
            
            motor = MotorExtracao()
            try:
                motor.iniciar_navegador()
                if motor.fazer_login():
                    motor.raspar_todas_as_fontes()
            except Exception as e:
                print(f"Erro Crítico no Motor: {e}")
            finally:
                motor.fechar()
                
                # Atualiza o status visual no painel para "Em Espera"
                config = ler_estado_robo() # Lê de novo para não sobrescrever caso alguém tenha mexido
                config["em_andamento"] = False
                config["ultima_execucao"] = datetime.now().isoformat()
                salvar_estado_robo(config)
                
            intervalo_minutos = config.get("intervalo", 60)
            print(f"⏳ Ciclo concluído. O Fantasma vai dormir por {intervalo_minutos} minutos.")
            time.sleep(intervalo_minutos * 60)
            
        else:
            # Se a chavinha estiver desligada no Streamlit, dorme 1 minuto e verifica novamente
            time.sleep(60)

if __name__ == "__main__":
    iniciar_daemon()