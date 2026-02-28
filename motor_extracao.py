import time
import os
import re
import logging
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
                
    
                chamados_citados = re.findall(r'\((\d+)\)', texto_release)
                
                print(f"✅ Versão: {titulo_release} | Chamados Corrigidos: {chamados_citados}")
                
                # Fecha a janela para não dar erro no próximo clique
                btn_fechar = self.driver.find_element(By.CSS_SELECTOR, "div.modal-header button.close")
                btn_fechar.click()
                time.sleep(1) # Respiro para a animação do site
                
        except Exception as e:
            print(f"❌ Erro ao ler os Releases: {e}")

    def extrair_todos_os_tickets(self):
        print("\n📥 Acessando Fila de Tickets (Iniciando Sincronização Delta)...")
        url_base_tickets = "https://postogestor.com.br/helpdesk/?path=sistema/tickets" 
        
        try:
            self.driver.get(url_base_tickets)
            time.sleep(3) 
            
            print("⚙️ Injetando script para selecionar TODOS os 11 status...")
            self.driver.execute_script("""
                $('#ticket_status option').prop('selected', true);
                $('#ticket_status').multiselect('refresh');
            """)
            time.sleep(1)
            
            print("⏳ Pressionando o botão de Busca para carregar a base completa...")
            btn_busca = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "btnBusca"))
            )
            btn_busca.click()
            time.sleep(5) 
            
            html_atual = self.driver.page_source
            match_paginas = re.search(r'Nº de páginas:.*?<font[^>]*>(\d+)</font>', html_atual, re.DOTALL)
            
            if match_paginas:
                total_paginas = int(match_paginas.group(1))
                print(f"📊 Sucesso! O Fantasma detetou {total_paginas} páginas de Tickets.")
            else:
                total_paginas = 1
                
            # ==========================================
            # 🛑 CONTROLE DE SAÍDA ANTECIPADA (Early Exit)
            # ==========================================
            paginas_sem_mudanca_consecutivas = 0
            LIMITE_PAGINAS_INALTERADAS = 2  # Se ler 2 páginas seguidas sem novidades, ele para!

            for pagina_atual in range(1, total_paginas + 1):
                print(f"📄 Extraindo Página {pagina_atual} de {total_paginas}...")
                
                if pagina_atual > 1:
                    url_paginada = f"{url_base_tickets}&pg={pagina_atual}"
                    self.driver.get(url_paginada)
                    time.sleep(4) 
                    
                html_pagina = self.driver.page_source
                
                # Captura a resposta do Oráculo
                estatisticas = self.oraculo.processar_html_tickets(html_pagina)
                
                # Se não houve nenhum ticket inserido e nenhum atualizado...
                if estatisticas["inseridos"] == 0 and estatisticas["atualizados"] == 0:
                    paginas_sem_mudanca_consecutivas += 1
                    print(f"💤 Tudo igual! Páginas inalteradas seguidas: {paginas_sem_mudanca_consecutivas}")
                else:
                    # Achou algo novo? Zera o contador e continua animado!
                    paginas_sem_mudanca_consecutivas = 0 
                    
                # A MÁGICA ACONTECE AQUI:
                if paginas_sem_mudanca_consecutivas >= LIMITE_PAGINAS_INALTERADAS:
                    print("🛑 SINCRONIZAÇÃO DELTA CONCLUÍDA! O robô atingiu o histórico antigo e encerrou a paginação para poupar recursos.")
                    break # Estilhaça o loop e sai da função!
                
            print("✅ Processo de Tickets finalizado com excelência!")
            
        except Exception as e:
            print(f"❌ Erro ao tentar paginar os Tickets: {e}")


    # 2. AGORA, AJUSTE A FUNÇÃO PRINCIPAL:
    def raspar_todas_as_fontes(self):
        try:
            # 1. Releases (Página Home) - LÓGICA NOVA COM CLIQUES
            print("\n📥 Acessando Home (Releases)...")            
            self.driver.get("https://postogestor.com.br/helpdesk/home")
            time.sleep(3) 
            # Em vez de mandar o HTML cego para o oráculo, mandamos o motor clicar nas janelas!
            self.extrair_releases()
            
            # 2. Plantões (Mantém igual)
            print("\n📥 Acessando Plantões...")
            self.driver.get(URL_PLANTOES)
            time.sleep(3)
            self.oraculo.processar_html_plantoes(self.driver.page_source)
            
            # 3. Tickets da EPSY (Nova Lógica com Paginação)
            self.extrair_todos_os_tickets()
            time.sleep(3)
            self.oraculo.processar_html_tickets(self.driver.page_source)
            
            # ==========================================
            # 4. Manuais (Sincronização RAG)
            # ==========================================
            print("\n📥 Acessando Biblioteca de Manuais...")
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/manuais/busca") 
            
            # Clica no botão de busca para forçar o recarregamento da tabela completa
            try:
                btn_busca_manuais = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value='Buscar']"))
                )
                print("⏳ Pressionando botão de Busca dos Manuais...")
                btn_busca_manuais.click()
            except Exception as e:
                print("👁️ Botão de busca não encontrado ou clicável. Aguardando a tabela...")

            # O CÃO DE GUARDA INTELIGENTE:
            # Esperamos até que a linha do "MANUAL DE CADASTRO DE ENTIDADE" (ou qualquer manual) apareça!
            try:
                print("⏳ Aguardando os dados do servidor da Tecnuv chegarem na tela...")
                WebDriverWait(self.driver, 20).until(
                    # Procura por qualquer tag <a> que tenha 'href' apontando para um .pdf
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href$='.pdf']"))
                )
                print("✅ CHUVA DE PDFs! A tabela carregou completamente.")
            except Exception as e:
                print("⚠️ Aviso: Os PDFs não carregaram a tempo. A extração pode falhar.")
            
            # Um fôlego final de 2 segundos para o JavaScript estabilizar o layout
            time.sleep(2) 
            
            html_pagina = self.driver.page_source
            self.oraculo.processar_html_manuais(html_pagina)
            
            # 5. Wikis da Tecnuv 
            print("\n📥 Acessando Base de Wikis...")
            self.extrair_todas_as_wikis()
  
            try:
                self.oraculo.processar_html_wikis(self.driver.page_source)
            except AttributeError:
                print("⚠️ Método processar_html_wikis ainda não implementado no OraculoLogistica.")
            
        except Exception as e:
            print(f"❌ Erro durante a navegação: {e}")


    def extrair_todas_as_wikis(self):
        print("\n📥 Acessando Base de Wikis (Iniciando Modo Mergulhador)...")
        # URL da tabela das wikis
        url_base_busca = "https://postogestor.com.br/helpdesk/sistema/wiki/busca" 
        
        ids_ja_sincronizados = self.oraculo.obter_ids_wikis_sincronizadas()
        ids_pendentes_para_mergulho = []

        try:
            self.driver.get(url_base_busca)
            
            # Tenta encontrar e clicar no botão "Buscar" de várias formas
            try:
                btn_busca = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.ID, "btnBusca"))
                )
                btn_busca.click()
            except:
                try:
                    btn_busca = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit'][value='Buscar']")
                    btn_busca.click()
                except:
                    print("👁️ Botão de busca não encontrado. Aguardando a tabela carregar sozinha...")
                
            # O ESCUDO: Se a tabela não carregar, ele não explode o terminal, ele avisa e sai.
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/wiki/editar/id/']"))
                )
            except Exception as e:
                print("⚠️ A tabela de Wikis não apareceu. O robô pode estar no URL errado ou a Tecnuv está lenta.")
                return # Aborta o mergulho em segurança

            time.sleep(2)
            html_atual = self.driver.page_source
            match_paginas = re.search(r'Nº de páginas:.*?<font[^>]*>(\d+)</font>', html_atual, re.DOTALL)
            total_paginas = int(match_paginas.group(1)) if match_paginas else 1

            print(f"📊 O Fantasma detetou {total_paginas} páginas de Wikis. Iniciando Voo de Reconhecimento...")

            for pagina_atual in range(1, total_paginas + 1):
                if pagina_atual > 1:
                    self.driver.get(f"{url_base_busca}?pg={pagina_atual}")
                    time.sleep(3)
                    
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                links_abrir = soup.find_all('a', href=re.compile(r'/wiki/editar/id/(\d+)'))
                
                for link in links_abrir:
                    m = re.search(r'/id/(\d+)', link['href'])
                    if m:
                        wiki_id = int(m.group(1))
                        # SEGREDO DA VELOCIDADE: Só mergulha se a Wiki não existir no Banco!
                        if wiki_id not in ids_ja_sincronizados and wiki_id not in ids_pendentes_para_mergulho:
                            ids_pendentes_para_mergulho.append(wiki_id)

            print(f"🎯 Reconhecimento concluído! Encontradas {len(ids_pendentes_para_mergulho)} Wikis NOVAS para mergulhar.")

            if not ids_pendentes_para_mergulho:
                print("💤 Nenhuma wiki nova encontrada. Poupando o oxigénio do mergulhador!")
                return

            for i, wiki_id in enumerate(ids_pendentes_para_mergulho, 1):
                print(f"🤿 Mergulhando na Wiki {wiki_id} ({i} de {len(ids_pendentes_para_mergulho)})...")
                url_interna = f"https://postogestor.com.br/helpdesk/sistema/wiki/editar/id/{wiki_id}"
                
                self.driver.get(url_interna)
                
                # Cão de Guarda do texto da Wiki
                try:
                    WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "w_desc")))
                    html_interno = self.driver.page_source
                    self.oraculo.processar_e_salvar_wiki_interna(html_interno, wiki_id)
                except:
                    print(f"⚠️ Erro ao ler a Wiki {wiki_id}. Conteúdo vazio ou acesso negado.")
                
                time.sleep(1) # Respeito ao servidor

            print("✅ Varredura profunda de Wikis concluída com sucesso!")

        except Exception as e:
            print(f"❌ Erro crítico no robô de Wikis: {e}")

            
    def fechar(self):
        if self.driver:
            self.driver.quit()
            print("🛑 Navegador Fantasma encerrado.")

    

# ==========================================
# O PSY Assistente WikiSuporte (MOTOR EM SEGUNDO PLANO)
# ==========================================
def iniciar_psy_assistente():
    print("🤖 PSY Assistente do WikiSuporte Iniciado. Aguardando ordens do painel de controle...")
    
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
    iniciar_psy_assistente()