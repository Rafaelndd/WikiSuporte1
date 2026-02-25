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

# Banco de Dados
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from modules.database import get_connection 
from modules.models import ChamadoTecnuv, HistoricoInteracao, HistoricoTransicaoStatus

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("oraculo_engine.log"),logging.StreamHandler()]
)

load_dotenv()

class OraculoBot:
    def __init__(self):
        """
        Inicializa o ChromeDriver, a conexão com o banco e as configurações de espera.
        """
        self.driver = self._iniciar_driver()
        self.engine = get_connection()
        self.Session = sessionmaker(bind=self.engine)
        self.wait = WebDriverWait(self.driver, 5)

    # def _iniciar_driver(self):
    #     """
    #     Configura e inicia o ChromeDriver com opções de segurança e performance. Modo invisível, user-agent humano, resolução fixa e outras artimanhas para enganar o Tecnuv.
    #     """
    #     options = webdriver.ChromeOptions()
        
    #     # --- 1. MODO INVISÍVEL ---
    #     if os.getenv("MODO_HEADLESS") == "True" or True: # Forçado para produção
    #         options.add_argument("--headless=new")
        
    #     # --- 2. MÁSCARA HUMANA E DE RESOLUÇÃO (A CIRURGIA) ---
    #     # Engana o Tecnuv dizendo que é um utilizador normal num PC com Windows
    #     user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    #     options.add_argument(f"user-agent={user_agent}")
        
    #     # Força uma tela gigante e impede o site de encolher os botões
    #     options.add_argument("--window-size=1920,1080")
    #     options.add_argument("--force-device-scale-factor=1")
    #     # -----------------------------------------------------

    #     options.add_argument("--start-maximized")
    #     options.add_argument("--no-sandbox")
    #     options.add_argument("--disable-dev-shm-usage")
        
    #     # Opções extras para evitar que o site detete a automação
    #     options.add_argument("--disable-blink-features=AutomationControlled")
    #     options.add_experimental_option("excludeSwitches", ["enable-automation"])
    #     options.add_experimental_option('useAutomationExtension', False)

    #     service = Service(ChromeDriverManager().install())
    #     driver = webdriver.Chrome(service=service, options=options)
        
    #     # Remove a flag de webdriver do navegador criado
    #     driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
        
    #     return driver

    def _iniciar_driver(self):
        """
        Configura e inicia o ChromeDriver com SUPER VISÃO no Modo Fantasma.
        Garante que as tabelas responsivas nunca ocultem colunas.
        """
        options = webdriver.ChromeOptions()
        
        # --- 1. MODO FANTASMA (INVISÍVEL) REATIVADO ---
        options.add_argument("--headless=new")
        
        # --- 2. MÁSCARA HUMANA ---
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        options.add_argument(f"user-agent={user_agent}")
        
        # --- 3. SUPER VISÃO (Resolução e Zoom exatos) ---
        # Resolução 2K para garantir espaço de sobra para a tabela
        options.add_argument("--window-size=2560,1440")
        
        # Força o Zoom exato em 100% (1.0). Se preferir 90%, basta mudar para 0.9
        options.add_argument("--force-device-scale-factor=1.0")
        # ------------------------------------------------
        
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Opções extras de evasão para evitar bloqueios do servidor
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Injeta a máscara humana profundamente nas requisições de rede
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
        
        return driver

    def fechar_modal_se_existir(self):
        """
        Tenta fechar modais de notificação sem interromper o fluxo.
        """
        try:
            modais = self.driver.find_elements(By.CSS_SELECTOR, ".modal-dialog .close")
            if modais and modais[0].is_displayed():
                modais[0].click()
                logging.info("[OK] Modal de notificação interceptado e fechado.")
        except Exception:
            pass 
        
    def login(self):
        """
        Realiza o login seguro no sistema da Tecnuv.
        """
        try:
            logging.info("Acessando página de login...")
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/login/")
            
            usuario_cru = os.getenv("TECNUV_USER", "")
            senha_cru = os.getenv("TECNUV_PASS", "")
            
            xpath_user = "//div[contains(@class, 'card-container')]//input[@name='userdata[user]']"
            xpath_pass = "//div[contains(@class, 'card-container')]//input[@name='userdata[pass]']"
            xpath_btn  = "//div[contains(@class, 'card-container')]//button[@type='submit']"
            
            campo_usuario = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_user)))
            campo_senha = self.driver.find_element(By.XPATH, xpath_pass)
            botao_acessar = self.driver.find_element(By.XPATH, xpath_btn)
            
            campo_usuario.clear()
            campo_usuario.send_keys(usuario_cru)
            campo_senha.clear()
            campo_senha.send_keys(senha_cru)
            
            logging.info("Clicando em Acessar...")
            self.driver.execute_script("arguments[0].click();", botao_acessar)
            
            time.sleep(3)
            erro_msg = self.driver.find_elements(By.XPATH, "//a[contains(@style, 'color: red')]")
            if erro_msg and erro_msg[0].text.strip():
                logging.error(f"O site recusou o acesso: {erro_msg[0].text}")
                return False

            logging.info("Login realizado com sucesso!")
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            return True
            
        except Exception as e:
            logging.error(f"Falha no login: {e}")
            return False

           


    def configurar_filtros(self):
        """
        Ajusta paginação e aplica os status um a um para evitar bugs do site.
        """
        try:
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            
            # Limpeza de Filtros/Cache
            try:
                btn_limpar = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.limpa_filtros"))
                )
                btn_limpar.click()
                time.sleep(2)
            except TimeoutException:
                pass

            # Paginação 500
            try:
                select_pag = self.driver.find_element(By.XPATH, "//select[contains(@name, 'per_page')]")
                select_pag.click()
                self.driver.find_element(By.XPATH, "//option[@value='500']").click()
                time.sleep(1)
            except: pass 

            # Seleção de Status (Lista Conversada)
            btn_status = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@title='Status']")))
            btn_status.click()
            time.sleep(1) 

            status_desejados = [
                "Em aberto", "Encerrado", "Cancelado", "Em analise", 
                "Pendente representante", "Pendente tecnuv", "Em Desenvolvimento", 
                "Em Fila de Desenvolvimento", "Em Andamento", 
                "Aguardando Liberacao de Versao", "Aguardando Avaliacao", 
                "Enviado Para Qualidade", "Retorno Qualidade"
            ]
            
            checkboxes = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'multiselect-container')]//input[@type='checkbox']")
            
            for check in checkboxes:
                valor_exato = check.get_attribute("value")
                if valor_exato == "multiselect-all": continue 
                
                is_selected = check.is_selected()
                if valor_exato in status_desejados and not is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
                elif valor_exato not in status_desejados and is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
            
            btn_status.click()
            self.driver.find_element(By.ID, "btnBusca").click()
            logging.info("Filtros aplicados com sucesso.")
            time.sleep(5) 
            return True
        except Exception as e:
            logging.error(f"Erro ao configurar filtros: {e}")
            return False


    def varrer_tabela(self):
        """
        Fase 1: Percorre todas as páginas capturando metadados.
        Fase 2: Realiza o Deep Scrape apenas nos chamados necessários.
        """
        session = self.Session()
        chamados_coletados = []
        pagina_atual = 1

        try:
            logging.info("Iniciando Fase 1: Mapeamento de todas as páginas...")
            
            while True:
                logging.info(f"Coletando metadados da página {pagina_atual}...")
                
                self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr")))
                linhas = self.driver.find_elements(By.XPATH, "//table/tbody/tr")
                for linha in linhas:
                    try:
                        tds = linha.find_elements(By.TAG_NAME, "td")
                        if not tds: 
                            continue
                        
                        cliente_tabela = tds[1].text.strip()

                        if "TECNUV SISTEMAS" in cliente_tabela.upper():
                            continue
                        
                        btn_abrir = linha.find_element(By.CSS_SELECTOR, "a.btn-primary")
                        link = btn_abrir.get_attribute("href")
                        nr_chamado = int(link.split("/")[-1])
                        
                        try:
                            icone_i = linha.find_element(By.XPATH, ".//a[contains(@class, 'dcontexto')]")
                            html_icone = icone_i.get_attribute("innerHTML")
                            data_alt_web = self.extrair_data_alteracao(html_icone)
                        except:
                            data_alt_web = None
                            logging.warning(f"Chamado {nr_chamado} sem ícone de alteração (dcontexto).")

                        chamados_coletados.append({
                            "nr_chamado": nr_chamado,
                            "link": link,
                            "status_web": tds[7].text.strip(),
                            "data_alt_web": data_alt_web,
                            "ticket_vinculado": tds[2].text.strip(),
                            "setor": tds[6].text.strip(),
                            "situacao": tds[8].text.strip(),
                            "prioridade": tds[9].text.strip(),
                            "dt_abertura_str": tds[5].text.strip()
                        })
                        
                    except Exception as e:
                        logging.error(f"Erro ao processar linha da tabela: {e}")
                        continue
                
                try:
                    btn_proximo = self.driver.find_elements(By.CSS_SELECTOR, "a[title='próxima página']")
                    if btn_proximo and btn_proximo[0].is_displayed():
                        pagina_atual += 1
                        logging.info(f"Indo para a página {pagina_atual}...")
                        self.driver.execute_script("arguments[0].click();", btn_proximo[0])
                        time.sleep(4) 
                    else:
                        logging.info("Chegamos à última página da tabela.")
                        break
                except NoSuchElementException:
                    break

            # --- FASE 2: PROCESSAMENTO E DEEP SCRAPE ---
            logging.info(f"Total de {len(chamados_coletados)} chamados mapeados. Iniciando verificações no banco...")
            
            # CIRURGIA: Variáveis para o Relatório Final
            sucesso_count = 0
            falhas_lista = []

            for item in chamados_coletados:
                nr_chamado = item["nr_chamado"]
                chamado_db = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                
                if chamado_db and chamado_db.status_atual in ["Encerrado", "Cancelado"]:
                    continue 

                precisa_raspar = False

                if not chamado_db:
                    dt_abertura = None
                    try: dt_abertura = datetime.strptime(item["dt_abertura_str"], "%d/%m/%Y %H:%M:%S")
                    except: pass

                    novo = ChamadoTecnuv(
                        nr_chamado=nr_chamado,
                        status_atual=item["status_web"],
                        ultima_alteracao_tecnuv=item["data_alt_web"],
                        ticket_vinculado=item["ticket_vinculado"],
                        setor=item["setor"],
                        situacao=item["situacao"],
                        prioridade=item["prioridade"],
                        data_abertura=dt_abertura
                    )
                    session.add(novo)
                    precisa_raspar = True
                else:
                    if chamado_db.status_atual != item["status_web"]:
                        log_status = HistoricoTransicaoStatus(
                            nr_chamado=nr_chamado,
                            status_anterior=chamado_db.status_atual,
                            status_novo=item["status_web"]
                        )
                        session.add(log_status)
                        chamado_db.status_atual = item["status_web"]
                        precisa_raspar = True
                    
                    elif item["data_alt_web"] and (not chamado_db.ultima_alteracao_tecnuv or item["data_alt_web"] > chamado_db.ultima_alteracao_tecnuv):
                        precisa_raspar = True

                if precisa_raspar:
                    session.commit()
                    self.driver.get(item["link"])
                    self.fechar_modal_se_existir()
                    
                    # CIRURGIA: Captura o resultado da raspagem
                    sucesso = self.deep_scrape_chamado_atual(nr_chamado)
                    if sucesso:
                        sucesso_count += 1
                    else:
                        falhas_lista.append(nr_chamado)

            # CIRURGIA: Relatório Final Impresso no Log/Streamlit
            logging.info("====== RELATÓRIO DE VARREDURA (FASE 2) ======")
            logging.info(f"✅ Chamados lidos com sucesso: {sucesso_count}")
            if falhas_lista:
                logging.warning(f"❌ Chamados com erro de leitura (Acesso Restrito/Falha): {len(falhas_lista)}")
                logging.warning(f"📋 Números com erro: {', '.join(map(str, falhas_lista))}")
            else:
                logging.info("Nenhum erro de leitura detectado.")
            logging.info("=============================================")

            logging.info("Sincronização completa de todas as páginas finalizada.")

            # --- LÓGICA DE ÓRFÃOS: QUEM SUMIU DA FILA? ---
            ids_vistos = [item["nr_chamado"] for item in chamados_coletados]
            
            chamados_orfaos = session.query(ChamadoTecnuv).filter(
                ChamadoTecnuv.status_atual.notin_(["Encerrado", "Cancelado"]),
                ChamadoTecnuv.nr_chamado.notin_(ids_vistos)
            ).all()

            if chamados_orfaos:
                logging.info(f"Detectados {len(chamados_orfaos)} chamados que sumiram da fila ativa. Verificando se foram finalizados...")
                self.processar_chamados_orfaos(chamados_orfaos)

        finally:
            session.close()

    def deep_scrape_chamado_atual(self, nr_chamado):
        """
        Extrai os detalhes profundos, incluindo a NOVA VERSÃO DO SISTEMA.
        Retorna True se sucesso, False se falhar (ex: sem acesso).
        """
        session = self.Session()
        try:
            # CIRURGIA: Reduzido o tempo de espera de 15s para 4s para acelerar os pulos
            WebDriverWait(self.driver, 4).until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Num. Chamado:')]")))
            
            def get_val(label_text):
                try: 
                    xpath = f"//label[normalize-space(text())='{label_text}']/following-sibling::span"
                    return self.driver.find_element(By.XPATH, xpath).text.strip()
                except: return "Não Informado"

            try:
                campo_versao = self.driver.find_element(By.ID, "tecnuv_versao_abertura")
                versao = campo_versao.get_attribute("value").strip()
            except:
                versao = "Não Informada"

            try:
                html_motivo = self.driver.find_element(By.ID, "tecnuv_motivo").get_attribute("innerHTML").strip()
            except: html_motivo = ""

            chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
            if chamado:
                chamado.cliente_nome = get_val("Cliente:")
                chamado.atendente_tecnuv = get_val("Atendente:")
                chamado.usuario_epsy = get_val("Usuário:")
                chamado.versao_sistema = versao 
                chamado.motivo_abertura_html = html_motivo
                chamado.assunto_html = html_motivo

            session.commit()
            logging.info(f"[OK] Detalhes do chamado {nr_chamado} sincronizados (Versão: {versao}).")
            return True
            
        except TimeoutException:
            # CIRURGIA: Erro limpo para chamados sem permissão de acesso
            session.rollback()
            logging.warning(f"[BLOQUEADO] Chamado {nr_chamado} não abriu. Provável restrição de acesso (Outra representante).")
            return False
            
        except Exception as e:
            session.rollback()
            logging.error(f"[ERRO] Falha no Deep Scrape do chamado {nr_chamado}: {str(e)}")
            return False
            
        finally:
            session.close()

    def recuperar_falhas_raspagem(self):
        """
        Fase 3: Auto-Cura para dados nulos OU Versões não capturadas (Retroativo).
        """
        session = self.Session()
        try:
            chamados_falhos = session.query(ChamadoTecnuv).filter(
                (
                    (ChamadoTecnuv.cliente_nome == None) | 
                    (ChamadoTecnuv.cliente_nome == "") |
                    (ChamadoTecnuv.versao_sistema == None)
                ),
                ChamadoTecnuv.status_atual.notin_(["Encerrado", "Cancelado"])
            ).all()
            
            if not chamados_falhos:
                return

            logging.info(f"Iniciando Auto-Cura para {len(chamados_falhos)} chamados (Varredura Retroativa)...")
            
            # CIRURGIA: Variáveis para o Relatório da Fase 3
            sucesso_count = 0
            falhas_lista = []
            
            self.driver.quit()
            self.driver = self._iniciar_driver()
            self.wait = WebDriverWait(self.driver, 15)
            
            if self.login():
                for chamado in chamados_falhos:
                    link = f"https://postogestor.com.br/helpdesk/sistema/tecnuv/editar/id/{chamado.nr_chamado}"
                    self.driver.get(link)
                    self.fechar_modal_se_existir()
                    
                    sucesso = self.deep_scrape_chamado_atual(chamado.nr_chamado)
                    if sucesso:
                        sucesso_count += 1
                    else:
                        falhas_lista.append(chamado.nr_chamado)

                # CIRURGIA: Relatório Final Impresso no Log
                logging.info("====== RELATÓRIO DE AUTO-CURA (FASE 3) ======")
                logging.info(f"✅ Chamados recuperados com sucesso: {sucesso_count}")
                if falhas_lista:
                    logging.warning(f"❌ Chamados impossíveis de ler (Acesso restrito permanente): {len(falhas_lista)}")
                logging.info("=============================================")
                        
        finally:
            session.close()

    def processar_chamados_orfaos(self, lista_orfaos):
        """Busca o paradeiro de chamados que não apareceram na fila normal."""
        for chamado in lista_orfaos:
            nr = chamado.nr_chamado
            logging.info(f"Rastreando chamado órfão {nr}...")
            
            # Nível 1: Busca apenas Cancelados/Encerrados
            encontrado = self.executar_busca_especifica(nr, filtros=["Encerrado", "Cancelado"])
            
            # Nível 2: Se não achou, busca sem filtro nenhum (Global)
            if not encontrado:
                encontrado = self.executar_busca_especifica(nr, filtros=[])
            
            if encontrado:
                self.deep_scrape_finalizacao(nr)
            else:
                logging.warning(f"Chamado {nr} não localizado em nenhuma busca. Pode ter sido movido de setor.")

    def executar_busca_especifica(self, nr_chamado, filtros):
        """Realiza a pesquisa no site usando o campo nr_chamado."""
        try:
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            self.fechar_modal_se_existir()
            
            # Limpa tudo
            self.driver.find_element(By.CSS_SELECTOR, "a.limpa_filtros").click()
            time.sleep(2)

            # Aplica filtros se houver
            if filtros:
                btn_status = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@title='Status']")))
                btn_status.click()
                time.sleep(1)
                checkboxes = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'multiselect-container')]//input[@type='checkbox']")
                for check in checkboxes:
                    if check.get_attribute("value") in filtros:
                        if not check.is_selected():
                            check.find_element(By.XPATH, "./parent::label").click()
                btn_status.click()

            # Preenche o número e busca
            campo = self.driver.find_element(By.NAME, "form[nr_chamado]")
            campo.clear()
            campo.send_keys(str(nr_chamado))
            self.driver.find_element(By.ID, "btnBusca").click()
            time.sleep(3)

            # Verifica se apareceu o link do chamado
            links = self.driver.find_elements(By.XPATH, f"//a[contains(@href, '/id/{nr_chamado}')]")
            if links:
                links[0].click()
                return True
            return False
        except:
            return False

    def deep_scrape_finalizacao(self, nr_chamado):
        """Extrai a ÚLTIMA interação para registrar o fim do chamado."""
        session = self.Session()
        try:
            # Aguarda o histórico carregar
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//legend[contains(text(), 'Histórico')]")))
            
            # Coleta todos os blocos de mensagens (pelo seu HTML, são col-md-11)
            blocos = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'col-md-11')]")
            if not blocos: return

            # Pegamos o ÚLTIMO bloco (a interação de finalização)
            ultimo = blocos[-1]
            header = ultimo.find_element(By.TAG_NAME, "label").text
            corpo = ultimo.find_element(By.CLASS_NAME, "msgMd").text.strip()
            
            # Status atual na tela (Label Status:)
            status_site = self.driver.find_element(By.XPATH, "//label[contains(text(), 'Status:')]/following-sibling::span").text.strip()

            # Regex para Usuário e Data
            match = re.search(r'Usuário:\s*(.*?)\s*-\s*Data:\s*(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})', header)
            
            chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
            if chamado and match:
                usuario = match.group(1).strip()
                data_dt = datetime.strptime(match.group(2), "%d/%m/%Y %H:%M:%S")
                
                chamado.status_atual = status_site
                chamado.assunto_encerramento = corpo
                
                if "ENCERRADO" in status_site.upper():
                    chamado.data_encerramento = data_dt
                    chamado.usuario_encerramento = usuario
                elif "CANCELADO" in status_site.upper():
                    chamado.data_cancelamento = data_dt
                    chamado.usuario_cancelamento = usuario
                
                session.commit()
                logging.info(f"Chamado {nr_chamado} finalizado com sucesso no banco via {status_site}.")
        except Exception as e:
            logging.error(f"Erro ao extrair finalização do {nr_chamado}: {e}")
        finally:
            session.close()

    def encerrar(self):
        self.driver.quit()
        logging.info("Robô finalizado.")