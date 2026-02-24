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
        Configura e inicia o ChromeDriver com opções de headless e maximização de janela.
        Retorna o objeto WebDriver.

        """
        options = webdriver.ChromeOptions()
        if os.getenv("MODO_HEADLESS") == "True":
            options.add_argument("--headless")
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    def fechar_modal_se_existir(self):
        """
        Verifica se existe um modal de notificação na tela e o fecha para evitar bloqueios na automação.   
        O método é projetado para ser resiliente, ignorando qualquer erro caso o modal não exista ou já tenha sido fechado.
        Retorna None.
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
        Realiza o login no sistema da Tecnuv utilizando as credenciais armazenadas nas variáveis de ambiente.
        O método é projetado para lidar com possíveis mensagens de erro na tela e validar o acesso antes de prosseguir para a página principal dos chamados.
        Retorna True se o login for bem-sucedido e a página principal for acessada, ou False em caso de falha.

        """
        try:
            logging.info("Acessando página de login...")
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/login/")
            
           
            usuario_cru = os.getenv("TECNUV_USER", "")
            senha_cru = os.getenv("TECNUV_PASS", "")
            
            usuario_limpo = usuario_cru.encode('utf-8').decode('utf-8-sig').strip().replace('"', '').replace("'", "")
            senha_limpa = senha_cru.encode('utf-8').decode('utf-8-sig').strip().replace('"', '').replace("'", "")
            
          
            xpath_user = "//div[contains(@class, 'card-container')]//input[@name='userdata[user]']"
            xpath_pass = "//div[contains(@class, 'card-container')]//input[@name='userdata[pass]']"
            xpath_btn  = "//div[contains(@class, 'card-container')]//button[@type='submit']"
            
            campo_usuario = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_user)))
            campo_senha = self.driver.find_element(By.XPATH, xpath_pass)
            botao_acessar = self.driver.find_element(By.XPATH, xpath_btn)
            
            # 3. Preenchimento
            logging.info("Preenchendo credenciais no formulário principal...")
            campo_usuario.clear()
            campo_usuario.send_keys(usuario_cru)
            time.sleep(1)
            
            campo_senha.clear()
            campo_senha.send_keys(senha_cru)
            time.sleep(1)
            
            # 4. CLIQUE VIA JAVASCRIPT
            logging.info("Clicando em Acessar...")
            self.driver.execute_script("arguments[0].click();", botao_acessar)
            
            # 5. Validação
            time.sleep(3)
            try:
                erro_msg = self.driver.find_elements(By.XPATH, "//a[contains(@style, 'color: red')]")
                if erro_msg and erro_msg[0].text.strip():
                    logging.error(f"O site recusou o acesso: {erro_msg[0].text}")
                    return False
            except NoSuchElementException:
                pass 

            logging.info("Login realizado com sucesso!")
            
            self.driver.get("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//table")))
            logging.info("Fila principal acessada com sucesso.")
            
            return True
            
        except Exception as e:
            logging.error(f"Falha no login: {e}")
            return False

    def configurar_filtros(self):
        """
        Aplica limpeza de cache, define paginação e aplica filtros de status para garantir que a tabela de chamados esteja configurada corretamente para a extração.
        O método é projetado para ser resiliente, lidando com a ausência de elementos de limpeza de cache e continuando a configuração mesmo que alguns passos falhem, garantindo a melhor chance de sucesso na extração dos dados.     
        Retorna True se a configuração for aplicada com sucesso, ou False em caso de falha crítica durante o processo.
    
        
        """
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
                
                
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "btnBusca"))
                )
                time.sleep(2) # Pausa extra para garantir a conclusão de scripts internos do site
            except TimeoutException:
                
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
                "Em aberto", 
                "Encerrado", 
                "Cancelado", 
                "Em analise", 
                "Pendente representante", 
                "Pendente tecnuv", 
                "Em Desenvolvimento", 
                "Em Fila de Desenvolvimento", 
                "Em Andamento", 
                "Aguardando Liberacao de Versao", 
                "Aguardando Avaliacao", 
                "Enviado Para Qualidade", 
                "Retorno Qualidade"
            ]
            
            checkboxes = self.driver.find_elements(By.XPATH, "//ul[contains(@class, 'multiselect-container')]//input[@type='checkbox']")
            logging.info("Ajustando checkboxes de Status com os valores exatos do HTML...")
            
            for check in checkboxes:
                valor_exato = check.get_attribute("value")
                
                # Pula o checkbox "Selecionar Todos"
                if valor_exato == "multiselect-all":
                    continue 
                
                is_selected = check.is_selected()
                
                # 2. Comparações diretas e cliques na label (pai do checkbox)
                if valor_exato in status_desejados and not is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
                elif valor_exato not in status_desejados and is_selected:
                    check.find_element(By.XPATH, "./parent::label").click()
            
            btn_status.click()
            
            # 4. APLICAÇÃO DA BUSCA (Ordem Crítica 4)
            btn_busca = self.driver.find_element(By.ID, "btnBusca")
            btn_busca.click()
            
            logging.info("Filtros aplicados. Aguardando recarregamento da tabela final...")
            time.sleep(5) 
            
            return True
            
        except Exception as e:
            logging.error(f" Erro crítico ao configurar filtros: {e}")
            return False

    def extrair_data_alteracao(self, html_icone):
        """
        Regex para pegar a data do ícone 'i' de última alteração, que é o gatilho para saber se precisamos raspar o chamado novamente ou não. O formato esperado é "dd/MM/yyyy HH:mm:ss" dentro do atributo innerHTML do ícone.
        Retorna um objeto datetime se a data for encontrada e convertida com sucesso, ou None caso contrário.

        """
        match = re.search(r'(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})', html_icone)
        if match:
            return datetime.strptime(match.group(1), "%d/%m/%Y %H:%M:%S")
        return None

    def varrer_tabela(self):
        """
Percorre a tabela de chamados na página principal, extrai os metadados de cada chamado e decide se é necessário raspar os detalhes do chamado com base em comparações com o banco de dados. O método é dividido em duas fases principais:
1. Coleta de Metadados: Varre cada linha da tabela, extrai os metadados visíveis (número do chamado, link, status, data de abertura, etc.) e armazena em uma lista temporária.      
2. Verificação e Raspagem: Para cada item coletado, verifica se o chamado já existe no banco de dados. Se for um novo chamado ou se houver mudanças significativas (como alteração de status ou data de última modificação), o método navega até a página de detalhes do chamado e executa a raspagem profunda para extrair todas as informações relevantes. O método é projetado para ser resiliente, lidando com possíveis erros de extração e garantindo que o banco de dados seja atualizado corretamente com as informações mais recentes. Retorna None.   
3. Auto-Cura de Falhas: Após a varredura inicial, o método também inclui uma rotina de auto-cura que identifica chamados que falharam na raspagem profunda (por exemplo, devido a dados nulos) e tenta raspar novamente esses chamados específicos com um navegador limpo para garantir a integridade dos dados no banco.   
4. Logs Detalhados: Durante todo o processo, o método registra logs detalhados para monitorar o progresso, identificar possíveis falhas e garantir a transparência das operações realizadas pelo robô.  
5. Otimização de Performance: A varredura é otimizada para minimizar o número de acessos à página de detalhes, realizando verificações prévias com os metadados coletados para decidir quando é realmente necessário acessar a página de detalhes do chamado, reduzindo assim o tempo total de execução e a carga no sistema da Tecnuv. 

        """
        session = self.Session()
        chamados_coletados = []

        try:
            linhas = self.driver.find_elements(By.XPATH, "//table/tbody/tr")
            logging.info(f"Fase 1: Coletando metadados de {len(linhas)} linhas...")

            for linha in linhas:
                try:
                    btn_abrir = linha.find_element(By.CSS_SELECTOR, "a.btn-primary")
                    link = btn_abrir.get_attribute("href")
                    nr_chamado = int(link.split("/")[-1])
                    
                    tds = linha.find_elements(By.TAG_NAME, "td")
                    
                    # TRAVA DE SEGURANÇA: Nome do Cliente (Coluna 2 -> Índice 1)
                    cliente_tabela = tds[1].text.strip()
                    
                    # Se for o cliente restrito, ignora e pula para a próxima linha da tabela
                    if "TECNUV SISTEMAS" in cliente_tabela.upper():
                        continue
                    
                    # MAPEAMENTO ÍNDICES
                    ticket_vinc_web = tds[2].text.strip()
                    data_abertura_str = tds[5].text.strip() 
                    setor_web = tds[6].text.strip()
                    status_web = tds[7].text.strip() 
                    situacao_web = tds[8].text.strip()
                    prioridade_web = tds[9].text.strip()
                    
                    dt_abertura = None
                    if data_abertura_str:
                        try:
                            dt_abertura = datetime.strptime(data_abertura_str, "%d/%m/%Y %H:%M:%S")
                        except ValueError:
                            pass

                    icone_i = linha.find_element(By.XPATH, ".//a[contains(@class, 'dcontexto')]")
                    data_alt_web = self.extrair_data_alteracao(icone_i.get_attribute("innerHTML"))

                    chamados_coletados.append({
                        "nr_chamado": nr_chamado,
                        "link": link,
                        "ticket_vinculado": ticket_vinc_web,
                        "setor": setor_web,
                        "status_web": status_web,
                        "situacao": situacao_web,
                        "prioridade": prioridade_web,
                        "dt_abertura": dt_abertura,
                        "data_alt_web": data_alt_web
                    })
                except NoSuchElementException:
                    continue 
                except Exception as e:
                    logging.warning(f"Erro ao coletar linha: {e}")
                    continue

            logging.info(f"Fase 1 Concluída. {len(chamados_coletados)} chamados mapeados.")
            
           
            # FASE 2: VERIFICAÇÃO NO BANCO E RASPAGEM
          
            logging.info("Fase 2: Iniciando processamento...")
            
            for item in chamados_coletados:
                nr_chamado = item["nr_chamado"]
                link = item["link"]
                status_web = item["status_web"]
                data_alt_web = item["data_alt_web"]
                
                chamado_db = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                precisa_raspar = False

                if not chamado_db:
                    logging.info(f"[*] {nr_chamado}: Novo chamado. Agendando raspagem...")
                    new_c = ChamadoTecnuv(
                        nr_chamado=nr_chamado, 
                        ticket_vinculado=item["ticket_vinculado"],
                        setor=item["setor"],
                        status_atual=status_web, 
                        situacao=item["situacao"],
                        prioridade=item["prioridade"],
                        data_abertura=item["dt_abertura"],
                        ultima_alteracao_tecnuv=data_alt_web
                    )
                    session.add(new_c)
                    precisa_raspar = True
                else:
                    # Atualiza os dados da grid dinamicamente caso o atendente altere na Tecnuv
                    mudou_metadados = False
                    if chamado_db.ticket_vinculado != item["ticket_vinculado"]: chamado_db.ticket_vinculado = item["ticket_vinculado"]; mudou_metadados = True
                    if chamado_db.setor != item["setor"]: chamado_db.setor = item["setor"]; mudou_metadados = True
                    if chamado_db.situacao != item["situacao"]: chamado_db.situacao = item["situacao"]; mudou_metadados = True
                    if chamado_db.prioridade != item["prioridade"]: chamado_db.prioridade = item["prioridade"]; mudou_metadados = True

                    if chamado_db.status_atual != status_web:
                        log_status = HistoricoTransicaoStatus(
                            nr_chamado=nr_chamado, 
                            status_anterior=chamado_db.status_atual, 
                            status_novo=status_web
                        )
                        session.add(log_status)
                        chamado_db.status_atual = status_web
                        precisa_raspar = True
                    
                    elif data_alt_web and (not chamado_db.ultima_alteracao_tecnuv or data_alt_web > chamado_db.ultima_alteracao_tecnuv):
                        chamado_db.ultima_alteracao_tecnuv = data_alt_web
                        precisa_raspar = True
                        
                    elif mudou_metadados:
                        
                        session.commit()

                if precisa_raspar:
                    session.commit()
                    self.driver.get(link)
                    self.fechar_modal_se_existir()
                    self.deep_scrape_chamado_atual(nr_chamado)

            logging.info("Sincronização finalizada.")

        finally:
            session.close()

    def deep_scrape_chamado_atual(self, nr_chamado):
        """
        Extrai os dados do chamado na aba ATUAL (Sem abrir novas guias), incluindo cliente, atendente, usuário, motivo de abertura e histórico de interações. O método é projetado para ser resiliente, implementando tentativas de raspagem com tratamento de exceções para garantir que os dados sejam extraídos corretamente mesmo em caso de falhas temporárias na página ou elementos ausentes. Os dados extraídos são então atualizados no banco de dados, garantindo que as informações mais recentes do chamado estejam sempre disponíveis para consulta. Retorna None.
        
        """
        session = self.Session()
        max_tentativas = 3
        
        for tentativa in range(1, max_tentativas + 1):
            try:
                # Aguarda o título "Num. Chamado:" carregar na tela
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Num. Chamado:')]")))
                
                def get_val(label_text):
                    """
                    Função auxiliar para extrair o texto associado a um label específico, utilizando XPath para localizar o elemento correto. O método é projetado para ser resiliente, retornando "Não Informado" caso o elemento não seja encontrado ou esteja vazio, garantindo que a raspagem continue mesmo em casos de dados ausentes. Retorna o texto extraído.  

                    """
                    try: 
                        xpath = f"//label[normalize-space(text())='{label_text}']/following-sibling::span"
                        texto = self.driver.find_element(By.XPATH, xpath).text.strip()
                        return texto if texto else "Não Informado"
                    except: 
                        return "Não Informado"

                cliente = get_val("Cliente:")
                atendente = get_val("Atendente:")
                usuario = get_val("Usuário:")
                
                try:
                    div_motivo = self.driver.find_element(By.ID, "tecnuv_motivo")
                    html_motivo = div_motivo.get_attribute("innerHTML").strip()
                except NoSuchElementException:
                    html_motivo = ""

                chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
                if chamado:
                    chamado.cliente_nome = cliente
                    chamado.atendente_tecnuv = atendente
                    chamado.usuario_epsy = usuario
                    chamado.motivo_abertura_html = html_motivo
                    chamado.assunto_html = html_motivo 

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
                logging.info(f"[OK] Chamado {nr_chamado} sincronizado (Tentativa {tentativa}).")
                break 
                
            except Exception as e:
                session.rollback()
                logging.warning(f"[AVISO] Falha na raspagem do chamado {nr_chamado} (Tentativa {tentativa}/{max_tentativas}). Erro: {e}")
                time.sleep(2) 
                if tentativa == max_tentativas:
                    logging.error(f"[ERRO] Raspagem do chamado {nr_chamado} abortada.")
            finally:
                session.close()
    def recuperar_falhas_raspagem(self):
        """
        Busca no banco chamados com dados nulos e tenta raspar novamente com um navegador limpo para garantir a integridade dos dados. O método é projetado para ser resiliente, lidando com possíveis erros durante a raspagem e garantindo que o processo de recuperação seja realizado de forma eficiente, minimizando o impacto no desempenho do sistema. Durante a execução, o método registra logs detalhados para monitorar o progresso e identificar possíveis falhas na rotina de auto-cura. Retorna None. 

        """
        session = self.Session()
        try:
            # Busca chamados onde o Deep Scrape falhou (ex: cliente_nome está nulo)
            chamados_falhos = session.query(ChamadoTecnuv).filter(
                (ChamadoTecnuv.cliente_nome == None) | (ChamadoTecnuv.cliente_nome == "")
            ).all()
            
            if not chamados_falhos:
                logging.info("[OK] Fase 3 ignorada: Todos os chamados foram raspados perfeitamente na primeira tentativa.")
                return

            logging.info(f"Fase 3: Iniciando rotina de Auto-Cura para {len(chamados_falhos)} chamados com falha...")
            
            
            logging.info("Reiniciando o ChromeDriver para limpar a memória RAM...")
            self.driver.quit()
            
            self.driver = self._iniciar_driver()
            self.wait = WebDriverWait(self.driver, 15)
            
            
            if not self.login():
                logging.error("Falha ao relogar na fase de recuperação. Abortando auto-cura.")
                return
                
            
            for chamado in chamados_falhos:
                nr_chamado = chamado.nr_chamado
                link = f"https://postogestor.com.br/helpdesk/sistema/tecnuv/editar/id/{nr_chamado}"
                
                logging.info(f"Resgatando dados do chamado {nr_chamado}...")
                self.driver.get(link)
                self.fechar_modal_se_existir()
                self.deep_scrape_chamado_atual(nr_chamado)
                
            logging.info("Fase de Auto-Cura (Fase 3) finalizada com sucesso.")
            
        except Exception as e:
            logging.error(f"Erro crítico na rotina de Auto-Cura: {e}")
        finally:
            session.close()


    def fechar_modal_se_existir(self):
        """
        Tenta fechar modais de notificação sem travar a performance do robô. O método é projetado para ser resiliente, ignorando qualquer erro caso o modal não exista ou já tenha sido fechado, garantindo que a automação continue fluida sem interrupções desnecessárias. Retorna None.  

        """
        try:
            modais = self.driver.find_elements(By.CSS_SELECTOR, ".modal-dialog .close")
            if modais and modais[0].is_displayed():
                modais[0].click()
                logging.info("[OK] Modal de notificação interceptado e fechado.")
        except Exception:
            pass 
            
    def encerrar(self):
        """
Encerra o ChromeDriver e finaliza o robô, garantindo que os recursos sejam liberados corretamente. 
O método é projetado para ser resiliente, lidando com possíveis erros durante o processo de encerramento e garantindo que o log seja atualizado para refletir a finalização do robô. 
Retorna None.   
        """
        self.driver.quit()
        logging.info("Robô finalizado.")