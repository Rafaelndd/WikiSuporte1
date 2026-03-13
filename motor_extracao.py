import time
import os
import re
import logging


from bs4 import BeautifulSoup
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
from services.db_homologacao import processar_release_completo
from services.bot_control import (
    consumir_tarefa,
    definir_etapa,
    iniciar_execucao,
    finalizar_execucao,
    ler_estado,
    pode_executar_raspagem,
    MIN_INTERVALO_ENTRE_REQUISICOES_SEG,
)


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

    def extrair_releases(self):
        """Extrai releases da Home do helpdesk e persiste no novo modelo (releases, chamados, ciclos_homologacao)."""
        print("📦 Lendo janelas de Releases...")
        try:
            links_releases = self.driver.find_elements(By.CLASS_NAME, "loadNoticia")
            total_vinculados = 0
            total_ciclos = 0

            for link in links_releases:
                link.click()
                textarea = WebDriverWait(self.driver, 10).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "msg3-noticia"))
                )
                titulo_release = self.driver.find_element(By.CLASS_NAME, "msg1-noticia").text
                texto_release = textarea.get_attribute("value") or ""

                if not texto_release.strip():
                    btn_fechar = self.driver.find_element(By.CSS_SELECTOR, "div.modal-header button.close")
                    btn_fechar.click()
                    time.sleep(1)
                    continue

                try:
                    qtd_vinculados, qtd_ciclos = processar_release_completo(
                        versao=titulo_release[:50].strip(),
                        texto_completo=texto_release,
                        autor="Processamento Automático (bot)",
                    )
                    total_vinculados += qtd_vinculados
                    total_ciclos += qtd_ciclos
                    chamados = re.findall(r"\((\d{4,6})\)", texto_release)
                    print(f"✅ Versão: {titulo_release} | Chamados: {chamados} | Ciclos criados: {qtd_ciclos}")
                except Exception as ex:
                    print(f"⚠️ Erro ao persistir release {titulo_release}: {ex}")

                btn_fechar = self.driver.find_element(By.CSS_SELECTOR, "div.modal-header button.close")
                btn_fechar.click()
                time.sleep(1)

            if total_vinculados > 0 or total_ciclos > 0:
                print(f"📊 Total: {total_vinculados} chamados vinculados, {total_ciclos} ciclos criados.")
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


    
    def _pausa_servidor(self):
        """Pausa entre requisições para não sobrecarregar o servidor da Tecnuv."""
        time.sleep(MIN_INTERVALO_ENTRE_REQUISICOES_SEG)

    def raspar_releases(self):
        definir_etapa("Releases: acessando Home")
        print("\n📥 Acessando Home (Releases)...")
        self.driver.get("https://postogestor.com.br/helpdesk/home")
        self._pausa_servidor()
        definir_etapa("Releases: extraindo dados")
        self.extrair_releases()

    def raspar_plantoes(self):
        definir_etapa("Plantões: acessando página")
        print("\n📥 Acessando Plantões...")
        self.driver.get(URL_PLANTOES)
        self._pausa_servidor()
        definir_etapa("Plantões: processando HTML")
        self.oraculo.processar_html_plantoes(self.driver.page_source)

    def raspar_tickets(self):
        definir_etapa("Tickets: acessando fila")
        self.extrair_todos_os_tickets()
        self._pausa_servidor()
        definir_etapa("Tickets: processando última página")
        self.oraculo.processar_html_tickets(self.driver.page_source)

    def raspar_manuais(self):
        definir_etapa("Manuais: acessando biblioteca")
        print("\n📥 Acessando Biblioteca de Manuais...")
        self.driver.get("https://postogestor.com.br/helpdesk/sistema/manuais/busca")
        try:
            btn_busca_manuais = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value='Buscar']"))
            )
            btn_busca_manuais.click()
        except Exception:
            pass
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href$='.pdf']"))
            )
        except Exception:
            pass
        self._pausa_servidor()
        definir_etapa("Manuais: processando HTML")
        self.oraculo.processar_html_manuais(self.driver.page_source)

    def raspar_wikis(self):
        definir_etapa("Wikis: iniciando mergulho")
        self.extrair_todas_as_wikis()

    def raspar_fonte(self, tipo: str):
        """Executa uma raspagem individual por tipo."""
        mapa = {
            "releases": self.raspar_releases,
            "plantoes": self.raspar_plantoes,
            "tickets": self.raspar_tickets,
            "manuais": self.raspar_manuais,
            "wikis": self.raspar_wikis,
        }
        fn = mapa.get(tipo)
        if fn:
            fn()
        else:
            print(f"⚠️ Tipo de raspagem '{tipo}' não tem handler no motor_extracao.")

    def raspar_todas_as_fontes(self):
        try:
            self.raspar_releases()
            self._pausa_servidor()
            self.raspar_plantoes()
            self._pausa_servidor()
            self.raspar_tickets()
            self._pausa_servidor()
            self.raspar_manuais()
            self._pausa_servidor()
            self.raspar_wikis()
        finally:
            definir_etapa(None)
            print("✅ Extração de todas as fontes concluída!")
   

    def extrair_todas_as_wikis(self):
        print("\n📥 Acessando Base de Wikis (Iniciando Modo Mergulhador)...")
        
        # O URL correto da lista principal de Wikis (Ajuste se necessário)
        url_base_wikis = "https://postogestor.com.br/helpdesk/sistema/wiki" 
        
        ids_ja_sincronizados = self.oraculo.obter_ids_wikis_sincronizadas()
        ids_pendentes_para_mergulho = []

        try:
            self.driver.get(url_base_wikis)
            print("⏳ Aguardando a tabela de Wikis carregar...")
                
            # O ESCUDO: Fica a olhar até que apareça a primeira linha com o botão "Abrir"
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/wiki/editar/id/']"))
                )
            except Exception as e:
                print("⚠️ A tabela de Wikis não apareceu. O URL base pode estar errado ou o site demorou muito.")
                return # Aborta o mergulho em segurança

            time.sleep(2)
            html_atual = self.driver.page_source
            
            # Tenta descobrir o número total de páginas (se não achar, assume que é 1 página só)
            match_paginas = re.search(r'Nº de páginas:.*?<font[^>]*>(\d+)</font>', html_atual, re.DOTALL)
            total_paginas = int(match_paginas.group(1)) if match_paginas else 1

            print(f"📊 O Fantasma detetou {total_paginas} páginas de Wikis. Iniciando Voo de Reconhecimento...")

            # ==========================================
            # FASE 1: VOO DE RECONHECIMENTO (Anotar IDs)
            # ==========================================
            for pagina_atual in range(1, total_paginas + 1):
                if pagina_atual > 1:
                    # Tenta navegar para a próxima página (Alguns sistemas usam ?pg=2, outros /pg/2)
                    self.driver.get(f"{url_base_wikis}?pg={pagina_atual}")
                    time.sleep(3)
                    
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                links_abrir = soup.find_all('a', href=re.compile(r'/wiki/editar/id/(\d+)'))
                
                for link in links_abrir:
                    m = re.search(r'/id/(\d+)', link['href'])
                    if m:
                        wiki_id = int(m.group(1))
                        # SEGREDO DA VELOCIDADE: Só anota se a Wiki não existir no Banco!
                        if wiki_id not in ids_ja_sincronizados and wiki_id not in ids_pendentes_para_mergulho:
                            ids_pendentes_para_mergulho.append(wiki_id)

            print(f"🎯 Reconhecimento concluído! Encontradas {len(ids_pendentes_para_mergulho)} Wikis NOVAS para mergulhar.")

            # ==========================================
            # FASE 2: O MERGULHO PROFUNDO
            # ==========================================
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

def _executar_motor(tarefa: str | None = None):
    """
    Cria o motor, faz login e executa a raspagem.
    Se `tarefa` for um tipo específico (ex: 'releases'), executa só ele.
    Se None, executa todas as fontes.
    """
    motor = MotorExtracao()
    try:
        definir_etapa("Iniciando navegador")
        motor.iniciar_navegador()
        definir_etapa("Autenticando no HelpDesk")
        if motor.fazer_login():
            if tarefa and tarefa != "all":
                motor.raspar_fonte(tarefa)
            else:
                motor.raspar_todas_as_fontes()
        else:
            print("❌ Falha no login. Abortando ciclo.")
    except Exception as e:
        print(f"Erro Crítico no Motor: {e}")
    finally:
        definir_etapa("Encerrando navegador")
        motor.fechar()


def iniciar_psy_assistente():
    print("🤖 PSY Assistente do WikiSuporte Iniciado. Aguardando ordens do painel de controle...")

    while True:
        try:
            estado = ler_estado()

            if estado.get("em_andamento"):
                time.sleep(10)
                continue

            tarefa = consumir_tarefa()
            if tarefa:
                ok, motivo = pode_executar_raspagem(ler_estado())
                if not ok:
                    print(f"⛔ Raspagem '{tarefa}' bloqueada: {motivo}")
                    time.sleep(30)
                    continue

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Tarefa solicitada: {tarefa}")
                iniciar_execucao(f"Preparando raspagem: {tarefa}")
                try:
                    _executar_motor(tarefa)
                finally:
                    finalizar_execucao()
                print(f"✅ Tarefa '{tarefa}' concluída.")
                time.sleep(10)
                continue

            if estado.get("auto_ativo", False):
                from datetime import timedelta
                intervalo_minutos = estado.get("intervalo", 60)
                ultima = estado.get("ultima_execucao")

                executar_agora = False
                if not ultima:
                    executar_agora = True
                else:
                    try:
                        dt_ultima = datetime.fromisoformat(ultima)
                        if datetime.now() >= dt_ultima + timedelta(minutes=intervalo_minutos):
                            executar_agora = True
                    except Exception:
                        executar_agora = True

                if executar_agora:
                    ok, motivo = pode_executar_raspagem(ler_estado())
                    if ok:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando ciclo automático (intervalo {intervalo_minutos} min)...")
                        iniciar_execucao("Ciclo automático: todas as fontes")
                        try:
                            _executar_motor()
                        finally:
                            finalizar_execucao()
                        print(f"⏳ Ciclo concluído. Próximo em {intervalo_minutos} min.")
                    else:
                        print(f"⛔ Ciclo automático bloqueado: {motivo}")

            time.sleep(30)

        except Exception as e:
            print(f"❌ Erro crítico no loop principal: {e}")
            try:
                finalizar_execucao()
            except Exception:
                pass
            time.sleep(60)


if __name__ == "__main__":
    iniciar_psy_assistente()