import time
import os
from dotenv import load_dotenv
from datetime import datetime
from selenium import webdriver
from config import Config 
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
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
URL_LOGIN = "https://postogestor.com.br/helpdesk/sistema/login"
URL_HOME = "https://postogestor.com.br/helpdesk/sistema/home"
URL_PLANTOES = "https://postogestor.com.br/helpdesk/sistema/plantao" 
URL_TICKETS = "https://postogestor.com.br/helpdesk/sistema/tickets" 
URL_MANUAIS = "https://postogestor.com.br/helpdesk/sistema/manuais/busca" 
URL_WIKI = "https://postogestor.com.br/helpdesk/sistema/wiki"

# INSIRA AQUI AS CREDENCIAIS DE UM USUÁRIO COM ACESSO A TUDO NO HELPDESK
USUARIO_HELPDESK = "rafaeln"
SENHA_HELPDESK = ""

class MotorExtracao:
    def __init__(self):
        self.oraculo = OraculoLogistica()
        self.driver = None

    def iniciar_navegador(self):
        print(f"🌐 Iniciando Navegador... (Headless: {Config.MODO_HEADLESS})")
        chrome_options = Options()
        
        # Ajusta o modo headless com base na configuração do .env (True/False)
        if Config.MODO_HEADLESS:
            chrome_options.add_argument("--headless")
            
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        # ...
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(10)

    def fazer_login(self):
        print("🔐 Autenticando no PostoGestor HelpDesk...")
        self.driver.get(URL_LOGIN)
        
        try:
            # 1. Espera a chave mestra (campo de usuário) aparecer na tela
            campo_usuario = WebDriverWait(self.driver, 20).until(
                EC.visibility_of_element_located((By.NAME, "userdata[user]"))
            )
            
            # 2. Localiza a senha e o botão com precisão cirúrgica
            campo_senha = self.driver.find_element(By.NAME, "userdata[pass]")
            btn_login = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            
            # 3. Digita e entra
            campo_usuario.send_keys(Config.TECNUV_USER)
            campo_senha.send_keys(Config.TECNUV_PASS)
            btn_login.click()
            
            # 4. Aguarda a página mudar (sinal de que o login foi aceite)
            WebDriverWait(self.driver, 10).until(
                EC.url_changes(URL_LOGIN)
            )
            
            print("✅ Login realizado com sucesso! Estamos dentro do sistema.")
            return True
            
        except Exception as e:
            print(f"❌ Falha no login: O Fantasma não conseguiu entrar. Erro: {e}")
            return False

    # 1. COLE A NOVA FUNÇÃO AQUI:
    def extrair_releases(self):
        print("📦 Lendo janelas de Releases...")
        try:
            # Encontra todos os links de releases na tela Home
            links_releases = self.driver.find_elements(By.CLASS_NAME, "loadNoticia")
            
            for link in links_releases:
                link.click() # O Selenium clica para abrir a janela
                
                # Espera a janela abrir e o texto aparecer
                textarea = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "msg3-noticia"))
                )
                
                titulo_release = self.driver.find_element(By.CLASS_NAME, "msg1-noticia").text
                texto_release = textarea.get_attribute("value") 
                
                import re
                chamados_citados = re.findall(r'\((\d+)\)', texto_release)
                
                print(f"✅ Versão: {titulo_release} | Chamados Corrigidos: {chamados_citados}")
                
                # Fecha a janela para não dar erro no próximo clique
                btn_fechar = self.driver.find_element(By.CSS_SELECTOR, "div.modal-header button.close")
                btn_fechar.click()
                time.sleep(1) # Respiro para a animação do site
                
        except Exception as e:
            print(f"❌ Erro ao ler os Releases: {e}")

    # 2. AGORA, AJUSTE A FUNÇÃO PRINCIPAL:
    def raspar_todas_as_fontes(self):
        try:
            # 1. Releases (Página Home) - LÓGICA NOVA COM CLIQUES
            print("\n📥 Acessando Home (Releases)...")
            self.driver.get("https://postogestor.com.br/helpdesk/home") # Use sua URL_HOME real
            time.sleep(3) 
            
            # Em vez de mandar o HTML cego para o oráculo, mandamos o motor clicar nas janelas!
            self.extrair_releases()
            
            # 2. Plantões (Mantém igual)
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