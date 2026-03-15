import time
import os
import re
import sys
import logging


# Windows: evita UnicodeEncodeError no console ao logar/imprimir emoji
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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
from services.db_homologacao import (
    processar_release_completo,
    get_helpdesk_release_head,
    set_helpdesk_release_head,
    _extrair_versao_do_titulo,
)
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
URL_HOME_ALT = "https://postogestor.com.br/helpdesk/home"
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

    def _texto_modal_release(self) -> str:
        """Conteúdo do release no modal: textarea, div ou body do modal."""
        seletores = [
            (By.CSS_SELECTOR, "textarea.msg3-noticia"),
            (By.CLASS_NAME, "msg3-noticia"),
            (By.CSS_SELECTOR, ".modal-body textarea"),
            (By.CSS_SELECTOR, "#modalNoticia textarea"),
            (By.CSS_SELECTOR, "div.msg3-noticia"),
            (By.CSS_SELECTOR, ".modal-content .modal-body"),
        ]
        for by, sel in seletores:
            try:
                el = self.driver.find_element(by, sel)
                t = (el.get_attribute("value") or el.get_attribute("innerHTML") or el.text or "").strip()
                if len(t) > 50:
                    return t
            except Exception:
                continue
        try:
            modal = self.driver.find_element(By.CSS_SELECTOR, ".modal.in, .modal.show, div.modal")
            return (modal.text or "").strip()
        except Exception:
            return ""

    def _fechar_modal_release(self):
        for sel in (
            "div.modal-header button.close",
            "button.close[data-dismiss='modal']",
            ".modal .close",
            "button.btn-default[data-dismiss='modal']",
        ):
            try:
                self.driver.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(0.5)
                return
            except Exception:
                continue
        try:
            self.driver.execute_script(
                "document.querySelectorAll('.modal').forEach(m=>{m.style.display='none'; m.classList.remove('in','show');});"
            )
        except Exception:
            pass

    def extrair_releases(self):
        """
        Só o 1º release da Home (o mais recente da Tecnuv). Compara com o banco:
        igual ao último sincronizado → não baixa de novo; diferente → abre modal, persiste e atualiza versão atual.
        """
        print("📦 Releases: apenas o 1º da Home (último liberado) + comparação com banco…")
        total_vinculados = 0
        total_ciclos = 0
        try:
            time.sleep(2)
            links_releases = []
            for by, sel in [
                (By.CLASS_NAME, "loadNoticia"),
                (By.CSS_SELECTOR, "a.loadNoticia"),
                (By.CSS_SELECTOR, "[class*='loadNoticia']"),
                (By.CSS_SELECTOR, "a[onclick*='Noticia']"),
                (By.CSS_SELECTOR, "a[onclick*='noticia']"),
                (By.XPATH, "//a[contains(@class,'loadNoticia')]"),
                (By.XPATH, "//*[contains(@onclick,'loadNoticia')]"),
            ]:
                try:
                    found = self.driver.find_elements(by, sel)
                    if found:
                        links_releases = [e for e in found if e.is_displayed()]
                        if links_releases:
                            print(f"   → {len(links_releases)} link(s) na Home; uso só o 1º (mais recente).")
                            break
                except Exception:
                    continue

            if not links_releases:
                print(
                    "⚠️ Nenhum elemento .loadNoticia na página. "
                    "Confirme URL da Home (deve listar notícias/releases)."
                )
                return

            link = links_releases[0]
            titulo_link = re.sub(r"\s+", " ", (link.text or "").strip())[:2000]
            ver_do_link = _extrair_versao_do_titulo(titulo_link)
            low = titulo_link.lower()
            if "pdv móvel" in low or "pdv movel" in low:
                ver_do_link = _extrair_versao_do_titulo(
                    titulo_link.split("PDV")[0] if "PDV" in titulo_link else titulo_link
                ) or ver_do_link

            db_titulo, db_ver = get_helpdesk_release_head()
            if titulo_link and db_titulo == titulo_link:
                print(
                    f"⏭️ Versão atual já é a do último release sincronizado "
                    f"({db_ver or '—'}). Nada a baixar."
                )
                return
            if ver_do_link and db_ver == ver_do_link and not db_titulo:
                print(f"⏭️ Mesma versão no banco ({db_ver}). Nada a baixar.")
                return

            print(f"🆕 Novo 1º release na Home (ou 1ª sync). Abrindo modal…")
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                time.sleep(0.3)
                link.click()
            except Exception as ex:
                print(f"⚠️ Clique no 1º release: {ex}")
                return

            try:
                WebDriverWait(self.driver, 12).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, ".modal.in, .modal.show, .modal-dialog, .msg1-noticia")
                    )
                )
            except Exception:
                print("⚠️ Modal não abriu.")
                self._fechar_modal_release()
                return

            try:
                titulo_el = self.driver.find_element(By.CLASS_NAME, "msg1-noticia")
                titulo_release = (titulo_el.text or titulo_el.get_attribute("innerText") or "").strip()
            except Exception:
                try:
                    titulo_release = self.driver.find_element(By.CSS_SELECTOR, ".modal-title").text.strip()
                except Exception:
                    titulo_release = titulo_link or "Release"

            texto_release = self._texto_modal_release()
            if not texto_release.strip():
                print(f"⚠️ Release sem texto: {titulo_release[:60]}…")
                self._fechar_modal_release()
                return

            ver_norm = _extrair_versao_do_titulo(titulo_release) or _extrair_versao_do_titulo(
                texto_release[:800]
            ) or ver_do_link
            try:
                qtd_vinculados, qtd_ciclos = processar_release_completo(
                    versao=titulo_release[:50].strip(),
                    texto_completo=texto_release,
                    autor="Processamento Automático (bot)",
                    nome_arquivo=titulo_link[:255] if titulo_link else None,
                    origem="raspagem",
                )
                total_vinculados += qtd_vinculados
                total_ciclos += qtd_ciclos
                set_helpdesk_release_head(titulo_link=titulo_link or titulo_release[:500], versao_norm=ver_norm)
                chamados = re.findall(r"\((\d{4,6})\)", texto_release)
                print(
                    f"✅ Versão atual atualizada → {ver_norm} | {titulo_release[:50]} | "
                    f"itens: {qtd_vinculados} | ciclos: {qtd_ciclos} | {chamados[:6]}"
                )
            except Exception as ex:
                print(f"⚠️ Erro ao persistir release: {ex}")

            self._fechar_modal_release()
            time.sleep(0.5)
            print(f"📊 Sync 1º release: {total_vinculados} itens/chamados, {total_ciclos} ciclos.")
        except Exception as e:
            print(f"❌ Erro ao ler Releases: {e}")
            import traceback
            traceback.print_exc()

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
        for url in (URL_HOME, URL_HOME_ALT):
            self.driver.get(url)
            self._pausa_servidor()
            time.sleep(2)
            try:
                if self.driver.find_elements(By.CLASS_NAME, "loadNoticia") or self.driver.find_elements(
                    By.CSS_SELECTOR, "[class*='loadNoticia']"
                ):
                    print(f"   Home carregada: {url}")
                    break
            except Exception:
                pass
        else:
            print(f"   Aviso: usando {URL_HOME} (sem confirmação de links)")
            self.driver.get(URL_HOME)
            time.sleep(2)
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

def _executar_ciclo_chamados():
    """Delega a raspagem de Chamados ao OraculoBot (selenium_raspagem)."""
    try:
        from modules.selenium_raspagem import _executar_ciclo_chamados as _run_chamados
        _run_chamados()
    except ImportError as e:
        print(f"⚠️ Módulo selenium_raspagem não disponível para Chamados: {e}")


def _executar_motor(tarefa: str | None = None):
    """
    Cria o motor, faz login e executa a raspagem.
    Se `tarefa` for 'chamados', usa OraculoBot. Caso contrário, MotorExtracao.
    Se None, executa todas as fontes do MotorExtracao.
    """
    if tarefa == "chamados":
        _executar_ciclo_chamados()
        return

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