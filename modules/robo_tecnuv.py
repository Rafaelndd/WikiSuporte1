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
    handlers=[logging.FileHandler("oraculo_engine.log"), logging.StreamHandler()]
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
        self.wait = WebDriverWait(self.driver, 15)

    def _iniciar_driver(self):
        """
        Configura e inicia o ChromeDriver com opções de segurança e performance.
        """
        options = webdriver.ChromeOptions()
        if os.getenv("MODO_HEADLESS") == "True":
            options.add_argument("--headless")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

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

    # def varrer_tabela(self):
    #     """
    #     fase 1 e 2: coleta metadados e decide o que raspar profundamente.
    #     """
    #     session = self.session()
    #     try:
    #         linhas = self.driver.find_elements(by.xpath, "//table/tbody/tr")
    #         chamados_coletados = []

    #         for linha in linhas:
    #             try:
    #                 tds = linha.find_elements(by.tag_name, "td")
    #                 cliente_tabela = tds[1].text.strip()
                    
    #                 # trava de segurança obrigatória
    #                 if "tecnuv sistemas" in cliente_tabela.upper():
    #                     continue
                    
    #                 btn_abrir = linha.find_element(by.css_selector, "a.btn-primary")
    #                 link = btn_abrir.get_attribute("href")
    #                 nr_chamado = int(link.split("/")[-1])
                    
    #                 # metadados básicos
    #                 status_web = tds[7].text.strip()
    #                 chamados_coletados.append({
    #                     "nr_chamado": nr_chamado,
    #                     "link": link,
    #                     "status_web": status_web
    #                 })
    #             except: continue

    #         for item in chamados_coletados:
    #             nr_chamado = item["nr_chamado"]
    #             chamado_db = session.query(chamadotecnuv).filter_by(nr_chamado=nr_chamado).first()
                
    #             # só raspa se for novo, mudou o status ou nunca pegou a versão
    #             if not chamado_db or chamado_db.status_atual != item["status_web"] or not chamado_db.versao_sistema:
    #                 self.driver.get(item["link"])
    #                 self.fechar_modal_se_existir()
    #                 self.deep_scrape_chamado_atual(nr_chamado)
                    
    #     finally:
    #         session.close()

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
                
                # Aguarda as linhas da tabela carregarem
                self.wait.until(EC.presence_of_all_elements_located((By.XPATH, "//table/tbody/tr")))
                linhas = self.driver.find_elements(By.XPATH, "//table/tbody/tr")
                for linha in linhas:
                    try:
                        tds = linha.find_elements(By.TAG_NAME, "td")
                        if not tds: 
                            continue
                        
                        # LOG DE DEPURAÇÃO: Vamos ver o que o robô está lendo na coluna 1
                        cliente_tabela = tds[1].text.strip()
                        # logging.info(f"Analisando chamado do cliente: {cliente_tabela}") # Opcional: muita poluição se ligado

                        if "TECNUV SISTEMAS" in cliente_tabela.upper():
                            continue
                        
                        btn_abrir = linha.find_element(By.CSS_SELECTOR, "a.btn-primary")
                        link = btn_abrir.get_attribute("href")
                        nr_chamado = int(link.split("/")[-1])
                        
                        # --- VERIFICAÇÃO DO ÍCONE (Ponto provável de erro) ---
                        try:
                            icone_i = linha.find_element(By.XPATH, ".//a[contains(@class, 'dcontexto')]")
                            html_icone = icone_i.get_attribute("innerHTML")
                            data_alt_web = self.extrair_data_alteracao(html_icone)
                        except:
                            # Se não achar o ícone, não mata o chamado, apenas deixa a data nula
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
                        # AGORA O LOG VAI DIZER O QUE ACONTECEU
                        logging.error(f"Erro ao processar linha da tabela: {e}")
                        continue
                # for linha in linhas:
                #     try:
                #         tds = linha.find_elements(By.TAG_NAME, "td")
                #         if not tds: continue
                        
                #         cliente_tabela = tds[1].text.strip()
                        
                #         # TRAVA DE SEGURANÇA: Ignora cliente restrito
                #         if "TECNUV SISTEMAS" in cliente_tabela.upper():
                #             continue
                        
                #         btn_abrir = linha.find_element(By.CSS_SELECTOR, "a.btn-primary")
                #         link = btn_abrir.get_attribute("href")
                #         nr_chamado = int(link.split("/")[-1])
                        
                #         # Captura metadados para comparação no banco
                #         status_web = tds[7].text.strip()
                #         icone_i = linha.find_element(By.XPATH, ".//a[contains(@class, 'dcontexto')]")
                #         data_alt_web = self.extrair_data_alteracao(icone_i.get_attribute("innerHTML"))

                #         chamados_coletados.append({
                #             "nr_chamado": nr_chamado,
                #             "link": link,
                #             "status_web": status_web,
                #             "data_alt_web": data_alt_web,
                #             # Adicionamos metadados extras para o banco se for novo
                #             "ticket_vinculado": tds[2].text.strip(),
                #             "setor": tds[6].text.strip(),
                #             "situacao": tds[8].text.strip(),
                #             "prioridade": tds[9].text.strip(),
                #             "dt_abertura_str": tds[5].text.strip()
                #         })
                #     except Exception as e:
                #         continue

                # LÓGICA DE PAGINAÇÃO: Procura o botão "Próximo"
                try:
                    # Seletor baseado no seu HTML: a[title='próxima página']
                    btn_proximo = self.driver.find_elements(By.CSS_SELECTOR, "a[title='próxima página']")
                    
                    if btn_proximo and btn_proximo[0].is_displayed():
                        pagina_atual += 1
                        logging.info(f"Indo para a página {pagina_atual}...")
                        
                        # Clica no botão e aguarda um pequeno delay para o AJAX do site responder
                        self.driver.execute_script("arguments[0].click();", btn_proximo[0])
                        time.sleep(4) 
                    else:
                        logging.info("Chegamos à última página da tabela.")
                        break
                except NoSuchElementException:
                    break

            # --- FASE 2: PROCESSAMENTO E DEEP SCRAPE ---
            logging.info(f"Total de {len(chamados_coletados)} chamados mapeados. Iniciando verificações no banco...")
            
            for item in chamados_coletados:
                nr_chamado = item["nr_chamado"]
                chamado_db = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                
                # --- ADICIONADO: TRAVA DE ESTADO TERMINAL ---
                # Se o chamado já está encerrado ou cancelado no NOSSO banco, 
                # ignoramos completamente qualquer nova raspagem.
                if chamado_db and chamado_db.status_atual in ["Encerrado", "Cancelado"]:
                    continue 

                precisa_raspar = False
                # ... resto da lógica (if not chamado_db / if status_atual != item["status_web"]) ...

                if not chamado_db:
                    # Se não existe, cria o registro básico e agenda raspagem
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
                    # Se existe, checa se mudou o status ou a data de alteração
                    if chamado_db.status_atual != item["status_web"]:
                        # Grava histórico de transição
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

                # Se for identificado que precisa de raspagem profunda
                if precisa_raspar:
                    session.commit()
                    self.driver.get(item["link"])
                    self.fechar_modal_se_existir()
                    self.deep_scrape_chamado_atual(nr_chamado)
                
                

            logging.info("Sincronização completa de todas as páginas finalizada.")

            # --- LÓGICA DE ÓRFÃOS: QUEM SUMIU DA FILA? ---
            ids_vistos = [item["nr_chamado"] for item in chamados_coletados]
        
        # Busca no banco quem está ATIVO mas não foi visto nesta varredura
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
        """
        session = self.Session()
        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Num. Chamado:')]")))
            
            # Função interna para pegar texto de labels
            def get_val(label_text):
                try: 
                    xpath = f"//label[normalize-space(text())='{label_text}']/following-sibling::span"
                    return self.driver.find_element(By.XPATH, xpath).text.strip()
                except: return "Não Informado"

            # 1. Captura da Versão (Novo Requisito)
            try:
                # Localiza o input pelo ID fornecido no HTML
                campo_versao = self.driver.find_element(By.ID, "tecnuv_versao_abertura")
                versao = campo_versao.get_attribute("value").strip()
            except:
                versao = "Não Informada"

            # 2. Captura do Motivo/Assunto
            try:
                html_motivo = self.driver.find_element(By.ID, "tecnuv_motivo").get_attribute("innerHTML").strip()
            except: html_motivo = ""

            # 3. Atualização no Banco
            chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
            if chamado:
                chamado.cliente_nome = get_val("Cliente:")
                chamado.atendente_tecnuv = get_val("Atendente:")
                chamado.usuario_epsy = get_val("Usuário:")
                chamado.versao_sistema = versao # Salvando a nova informação
                chamado.motivo_abertura_html = html_motivo
                chamado.assunto_html = html_motivo

            session.commit()
            logging.info(f"[OK] Detalhes do chamado {nr_chamado} sincronizados (Versão: {versao}).")
        except Exception as e:
            session.rollback()
            logging.error(f"Erro no Deep Scrape {nr_chamado}: {e}")
        finally:
            session.close()

    def recuperar_falhas_raspagem(self):
        """
        Fase 3: Auto-Cura para dados nulos OU Versões não capturadas (Retroativo).
        """
        session = self.Session()
        try:
            # --- AJUSTADO: FILTRO PARA IGNORAR ESTADOS TERMINAIS ---
            chamados_falhos = session.query(ChamadoTecnuv).filter(
                (
                    (ChamadoTecnuv.cliente_nome == None) | 
                    (ChamadoTecnuv.cliente_nome == "") |
                    (ChamadoTecnuv.versao_sistema == None)
                ),
                # A vírgula no .filter funciona como um "AND"
                # Ignora os que já estão encerrados ou cancelados
                ChamadoTecnuv.status_atual.notin_(["Encerrado", "Cancelado"])
            ).all()
            
            if not chamados_falhos:
                return

            logging.info(f"Iniciando Auto-Cura para {len(chamados_falhos)} chamados (Varredura Retroativa)...")
            
            # Reinicia para limpar RAM
            self.driver.quit()
            self.driver = self._iniciar_driver()
            self.wait = WebDriverWait(self.driver, 15)
            if self.login():
                for chamado in chamados_falhos:
                    link = f"https://postogestor.com.br/helpdesk/sistema/tecnuv/editar/id/{chamado.nr_chamado}"
                    self.driver.get(link)
                    self.fechar_modal_se_existir()
                    self.deep_scrape_chamado_atual(chamado.nr_chamado)
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