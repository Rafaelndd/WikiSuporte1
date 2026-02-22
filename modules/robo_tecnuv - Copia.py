import os
import re
import logging
import time
from datetime import datetime
from dotenv import load_dotenv

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys

# Banco de Dados
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from modules.database import get_connection 
from modules.models import ChamadoTecnuv, HistoricoInteracao, HistoricoTransicaoStatus

# Configuração de Logs Profissionais
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("oraculo_engine.log"), logging.StreamHandler()]
)

load_dotenv()

class OraculoBot:
    def __init__(self):
        self.driver = self._iniciar_driver()
        self.engine = get_connection()
        self.Session = sessionmaker(bind=self.engine)
        self.wait = WebDriverWait(self.driver, 15)

    def _iniciar_driver(self):
        options = webdriver.ChromeOptions()
        if os.getenv("MODO_HEADLESS") == "True":
            options.add_argument("--headless")
        options.add_argument("--start-maximized")
        # Flags problemáticas no Windows removidas
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
        
    def login(self):
        try:
            logging.info("Acessando página de login...")
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/login/")
            
            # 1. Leitura e Sanitização
            usuario_cru = os.getenv("TECNUV_USER", "")
            senha_cru = os.getenv("TECNUV_PASS", "")
            
            usuario_limpo = usuario_cru.encode('utf-8').decode('utf-8-sig').strip().replace('"', '').replace("'", "")
            senha_limpa = senha_cru.encode('utf-8').decode('utf-8-sig').strip().replace('"', '').replace("'", "")
            
            # 2. LOCALIZAÇÃO CIRÚRGICA (Baseada na div do HTML que você mandou)
            # Ao adicionar //div[contains(@class, 'card-container')] nós garantimos 
            # que o robô vai ignorar qualquer formulário de celular/invisível.
            xpath_user = "//div[contains(@class, 'card-container')]//input[@name='userdata[user]']"
            xpath_pass = "//div[contains(@class, 'card-container')]//input[@name='userdata[pass]']"
            xpath_btn  = "//div[contains(@class, 'card-container')]//button[@type='submit']"
            
            campo_usuario = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_user)))
            campo_senha = self.driver.find_element(By.XPATH, xpath_pass)
            botao_acessar = self.driver.find_element(By.XPATH, xpath_btn)
            
            # 3. Preenchimento
            logging.info("⌨️ Preenchendo credenciais no formulário principal...")
            campo_usuario.clear()
            campo_usuario.send_keys(usuario_cru)
            time.sleep(1)
            
            campo_senha.clear()
            campo_senha.send_keys(senha_cru)
            time.sleep(1)
            
            # 4. CLIQUE VIA JAVASCRIPT (Garante que o botão será ativado)
            logging.info("Clicando em Acessar...")
            self.driver.execute_script("arguments[0].click();", botao_acessar)
            
            # 5. Validação
            time.sleep(3)
            try:
                erro_msg = self.driver.find_elements(By.XPATH, "//a[contains(@style, 'color: red')]")
                if erro_msg and erro_msg[0].text.strip():
                    logging.error(f"❌ O site recusou o acesso: {erro_msg[0].text}")
                    return False
            except NoSuchElementException:
                pass 

            logging.info("✅ Login realizado com sucesso!")
            
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//table")))
            logging.info("Fila principal acessada com sucesso.")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Falha crítica no login: {e}")
            return False

    def configurar_filtros(self):
        """Aplica limpeza de cache, define paginação e aplica filtros de status."""
        try:
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            logging.info("Acessando página de chamados e verificando cache...")

            # 1. LIMPEZA DE CACHE (Ordem Crítica 1)
            try:
                # Procura o link de limpar filtros com um tempo limite curto (3s)
                btn_limpar = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.limpa_filtros"))
                )
                logging.info("Filtro em cache detectado. Limpando a tela...")
                btn_limpar.click()
                
                # Após limpar, precisamos aguardar a página estabilizar antes de interagir.
                # Esperamos até que o botão de busca esteja presente novamente.
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "btnBusca"))
                )
                time.sleep(2) # Pausa extra para garantir a conclusão de scripts internos do site
            except TimeoutException:
                # É o comportamento esperado na maioria das vezes
                logging.info("Nenhum filtro em cache detectado. Prosseguindo...")

            # 2. CONFIGURAÇÃO DE 500 REGISTROS (Ordem Crítica 2)
            try:
                select_pag = self.driver.find_element(By.XPATH, "//select[contains(@name, 'per_page')]")
                select_pag.click()
                self.driver.find_element(By.XPATH, "//option[@value='500']").click()
                time.sleep(1)
            except:
                pass 

            # 3. SELEÇÃO CIRÚRGICA DE STATUS (Ordem Crítica 3)
            btn_status = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@title='Status']")))
            btn_status.click()
            time.sleep(1) 
            
            status_desejados = [
                "Em aberto", "Em analise", "Pendente representante", "Pendente tecnuv", 
                "Em fila de desenvolvimento", "Em Desenvolvimento", "Em Andamento", 
                "Aguardando Liberação de Versão", "Aguardando avaliação", 
                "Enviado para qualidade", "Retorno Qualidade"
            ]
            
            checkboxes = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'multiselect-container')]//input[@type='checkbox']")
            logging.info("Ajustando checkboxes de Status...")
            
            for check in checkboxes:
                valor = check.get_attribute("value")
                if valor == "multiselect-all":
                    continue 
                
                is_selected = check.is_selected()
                
                if valor in status_desejados and not is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
                elif valor not in status_desejados and is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
            
            btn_status.click() # Fecha o menu
            
            # 4. APLICAÇÃO DA BUSCA (Ordem Crítica 4)
            btn_busca = self.driver.find_element(By.ID, "btnBusca")
            btn_busca.click()
            
            logging.info("Filtros aplicados. Aguardando recarregamento da tabela final...")
            time.sleep(5) 
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Erro crítico ao configurar filtros: {e}")
            return False

    def extrair_data_alteracao(self, html_icone):
        """Regex para pegar a data do ícone 'i'."""
        match = re.search(r'(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})', html_icone)
        if match:
            return datetime.strptime(match.group(1), "%d/%m/%Y %H:%M:%S")
        return None

    def deep_scrape_chamado(self, link, nr_chamado_str):
        """Abre o chamado em nova aba, extrai tudo com HTML (Retry Controlado)."""
        nr_chamado = int(nr_chamado_str)
        max_tentativas = 3
        
        for tentativa in range(1, max_tentativas + 1):
            main_window = self.driver.current_window_handle
            session = self.Session()
            
            try:
                self.driver.execute_script(f"window.open('{link}', '_blank');")
                self.driver.switch_to.window(self.driver.window_handles[-1])
                
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Num. Chamado:')]")))
                
                def get_val(label_text):
                    try: 
                        xpath = f"//label[normalize-space(text())='{label_text}']/following-sibling::span"
                        texto = self.driver.find_element(By.XPATH, xpath).text.strip()
                        return texto if texto else "Não Informado"
                    except: 
                        return "Não Informado"

                # Extrai dados básicos
                cliente = get_val("Cliente:")
                atendente = get_val("Atendente:")
                usuario = get_val("Usuário:")
                
                # Extração HTML integral do Motivo
                try:
                    div_motivo = self.driver.find_element(By.ID, "tecnuv_motivo")
                    html_motivo = div_motivo.get_attribute("innerHTML").strip()
                except NoSuchElementException:
                    html_motivo = ""

                # Atualiza Capa do Chamado
                chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                if chamado:
                    chamado.cliente_nome = cliente
                    chamado.atendente_tecnuv = atendente
                    chamado.usuario_epsy = usuario
                    chamado.motivo_abertura_html = html_motivo
                    chamado.assunto_html = html_motivo # Por segurança, salva o HTML integral

                # Extração de Mensagens (Interações)
                mensagens = self.driver.find_elements(By.XPATH, "//label[contains(@for, 'mensagem')]")
                for msg_label in mensagens:
                    txt = msg_label.text
                    match = re.search(r'Usuário:\s*(.*?)\s*-\s*Data:\s*(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})', txt)
                    
                    if match:
                        autor = match.group(1).strip()
                        dt_msg = datetime.strptime(match.group(2), "%d/%m/%Y %H:%M:%S")
                        div_id = msg_label.get_attribute("for")
                        conteudo_html = self.driver.find_element(By.ID, div_id).get_attribute("innerHTML").strip()
                        
                        stmt = insert(HistoricoInteracao).values(
                            nr_chamado=nr_chamado,
                            usuario=autor,
                            data_interacao=dt_msg,
                            descricao_html=conteudo_html
                        ).on_conflict_do_nothing(index_elements=['nr_chamado', 'data_interacao', 'usuario'])
                        
                        session.execute(stmt)

                session.commit()
                logging.info(f"[OK] Chamado {nr_chamado} sincronizado na tentativa {tentativa}.")
                break # Sucesso, sai do laço de retry
                
            except Exception as e:
                session.rollback()
                logging.warning(f"[AVISO] Falha na raspagem do chamado {nr_chamado} (Tentativa {tentativa}/{max_tentativas}). Erro: {e}")
                time.sleep(2) # Pausa para o Chrome respirar
                if tentativa == max_tentativas:
                    logging.error(f"[ERRO] Raspagem do chamado {nr_chamado} abortada após 3 tentativas.")
            finally:
                if len(self.driver.window_handles) > 1:
                    self.driver.close()
                    self.driver.switch_to.window(main_window)
                session.close()

    def varrer_tabela(self):
        session = self.Session()
        try:
            linhas = self.driver.find_elements(By.XPATH, "//table/tbody/tr")
            logging.info(f"Encontradas {len(linhas)} linhas na tabela.")

            for linha in linhas:
                try:
                    btn_abrir = linha.find_element(By.CSS_SELECTOR, "a.btn-primary")
                    link = btn_abrir.get_attribute("href")
                    nr_chamado_str = link.split("/")[-1]
                    nr_chamado = int(nr_chamado_str)
                    
                    # Correção das colunas: Data (6) e Status (8)
                    tds = linha.find_elements(By.TAG_NAME, "td")
                    data_abertura_str = tds[5].text.strip() # td[6] indexado em 0 é 5
                    status_web = tds[7].text.strip() # td[8] indexado em 0 é 7
                    
                    # Conversão de Data de Abertura
                    dt_abertura = None
                    if data_abertura_str:
                        try:
                            dt_abertura = datetime.strptime(data_abertura_str, "%d/%m/%Y %H:%M:%S")
                        except ValueError:
                            pass

                    # Delta Load: Data de última alteração (Ícone i)
                    icone_i = linha.find_element(By.XPATH, ".//a[contains(@class, 'dcontexto')]")
                    data_alt_web = self.extrair_data_alteracao(icone_i.get_attribute("innerHTML"))

                    # Verifica no Banco usando nr_chamado
                    chamado_db = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                    
                    if not chamado_db:
                        logging.info(f"[*] {nr_chamado}: Novo chamado detectado. Extraindo...")
                        new_c = ChamadoTecnuv(
                            nr_chamado=nr_chamado, 
                            status_atual=status_web, 
                            data_abertura=dt_abertura,
                            ultima_alteracao_tecnuv=data_alt_web
                        )
                        session.add(new_c)
                        session.commit()
                        self.deep_scrape_chamado(link, nr_chamado_str)
                    
                    else:
                        if chamado_db.status_atual != status_web:
                            log_status = HistoricoTransicaoStatus(
                                nr_chamado=nr_chamado, 
                                status_anterior=chamado_db.status_atual, 
                                status_novo=status_web
                            )
                            session.add(log_status)
                            chamado_db.status_atual = status_web
                            session.commit()
                            self.deep_scrape_chamado(link, nr_chamado_str)
                        
                        elif data_alt_web and (not chamado_db.ultima_alteracao_tecnuv or data_alt_web > chamado_db.ultima_alteracao_tecnuv):
                            chamado_db.ultima_alteracao_tecnuv = data_alt_web
                            session.commit()
                            self.deep_scrape_chamado(link, nr_chamado_str)
                        
                except NoSuchElementException:
                    continue
                except Exception as row_e:
                    logging.warning(f"Erro inesperado ao processar linha: {row_e}")
                    continue
        finally:
            session.close()
    def fechar_modal_se_existir(self):
        """Tenta fechar modais de notificação sem travar a performance."""
        try:
            modais = self.driver.find_elements(By.CSS_SELECTOR, ".modal-dialog .close")
            if modais and modais[0].is_displayed():
                modais[0].click()
                logging.info("[OK] Modal de notificação interceptado e fechado.")
        except Exception:
            pass # Segue o fluxo imediatamente
            
    def encerrar(self):
        self.driver.quit()
        logging.info("Robô finalizado.")