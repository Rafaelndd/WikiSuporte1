import os
import re
import logging
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from datetime import datetime, timedelta
from dotenv import load_dotenv

# Playwright
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# Banco de Dados
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert
from modules.database import get_connection
from modules.log_redaction import install_sensitive_data_redaction
from modules.models import ChamadoTecnuv, HistoricoInteracao, HistoricoTransicaoStatus
from services.bot_control import definir_etapa, deve_parar


def _status_encerrado_cancelado(status_txt: str) -> bool:
    if not status_txt or not str(status_txt).strip():
        return False
    s = str(status_txt).strip().lower()
    return s in ("encerrado", "cancelado") or "encerrado" in s or "cancelado" in s


def _norm_lista_txt(v) -> str:
    return (str(v) if v is not None else "").strip()


def _lista_helpdesk_difere_do_banco(chamado_db, meta: dict) -> bool:
    """True se colunas espelhadas da grade TecNuv divergem do registro local."""
    pares = (
        ("setor", "setor"),
        ("situacao", "situacao"),
        ("prioridade", "prioridade"),
        ("ticket_vinculado", "ticket_vinculado"),
    )
    for attr, key in pares:
        if _norm_lista_txt(getattr(chamado_db, attr, None)) != _norm_lista_txt(meta.get(key)):
            return True
    return False


# Logs: arquivo UTF-8; consola Windows (cp1252) sem emoji para evitar UnicodeEncodeError
_log_file = logging.FileHandler("oraculo_engine.log", encoding="utf-8")
_log_console = logging.StreamHandler()
_log_console.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[_log_file, _log_console],
)
install_sensitive_data_redaction(logging.getLogger())

load_dotenv()


# ==========================================
# HELPERS DE LIBERAÇÃO
# ==========================================

def detectar_liberacao(texto):
    """
    Detecta se uma interação contém padrão de liberação da TecNuv.
    Só deve ser usada sobre interações individuais, nunca isoladamente.
    """
    return re.search(r"Este chamado foi liberado em vers", texto or "", re.IGNORECASE) is not None


def extrair_versao_liberacao(texto):
    """
    Extrai o número da versão citada na mensagem de liberação.
    Ex.: 'Este chamado foi liberado em versão 3.1.4' -> '3.1.4'
    """
    if not texto:
        return None
    m = re.search(r"vers(?:ão)?\s*([\d\.]+)", texto, flags=re.IGNORECASE)
    return m.group(1) if m else None


class OraculoBot:
    def __init__(self):
        """
        Inicializa o navegador (Playwright/Chromium), a conexão com o banco e as
        configurações de espera.
        A lista chamados_sem_permissao armazena IDs que o bot não conseguiu acessar.
        """
        self._playwright = None
        self.browser = None
        self.page = None
        self._iniciar_driver()
        self.engine = get_connection()
        self._garantir_schema_minimo()
        self.Session = sessionmaker(bind=self.engine)
        # Lista de chamados que o bot não tem permissão para acessar
        self.chamados_sem_permissao = []

    def _garantir_schema_minimo(self):
        """
        Auto-repara divergências de schema que quebram o ciclo do robô.
        Mantém compatibilidade com trigger update_modified_column().
        """
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    sa_text(
                        """
                        ALTER TABLE IF EXISTS chamados_tecnuv
                        ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMP
                        """
                    )
                )
                conn.execute(
                    sa_text(
                        """
                        UPDATE chamados_tecnuv
                        SET atualizado_em = COALESCE(atualizado_em, CURRENT_TIMESTAMP)
                        WHERE atualizado_em IS NULL
                        """
                    )
                )
            logging.info("[DB] Schema validado para chamados_tecnuv (coluna atualizado_em).")
        except Exception as e:
            logging.error(f"[DB] Falha ao validar schema mínimo de chamados_tecnuv: {e}")
            raise

    def _iniciar_driver(self):
        """
        Inicia o processo do Playwright (uma única vez por bot) e abre o navegador.
        """
        self._playwright = sync_playwright().start()
        self._abrir_navegador()

    def _abrir_navegador(self):
        """
        Abre um navegador Chromium (Playwright) novo com SUPER VISÃO no Modo Fantasma,
        reaproveitando o processo do Playwright já iniciado (self._playwright).

        Reaberto sem reiniciar sync_playwright(): iniciar um segundo
        sync_playwright().start() na mesma thread depois que alguma lib async
        (ex.: cliente Gemini/OpenAI usado na classificação) tocou num event loop
        asyncio quebra com "Playwright Sync API inside the asyncio loop".
        """
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

        self.browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--window-size=2560,1440",
                "--force-device-scale-factor=1.0",
                "--start-maximized",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # NOTA: mascara sinais de automação contra o helpdesk do fornecedor
                # (postogestor.com.br). Uso autorizado formalmente pela equipe/
                # fornecedor — confirmado em 2026-09-11 — não é uma tentativa de
                # burlar controle de acesso.
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": 2560, "height": 1440},
            device_scale_factor=1.0,
        )
        self.page = context.new_page()
        # Timeouts explícitos evitam travas silenciosas em execução longa (24/7).
        self.page.set_default_navigation_timeout(60_000)
        self.page.set_default_timeout(5_000)

    def _ler_linhas_grade_helpdesk(self):
        """
        Lê a grade da página de chamados em lote (uma chamada JS),
        reduzindo round-trips e risco de queda de sessão.
        """
        script = """
            () => {
                const rows = Array.from(document.querySelectorAll("table tbody tr"));
                return rows.map((tr) => {
                    const cols = Array.from(tr.querySelectorAll("td"));
                    return {
                        colunas: cols.map((td) => (td.innerText || "").trim()),
                        html_coluna_10: cols[10] ? (cols[10].innerHTML || "") : "",
                    };
                });
            }
        """
        return self.page.evaluate(script) or []

    def fechar_modal_se_existir(self):
        """Tenta fechar modais de notificação sem interromper o fluxo."""
        try:
            modal = self.page.locator(".modal-dialog .close").first
            if modal.count() and modal.is_visible():
                modal.click()
                logging.info("[OK] Modal de notificação interceptado e fechado.")
        except Exception:
            pass

    def _verificar_acesso_pagina(self, nr_chamado):
        """
        Verifica se o bot conseguiu acessar a página do chamado.
        Retorna True se acessou, False se foi bloqueado (sem permissão).
        Se bloqueado, adiciona o chamado à lista de sem permissão.
        """
        try:
            # Verifica se a página carregou o label de chamado (indica acesso OK)
            self.page.wait_for_selector(
                "xpath=//label[contains(text(), 'Num. Chamado:')]", timeout=4_000
            )
            return True
        except PlaywrightTimeoutError:
            pass

        # Verifica sinais de bloqueio/sem permissão na página
        try:
            page_text = (self.page.locator("body").inner_text() or "").lower()
            sinais_bloqueio = [
                "acesso negado", "sem permissão", "não autorizado",
                "access denied", "forbidden", "permissão negada",
                "você não tem permissão", "acesso restrito"
            ]
            for sinal in sinais_bloqueio:
                if sinal in page_text:
                    self.chamados_sem_permissao.append(nr_chamado)
                    logging.warning(
                        f"[SEM PERMISSÃO] Chamado {nr_chamado} - "
                        f"Acesso bloqueado. Adicionado à lista de não acessados."
                    )
                    return False
        except Exception:
            pass

        # Se não carregou e não achou mensagem de erro, assume bloqueio por timeout
        self.chamados_sem_permissao.append(nr_chamado)
        logging.warning(
            f"[SEM PERMISSÃO] Chamado {nr_chamado} - "
            f"Página não carregou (timeout). Adicionado à lista de não acessados."
        )
        return False

    def _esta_sem_permissao(self, nr_chamado):
        """Verifica se o chamado já foi marcado como sem permissão neste ciclo."""
        return nr_chamado in self.chamados_sem_permissao

    def login(self):
        """Realiza o login seguro no sistema da Tecnuv."""
        try:
            logging.info("Acessando página de login...")
            self.page.goto("https://postogestor.com.br/helpdesk/sistema/login/")

            usuario_cru = os.getenv("TECNUV_USER", "")
            senha_cru = os.getenv("TECNUV_PASS", "")

            xpath_user = "xpath=//div[contains(@class, 'card-container')]//input[@name='userdata[user]']"
            xpath_pass = "xpath=//div[contains(@class, 'card-container')]//input[@name='userdata[pass]']"
            xpath_btn = "xpath=//div[contains(@class, 'card-container')]//button[@type='submit']"

            campo_usuario = self.page.locator(xpath_user)
            campo_usuario.wait_for(state="visible", timeout=5_000)
            campo_senha = self.page.locator(xpath_pass)
            botao_acessar = self.page.locator(xpath_btn)

            campo_usuario.fill("")
            campo_usuario.fill(usuario_cru)
            campo_senha.fill("")
            campo_senha.fill(senha_cru)

            logging.info("Clicando em Acessar...")
            botao_acessar.evaluate("(el) => el.click()")

            self.page.wait_for_timeout(3_000)
            erro_msg = self.page.locator("xpath=//a[contains(@style, 'color: red')]")
            if erro_msg.count() and (erro_msg.first.text_content() or "").strip():
                logging.error(f"O site recusou o acesso: {erro_msg.first.text_content()}")
                return False

            logging.info("Login realizado com sucesso!")
            self.page.goto("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            return True

        except Exception as e:
            logging.error(f"Falha no login: {e}")
            return False

    # ==========================================
    # FASE 1: COLETAR TODOS OS ABERTOS NO HELPDESK (SEM FILTROS)
    # ==========================================

    def coletar_abertos_helpdesk(self):
        """
        Acessa o helpdesk, limpa filtros (visão nativa de ativos),
        aplica paginação 500 e percorre TODAS as páginas.
        Retorna dict {nr_chamado: metadados} de chamados considerados ATIVOS.

        Regra de atividade:
        - Primeiro, lê todos os chamados listados na tela (independente do status_web).
        - Em seguida, cruza com o banco de dados local e REMOVE todos os que já
          constam como 'Encerrado' ou 'Cancelado' em chamados_tecnuv.status_atual.
        Assim, mesmo que a tela liste históricos, a Fase 2 só trabalha com a fila ativa.
        """
        try:
            self.page.goto("https://postogestor.com.br/helpdesk/sistema/tecnuv")

            # Limpeza de Filtros (sem aplicar nenhum filtro de status)
            try:
                btn_limpar = self.page.locator("a.limpa_filtros")
                btn_limpar.wait_for(state="visible", timeout=3_000)
                btn_limpar.click()
                self.page.wait_for_timeout(2_000)
            except PlaywrightTimeoutError:
                pass

            # Paginação 500
            try:
                self.page.locator("xpath=//select[contains(@name, 'per_page')]").select_option("500")
                self.page.wait_for_timeout(1_000)
            except Exception:
                pass

            # Clica em Buscar (visão nativa sem filtros = apenas ativos)
            self.page.locator("#btnBusca").click()
            logging.info("[FASE 1] Buscando todos os chamados ativos no helpdesk (sem filtros)...")
            self.page.wait_for_timeout(5_000)

            chamados_helpdesk = {}
            pagina_atual = 1

            while True:
                logging.info(f"[FASE 1] Lendo página {pagina_atual}...")
                self.page.wait_for_selector("xpath=//table/tbody/tr")

                linhas = []
                for tentativa in range(1, 4):
                    try:
                        linhas = self._ler_linhas_grade_helpdesk()
                        break
                    except PlaywrightError as e:
                        if tentativa == 3:
                            raise RuntimeError(
                                f"[FASE 1] Falha ao ler grade na página {pagina_atual} após 3 tentativas: {e}"
                            ) from e
                        logging.warning(
                            f"[FASE 1] Instabilidade ao ler grade (página {pagina_atual}, tentativa {tentativa}/3): {e}"
                        )
                        self.page.wait_for_timeout(2_000)

                for linha in linhas:
                    try:
                        colunas = linha.get("colunas") or []
                        if len(colunas) < 11:
                            continue

                        cliente_tabela = colunas[1].strip()
                        if "TECNUV SISTEMAS" in cliente_tabela.upper():
                            continue

                        nr_chamado_str = colunas[0].strip()
                        if not nr_chamado_str.isdigit():
                            continue

                        nr_chamado = int(nr_chamado_str)
                        status_web = colunas[7].strip()
                        if _status_encerrado_cancelado(status_web):
                            continue

                        data_alt_web = None
                        try:
                            html_coluna_10 = linha.get("html_coluna_10") or ""
                            if "dcontexto" in html_coluna_10:
                                datas_encontradas = re.findall(
                                    r'(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}(?::\d{2})?)',
                                    html_coluna_10
                                )
                                if datas_encontradas:
                                    ultima_data_str = datas_encontradas[-1]
                                    try:
                                        data_alt_web = datetime.strptime(ultima_data_str, "%d/%m/%Y %H:%M:%S")
                                    except ValueError:
                                        data_alt_web = datetime.strptime(ultima_data_str, "%d/%m/%Y %H:%M")
                        except Exception as e:
                            logging.warning(f"Falha ao processar data do chamado {nr_chamado}: {e}")

                        chamados_helpdesk[nr_chamado] = {
                            "nr_chamado": nr_chamado,
                            "link": f"https://postogestor.com.br/helpdesk/sistema/tecnuv/editar/id/{nr_chamado}",
                            "status_web": status_web,
                            "data_alt_web": data_alt_web,
                            "ticket_vinculado": colunas[2].strip(),
                            "setor": colunas[6].strip(),
                            "situacao": colunas[8].strip(),
                            "prioridade": colunas[9].strip(),
                            "dt_abertura_str": colunas[5].strip()
                        }

                    except Exception as e:
                        logging.error(f"Erro ao processar linha da tabela: {e}")
                        continue

                # Próxima página
                try:
                    btn_proximo = self.page.locator("a[title='próxima página']")
                    if btn_proximo.count() and btn_proximo.first.is_visible():
                        pagina_atual += 1
                        btn_proximo.first.evaluate("(el) => el.click()")
                        self.page.wait_for_timeout(4_000)
                    else:
                        break
                except Exception:
                    break

            logging.info(f"[FASE 1] Total de chamados ativos encontrados no helpdesk: {len(chamados_helpdesk)}")
            # Filtro extra: remove da lista tudo que já está ENCERRADO/CANCELADO no banco
            try:
                with self.engine.connect() as conn:
                    rows = conn.execute(
                        sa_text(
                            """
                            SELECT nr_chamado
                            FROM chamados_tecnuv
                            WHERE TRIM(LOWER(COALESCE(status_atual, ''))) IN ('encerrado', 'cancelado')
                               OR LOWER(TRIM(COALESCE(status_atual, ''))) LIKE '%encerrado%'
                               OR LOWER(TRIM(COALESCE(status_atual, ''))) LIKE '%cancelado%'
                            """
                        )
                    ).fetchall()
                    encerrados_banco = {int(r[0]) for r in rows if r[0] is not None}
                if encerrados_banco:
                    antes = len(chamados_helpdesk)
                    chamados_helpdesk = {
                        k: v for k, v in chamados_helpdesk.items() if k not in encerrados_banco
                    }
                    logging.info(
                        f"[FASE 1] Filtro por banco: removidos {antes - len(chamados_helpdesk)} "
                        f"chamado(s) já Encerrado/Cancelado em chamados_tecnuv."
                    )
            except Exception as e:
                logging.warning(f"[FASE 1] Falha ao filtrar por status do banco: {e}")

            return chamados_helpdesk

        except Exception as e:
            logging.error(f"[FASE 1] Erro ao coletar abertos do helpdesk: {e}")
            return {}

    # ==========================================
    # FASE 2: COMPARAR HELPDESK vs BANCO E PROCESSAR DIFERENÇAS
    # ==========================================

    def comparar_e_processar(self, chamados_helpdesk):
        """
        1. Busca todos os chamados abertos no banco de dados.
        2. Compara com a lista vinda do helpdesk.
        3. Para cada DIFERENÇA, entra no chamado e busca o que mudou.
        4. Para chamados que SUMIRAM do helpdesk, busca nos encerrados/cancelados.
        Chamados sem permissão são registrados e pulados sem travar.
        """
        session = self.Session()
        try:
            # --- Passo 1: Buscar abertos no banco ---
            ids_helpdesk = set(chamados_helpdesk.keys())

            # Abertos no banco: exclui encerrado/cancelado (várias grafias)
            todos = session.query(ChamadoTecnuv).all()
            registros_banco = []
            for c in todos:
                st = (c.status_atual or "").strip().lower()
                if st in ("encerrado", "cancelado"):
                    continue
                if "encerrado" in st or "cancelado" in st:
                    continue
                if st == "analisado/arquivo":
                    continue
                registros_banco.append(c)

            banco_dict = {c.nr_chamado: c for c in registros_banco}
            ids_banco = set(banco_dict.keys())

            # --- Passo 2: Identificar diferenças ---
            novos_no_helpdesk = ids_helpdesk - ids_banco
            sumiram_do_helpdesk = ids_banco - ids_helpdesk
            em_ambos = ids_helpdesk & ids_banco

            logging.info(f"[FASE 2] Helpdesk: {len(ids_helpdesk)} | Banco: {len(ids_banco)}")
            logging.info(f"[FASE 2] Novos no helpdesk: {len(novos_no_helpdesk)}")
            logging.info(f"[FASE 2] Sumiram do helpdesk: {len(sumiram_do_helpdesk)}")
            logging.info(f"[FASE 2] Presentes em ambos: {len(em_ambos)}")

            sucesso_count = 0
            falhas_lista = []

            # --- Passo 3A: Chamados NOVOS (existem no helpdesk mas não no banco) ---
            for nr in novos_no_helpdesk:
                if deve_parar():
                    logging.warning("[PARADA] Encerramento manual solicitado — interrompendo ciclo de chamados.")
                    break
                if self._esta_sem_permissao(nr):
                    continue

                meta = chamados_helpdesk[nr]
                logging.info(f"[NOVO] Chamado {nr} encontrado no helpdesk. Inserindo no banco...")

                dt_abertura = None
                try:
                    dt_abertura = datetime.strptime(meta["dt_abertura_str"], "%d/%m/%Y %H:%M:%S")
                except Exception:
                    pass

                novo = ChamadoTecnuv(
                    nr_chamado=nr, status_atual=meta["status_web"],
                    ultima_alteracao_tecnuv=meta["data_alt_web"],
                    ticket_vinculado=meta["ticket_vinculado"],
                    setor=meta["setor"], situacao=meta["situacao"],
                    prioridade=meta["prioridade"], data_abertura=dt_abertura
                )
                if meta.get("data_alt_web"):
                    novo.ultima_alteracao_tecnuv = meta["data_alt_web"]
                session.add(novo)
                session.commit()
                logging.info(f"[DB] Chamado {nr} inserido na fila (commit).")

                # Tenta deep scrape — se não tiver permissão, pula
                self.page.goto(meta["link"])
                self.fechar_modal_se_existir()

                if self._verificar_acesso_pagina(nr):
                    if self.deep_scrape_chamado_atual(nr):
                        sucesso_count += 1
                    else:
                        falhas_lista.append(nr)

            # --- Passo 3B: Chamados que EXISTEM nos dois lados (prioridade: fila atual do helpdesk) ---
            em_ambos_lista = sorted(em_ambos)
            for nr in em_ambos_lista:
                if deve_parar():
                    logging.warning("[PARADA] Encerramento manual — interrompendo.")
                    break
                if self._esta_sem_permissao(nr):
                    continue

                meta = chamados_helpdesk[nr]
                chamado_db = banco_dict[nr]

                if chamado_db.status_atual in ["Encerrado", "Cancelado"]:
                    continue

                precisa_raspar = False
                motivo = ""

                # Status mudou?
                if chamado_db.status_atual != meta["status_web"]:
                    log_status = HistoricoTransicaoStatus(
                        nr_chamado=nr,
                        status_anterior=chamado_db.status_atual,
                        status_novo=meta["status_web"]
                    )
                    session.add(log_status)
                    chamado_db.status_atual = meta["status_web"]
                    precisa_raspar = True
                    motivo = "mudança de status"

                # Data de última alteração mudou?
                elif meta["data_alt_web"] and (
                    not chamado_db.ultima_alteracao_tecnuv
                    or meta["data_alt_web"] > chamado_db.ultima_alteracao_tecnuv
                ):
                    precisa_raspar = True
                    motivo = "nova alteração detectada"

                # Grade TecNuv (setor, situação, ticket EPSY, prioridade) divergiu do banco
                elif _lista_helpdesk_difere_do_banco(chamado_db, meta):
                    precisa_raspar = True
                    motivo = "lista TecNuv divergente do banco (setor/situação/vínculo/prioridade)"

                if precisa_raspar:
                    # Persistir já o que veio da lista (status, datas, setor…) antes do deep scrape
                    if meta.get("data_alt_web"):
                        chamado_db.ultima_alteracao_tecnuv = meta["data_alt_web"]
                    for attr, key in (
                        ("setor", "setor"),
                        ("situacao", "situacao"),
                        ("prioridade", "prioridade"),
                        ("ticket_vinculado", "ticket_vinculado"),
                    ):
                        if meta.get(key):
                            setattr(chamado_db, attr, meta[key])
                    chamado_db.ultima_verificacao_robo = datetime.now()
                    logging.info(f"[DIFERENÇA] Chamado {nr} - Motivo: {motivo}. Buscando detalhes...")
                    session.commit()
                    logging.info(f"[DB] Chamado {nr} lista/status gravados (commit). Deep scrape a seguir.")
                    self.page.goto(meta["link"])
                    self.fechar_modal_se_existir()

                    if self._verificar_acesso_pagina(nr):
                        if self.deep_scrape_chamado_atual(nr):
                            sucesso_count += 1
                        else:
                            falhas_lista.append(nr)

            # --- Passo 3C: Órfãos (no banco como abertos, não na lista atual do helpdesk) — limite por ciclo ---
            if sumiram_do_helpdesk and not deve_parar():
                orfaos = list(sumiram_do_helpdesk)
                try:
                    orfaos.sort(
                        key=lambda n: banco_dict[n].ultima_alteracao_tecnuv
                        or banco_dict[n].data_abertura
                        or datetime.min,
                        reverse=True,
                    )
                except Exception:
                    pass
                max_orfaos = 25
                fila = orfaos[:max_orfaos]
                logging.info(
                    f"[FASE 2] Órfãos: {len(orfaos)} no banco; neste ciclo investigando só {len(fila)} "
                    f"(mais recentes). Demais ficam para próximos ciclos — prioridade é a fila aberta do helpdesk."
                )

                # A busca de órfãos usa um widget de filtro (dropdown "Status") que fica
                # instável depois de centenas de navegações acumuladas nas Fases 1/2
                # (confirmado por diagnóstico: 100% de sucesso com sessão nova, falha
                # quase sempre numa sessão já longa). Reinicia o navegador antes de
                # começar, mesmo padrão já usado na Fase 3 (Auto-Cura).
                self._fechar_driver()
                self._abrir_navegador()
                sessao_orfaos_ok = self.login()
                if not sessao_orfaos_ok:
                    logging.warning(
                        "[FASE 2] Falha ao reautenticar para a busca de órfãos — pulando para este ciclo."
                    )

                if sessao_orfaos_ok:
                    for nr in fila:
                        if deve_parar():
                            break
                        if self._esta_sem_permissao(nr):
                            continue
                        logging.info(f"[ÓRFÃO] Chamado {nr} sumiu da lista ativa. Investigando...")
                        encontrado = self.executar_busca_especifica(nr)
                        if encontrado:
                            if self._verificar_acesso_pagina(nr):
                                self.deep_scrape_finalizacao(nr)
                        else:
                            logging.warning(f"[ÓRFÃO] Chamado {nr} não localizado em nenhuma busca.")

            # --- Relatório Final ---
            logging.info("====== RELATÓRIO DE SINCRONIZAÇÃO ======")
            logging.info(f"[OK] Chamados processados com sucesso: {sucesso_count}")
            logging.info(f"[NOVO] Inseridos neste ciclo: {len(novos_no_helpdesk)}")
            logging.info(f"[BUSCA] Investigados (sumiram da fila): {len(sumiram_do_helpdesk)}")
            if falhas_lista:
                logging.warning(f"[FALHA] Chamados com falha de leitura: {falhas_lista}")
            if self.chamados_sem_permissao:
                logging.warning(
                    f"[SEM_PERMISSAO] Chamados ({len(self.chamados_sem_permissao)}): "
                    f"{self.chamados_sem_permissao}"
                )
            logging.info("========================================")

        finally:
            session.close()

    # ==========================================
    # COLETA DE INTERAÇÕES DA PÁGINA DO CHAMADO
    # ==========================================

    def coletar_interacoes_atual(self, nr_chamado):
        """
        Lê os blocos de histórico na página do chamado já aberta.
        Retorna lista de dicts compatíveis com HistoricoInteracao.
        """
        interacoes = []
        blocos = self.page.locator("xpath=//div[contains(@class, 'col-md-11')]")
        for i in range(blocos.count()):
            bloco = blocos.nth(i)
            try:
                header = bloco.locator("label").first.text_content() or ""
                corpo_locator = bloco.locator(".msgMd").first
                corpo_html = corpo_locator.inner_html()
                corpo_txt = corpo_locator.inner_text()

                m = re.search(
                    r"Usuário:\s*(.*?)\s*-\s*Data:\s*(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})",
                    header
                )
                usuario = m.group(1).strip() if m else "Desconhecido"
                data_str = m.group(2) if m else None
                data_dt = datetime.strptime(data_str, "%d/%m/%Y %H:%M:%S") if data_str else None

                interacoes.append({
                    "nr_chamado": nr_chamado,
                    "data_interacao": data_dt,
                    "usuario": usuario,
                    "descricao_html": corpo_html or corpo_txt,
                    "_texto_limpo": corpo_txt,
                })
            except Exception as e:
                logging.warning(f"Falha ao parsear interação do chamado {nr_chamado}: {e}")
                continue
        return interacoes

    def registrar_interacoes(self, session, interacoes):
        """
        Upsert das interações no banco (evita duplicidade).
        Usa constraint uix_chamado_msg_autor (nr_chamado, data_interacao, usuario).
        """
        if not interacoes:
            return

        payload = []
        for i in interacoes:
            if i.get("data_interacao") and i.get("usuario"):
                payload.append({
                    "nr_chamado": i["nr_chamado"],
                    "data_interacao": i["data_interacao"],
                    "usuario": i["usuario"],
                    "descricao_html": i["descricao_html"],
                })

        if not payload:
            return

        stmt = insert(HistoricoInteracao).values(payload)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["nr_chamado", "data_interacao", "usuario"]
        )
        session.execute(stmt)

    def _processar_liberacoes(self, session, interacoes, chamado_db):
        """
        Percorre interações buscando liberação APENAS da TecNuv.
        Se encontrar, registra data e versão liberada.
        Indica que a TecNuv teoricamente resolveu, mas só confirma após testes do cliente.
        """
        if not chamado_db:
            return

        for inter in interacoes:
            usuario = (inter.get("usuario") or "").lower()
            if "tecnuv" not in usuario:
                continue

            texto = inter.get("_texto_limpo") or inter.get("descricao_html") or ""

            if detectar_liberacao(texto):
                versao = extrair_versao_liberacao(texto)

                if inter.get("data_interacao"):
                    chamado_db.ultima_alteracao_tecnuv = inter["data_interacao"]

                if versao and (not chamado_db.versao_sistema or chamado_db.versao_sistema == "Não Informada"):
                    chamado_db.versao_sistema = versao

                logging.info(
                    f"[LIBERAÇÃO] Chamado {chamado_db.nr_chamado} - "
                    f"Versão: {versao or 'não extraída'} - "
                    f"Data: {inter.get('data_interacao')} - "
                    f"(Aguarda validação do cliente)"
                )
                break

    # ==========================================
    # DEEP SCRAPE: DETALHES + INTERAÇÕES + LIBERAÇÃO
    # ==========================================

    def deep_scrape_chamado_atual(self, nr_chamado):
        """
        Extrai detalhes profundos do chamado.
        Coleta interações e verifica liberação pela TecNuv.
        Se o chamado não tiver permissão, já foi filtrado antes de chegar aqui.
        """
        session = self.Session()
        try:
            try:
                from modules.models import CobrancaChamado, ClienteVinculadoChamado
            except Exception:
                pass

            def get_val(label_text):
                try:
                    loc = self.page.locator(
                        f"xpath=//label[normalize-space(text())='{label_text}']/following-sibling::span"
                    )
                    return (loc.first.text_content() or "").strip()
                except Exception:
                    return "Não Informado"

            try:
                versao = (self.page.locator("#tecnuv_versao_abertura").first.input_value() or "").strip()
            except Exception:
                versao = "Não Informada"

            try:
                html_motivo = (self.page.locator("#tecnuv_motivo").first.inner_html() or "").strip()
            except Exception:
                html_motivo = ""
            try:
                from modules.html_texto import html_para_exibicao

                texto_limpo = html_para_exibicao(html_motivo, title_case=True)
            except Exception:
                texto_limpo = html_motivo

            chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
            if chamado:
                chamado.nome_cliente = get_val("Cliente:")
                chamado.atendente_tecnuv = get_val("Atendente:")
                chamado.usuario_epsy = get_val("Usuário:")
                chamado.versao_sistema = versao
                # Grava texto limpo (sem tags) para amostragem no sistema
                chamado.motivo_abertura_html = texto_limpo or html_motivo
                chamado.assunto_html = texto_limpo or html_motivo

                # Previsão de Conclusão
                previsao_str = get_val("Previsão de conclusão:")
                if previsao_str and previsao_str != "Não Informado":
                    try:
                        chamado.previsao_conclusao = datetime.strptime(previsao_str, "%d/%m/%Y").date()
                    except Exception:
                        pass

                # Cobranças
                try:
                    session.query(CobrancaChamado).filter_by(nr_chamado=nr_chamado).delete()
                    blocos_cobranca = self.page.locator("xpath=//div[contains(@style, '#EA4335')]")
                    for i in range(blocos_cobranca.count()):
                        cob = blocos_cobranca.nth(i)
                        try:
                            header = cob.locator("label").first.text_content() or ""
                            match = re.search(
                                r'Usuário:\s*(.*?)\s*-\s*Data:\s*(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})',
                                header
                            )
                            if match:
                                usu = match.group(1).strip()
                                dt = datetime.strptime(match.group(2), "%d/%m/%Y %H:%M:%S")
                                texto_msg = cob.locator(".msgMd").first.inner_text()
                                cli_match = re.search(r'pelo cliente\s+(.*?)\s+-', texto_msg)
                                cli_nome = cli_match.group(1).strip() if cli_match else "Não Identificado"
                                nova_cob = CobrancaChamado(
                                    nr_chamado=nr_chamado, data_cobranca=dt,
                                    analista_epsy=usu, cliente_solicitante=cli_nome,
                                    texto_bruto_cobranca=texto_msg
                                )
                                session.add(nova_cob)
                        except Exception as e:
                            logging.warning(f"Erro ao ler cobrança: {e}")
                except Exception:
                    pass

                # Clientes Vinculados
                try:
                    session.query(ClienteVinculadoChamado).filter_by(nr_chamado=nr_chamado).delete()
                    list_vinc = self.page.locator("#list-vinculo").first
                    textos = (list_vinc.inner_text() or "").split('\n')
                    for t in textos:
                        if t.strip():
                            cnpj_match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', t)
                            cnpj = cnpj_match.group(0) if cnpj_match else None
                            session.add(ClienteVinculadoChamado(
                                nr_chamado=nr_chamado,
                                nome_cliente=t.strip(),
                                cnpj_cliente=cnpj
                            ))
                except Exception:
                    pass

            # Coleta interações, salva e verifica liberação
            interacoes = self.coletar_interacoes_atual(nr_chamado)
            self.registrar_interacoes(session, interacoes)
            self._processar_liberacoes(session, interacoes, chamado)

            if chamado:
                chamado.ultima_verificacao_robo = datetime.now()
            session.commit()
            logging.info(f"[OK] Chamado {nr_chamado} sincronizado com sucesso (commit no banco).")
            # Classificação semântica (Erro / Melhoria / Adequação Fiscal) via pgvector
            try:
                from services.classificacao_chamados import classificar_chamado
                ok, cat, _ = classificar_chamado(nr_chamado)
                if ok:
                    logging.info(f"[IA] Chamado {nr_chamado} classificado: {cat}")
            except Exception as e_class:
                logging.debug("Classificação IA do chamado %s não executada: %s", nr_chamado, e_class)
            return True

        except Exception as e:
            session.rollback()
            logging.error(f"[ERRO] Falha no Deep Scrape do chamado {nr_chamado}: {str(e)}")
            return False
        finally:
            session.close()

    # ==========================================
    # BUSCA ESPECÍFICA (CHAMADOS QUE SUMIRAM)
    # ==========================================

    def executar_busca_especifica(self, nr_chamado):
        """
        Busca um chamado específico selecionando TODOS os status.
        Usado para encontrar chamados que sumiram da fila de ativos.
        """
        try:
            self.page.goto("https://postogestor.com.br/helpdesk/sistema/tecnuv")
            self.fechar_modal_se_existir()

            try:
                btn_limpar = self.page.locator("a.limpa_filtros")
                btn_limpar.wait_for(state="visible", timeout=3_000)
                btn_limpar.click()
                self.page.wait_for_timeout(2_000)
            except Exception:
                pass

            numero_limpo = str(nr_chamado).strip()
            campo = self.page.locator("#chamado")
            campo.wait_for(state="visible", timeout=5_000)
            campo.fill("")
            # Digita caractere a caractere (like o send_keys do Selenium): esta
            # grade tem busca-enquanto-digita em JS que escuta eventos de tecla
            # reais; .fill() só dispara um evento 'input' e deixa o widget de
            # Status num estado inconsistente/instável (timeout intermitente).
            campo.press_sequentially(numero_limpo, delay=50)

            # Botão de dropdown "Status" (multiselect Bootstrap): a checagem de
            # "clicável" do Playwright (não sobreposto/estável) é mais rígida que a
            # do Selenium e falha aqui apesar do elemento estar visível — usa clique
            # via JS, mesmo padrão já usado para o botão de login e paginação.
            btn_status = self.page.locator("xpath=//button[@title='Status']")
            btn_status.wait_for(state="visible", timeout=5_000)
            btn_status.evaluate("(el) => el.click()")
            self.page.wait_for_timeout(1_000)

            chk_all = self.page.locator("xpath=//input[@value='multiselect-all']").first
            if not chk_all.is_checked():
                chk_all.locator("xpath=./parent::label").evaluate("(el) => el.click()")
                self.page.wait_for_timeout(500)

            btn_status.evaluate("(el) => el.click()")

            self.page.locator("#btnBusca").click()
            self.page.wait_for_timeout(4_000)

            links = self.page.locator(f"xpath=//a[contains(@href, '/id/{numero_limpo}')]")
            if links.count():
                links.first.click()
                return True

            return False

        except Exception as e:
            logging.error(f"Erro na busca específica do chamado {nr_chamado}: {e}")
            return False

    def deep_scrape_finalizacao(self, nr_chamado):
        """
        Para chamados que sumiram da fila ativa:
        Extrai data de finalização/cancelamento, usuário responsável e mensagem final.
        """
        session = self.Session()
        try:
            self.page.wait_for_selector("xpath=//legend[contains(text(), 'Histórico')]")

            blocos = self.page.locator("xpath=//div[contains(@class, 'col-md-11')]")
            total_blocos = blocos.count()
            if not total_blocos:
                return

            ultimo = blocos.nth(total_blocos - 1)
            header = ultimo.locator("label").first.text_content() or ""
            corpo = (ultimo.locator(".msgMd").first.text_content() or "").strip()

            status_site = (
                self.page.locator(
                    "xpath=//label[contains(text(), 'Status:')]/following-sibling::span"
                ).first.text_content() or ""
            ).strip()

            match = re.search(
                r'Usuário:\s*(.*?)\s*-\s*Data:\s*(\d{2}/\d{2}/\d{4}\s\d{2}:\d{2}:\d{2})',
                header
            )

            chamado = session.query(ChamadoTecnuv).filter_by(nr_chamado=nr_chamado).first()
            if chamado:
                chamado.status_atual = status_site
                chamado.assunto_encerramento = corpo

                if match:
                    usuario = match.group(1).strip()
                    data_dt = datetime.strptime(match.group(2), "%d/%m/%Y %H:%M:%S")

                    if "ENCERRADO" in status_site.upper():
                        chamado.data_encerramento = data_dt
                        chamado.usuario_encerramento = usuario
                        logging.info(
                            f"[ENCERRADO] Chamado {nr_chamado} - "
                            f"Por: {usuario} - Data: {data_dt} - "
                            f"Mensagem: {corpo[:100]}..."
                        )
                    elif "CANCELADO" in status_site.upper():
                        chamado.data_cancelamento = data_dt
                        chamado.usuario_cancelamento = usuario
                        logging.info(
                            f"[CANCELADO] Chamado {nr_chamado} - "
                            f"Por: {usuario} - Data: {data_dt} - "
                            f"Mensagem: {corpo[:100]}..."
                        )

                # Coleta interações do chamado finalizado
                interacoes = self.coletar_interacoes_atual(nr_chamado)
                self.registrar_interacoes(session, interacoes)
                self._processar_liberacoes(session, interacoes, chamado)

                session.commit()
                logging.info(f"[OK] Órfão {nr_chamado} atualizado: {status_site}")

        except Exception as e:
            session.rollback()
            logging.error(f"Erro ao extrair finalização do {nr_chamado}: {e}")
        finally:
            session.close()

    # ==========================================
    # AUTO-CURA (FASE 3)
    # ==========================================

    def recuperar_falhas_raspagem(self):
        """
        Fase 3: Auto-Cura para dados nulos OU Versões não capturadas.
        Pula chamados que já estão na lista de sem permissão.
        """
        session = self.Session()
        try:
            chamados_falhos = session.query(ChamadoTecnuv).filter(
                (
                    (ChamadoTecnuv.nome_cliente == None) |
                    (ChamadoTecnuv.nome_cliente == "") |
                    (ChamadoTecnuv.versao_sistema == None)
                ),
                ChamadoTecnuv.status_atual.notin_(["Encerrado", "Cancelado"])
            ).all()

            if not chamados_falhos:
                logging.info("[FASE 3] Nenhum chamado com dados faltantes. Auto-Cura não necessária.")
                return

            # Filtra chamados sem permissão
            chamados_para_curar = [
                c for c in chamados_falhos
                if not self._esta_sem_permissao(c.nr_chamado)
            ]

            if not chamados_para_curar:
                logging.info("[FASE 3] Todos os chamados faltantes estão na lista de sem permissão. Pulando.")
                return

            logging.info(f"[FASE 3] Iniciando Auto-Cura para {len(chamados_para_curar)} chamados...")
            sucesso_count = 0
            falhas_lista = []

            self._fechar_driver()
            self._abrir_navegador()

            if self.login():
                for chamado in chamados_para_curar:
                    if self._esta_sem_permissao(chamado.nr_chamado):
                        continue

                    link = f"https://postogestor.com.br/helpdesk/sistema/tecnuv/editar/id/{chamado.nr_chamado}"
                    self.page.goto(link)
                    self.fechar_modal_se_existir()

                    if self._verificar_acesso_pagina(chamado.nr_chamado):
                        sucesso = self.deep_scrape_chamado_atual(chamado.nr_chamado)
                        if sucesso:
                            sucesso_count += 1
                        else:
                            falhas_lista.append(chamado.nr_chamado)

            logging.info("====== RELATÓRIO DE AUTO-CURA (FASE 3) ======")
            logging.info(f"[OK] Chamados recuperados (auto-cura): {sucesso_count}")
            if falhas_lista:
                logging.warning(f"[FALHA] Chamados com falha: {falhas_lista}")
            if self.chamados_sem_permissao:
                logging.warning(
                    f"[SEM_PERMISSAO] Total acumulado: {len(self.chamados_sem_permissao)} - "
                    f"IDs: {self.chamados_sem_permissao}"
                )
            logging.info("=============================================")
        finally:
            session.close()

    def _fechar_driver(self):
        """Fecha browser/contexto Playwright em uso, sem parar o processo do driver."""
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass

    def encerrar(self):
        """Encerra o navegador e exibe relatório final de permissões."""
        if self.chamados_sem_permissao:
            logging.info(
                f"[REL] Sem permissao neste ciclo ({len(self.chamados_sem_permissao)}): "
                f"{self.chamados_sem_permissao}"
            )
        self._fechar_driver()
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        logging.info("Robô finalizado e recursos liberados.")


# ==============================================================================
# CÉREBRO DO PSY Assistente WikiSuporte
# ==============================================================================

def _executar_ciclo_chamados():
    """Abre o bot, faz login, coleta chamados, compara e auto-cura."""
    if deve_parar():
        logging.info("Parada solicitada antes do ciclo de chamados.")
        return
    bot = None
    try:
        definir_etapa("Chamados: iniciando navegador")
        bot = OraculoBot()
        definir_etapa("Chamados: autenticando no HelpDesk")
        if bot.login():
            definir_etapa("Chamados: coletando abertos no HelpDesk")
            chamados_helpdesk = bot.coletar_abertos_helpdesk()
            if chamados_helpdesk:
                definir_etapa(f"Chamados: processando {len(chamados_helpdesk)} registros")
                bot.comparar_e_processar(chamados_helpdesk)
            if not deve_parar():
                definir_etapa("Chamados: auto-cura de falhas")
                bot.recuperar_falhas_raspagem()
        else:
            logging.error("Falha no login. Abortando ciclo de chamados.")
    except Exception as e_bot:
        logging.error(f"Erro durante execução do bot: {e_bot}")
    finally:
        if bot:
            definir_etapa("Chamados: encerrando navegador")
            bot.encerrar()


# Este módulo não expõe mais um loop de robô próprio (era um terceiro ponto
# de disparo independente, redundante com motor_extracao.py.
# iniciar_psy_assistente, que é hoje o único modo de operação — ciclo
# completo automático diário à meia-noite). `python -m
# modules.selenium_raspagem` não inicia nada; use `python motor_extracao.py`.
