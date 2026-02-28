import re 
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from sqlalchemy import text
from config import Config


# Importa a conexão com o banco que já temos no sistema
from modules.database import get_connection

class OraculoLogistica:
    def __init__(self):
        self.engine = get_connection()

    def processar_html_plantoes(self, html_content):
        """
        Extrai a escala de plantões e cruza com os Analistas EPSY no banco de dados.
        Baseado no HTML de <tr class="small">
        """
        print("🤖 [PSY - Assistente WikiSuporte] A processar HTML de Plantões...")
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr', class_='small')
        
        sucesso = 0
        with self.engine.begin() as conn:
            # Prevenção de duplicados: Apaga os plantões do mês atual antes de inserir a nova escala raspada
            conn.execute(text("DELETE FROM plantoes_epsy WHERE EXTRACT(MONTH FROM data_hora_entrada) = EXTRACT(MONTH FROM CURRENT_DATE)"))
            
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) >= 5:
                    nome_analista_epsy = tds[1].text.strip()
                    entrada_str = tds[2].text.strip() # Formato: 02/02/2026 / 18:00:00
                    saida_str = tds[3].text.strip()
                    
                    try:
                        # Limpa a string da data removendo a barra isolada
                        entrada_limpa = entrada_str.replace(' / ', ' ')
                        saida_limpa = saida_str.replace(' / ', ' ')
                        
                        dt_entrada = datetime.strptime(entrada_limpa, "%d/%m/%Y %H:%M:%S")
                        dt_saida = datetime.strptime(saida_limpa, "%d/%m/%Y %H:%M:%S")
                        
                        # Tenta encontrar o ID do analista logado na tabela usuarios usando o primeiro nome
                        primeiro_nome = nome_analista_epsy.split()[0]
                        query_user = text("SELECT id FROM usuarios WHERE nome ILIKE :busca LIMIT 1")
                        user_id = conn.execute(query_user, {"busca": f"%{primeiro_nome}%"}).scalar()
                        
                        # Insere o plantão no banco
                        query_insert = text("""
                            INSERT INTO plantoes_epsy (nome_analista_epsy, id_analista_epsy, data_hora_entrada, data_hora_saida) 
                            VALUES (:nome, :uid, :entrada, :saida)
                        """)
                        conn.execute(query_insert, {
                            "nome": nome_analista_epsy, 
                            "uid": user_id, 
                            "entrada": dt_entrada, 
                            "saida": dt_saida
                        })
                        sucesso += 1
                    except Exception as e:
                        print(f"⚠️ Erro ao processar linha de plantão ({nome_analista_epsy}): {e}")
                        
        print(f"✅ [PSY - Assistente WikiSuporte] Escala atualizada: {sucesso} plantões inseridos com sucesso!")

    def processar_html_manuais(self, html_content):
        """
        Raspa a tabela de manuais. Ignora ficheiros que sejam vídeos (YouTube).
        """
        print("🤖 [PSY - Assistente WikiSuporte] A processar HTML de Manuais...")
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr', class_='small')
        
        sucesso = 0
        with self.engine.begin() as conn:
            # Limpa a base antiga para atualizar com o HTML mais recente
            conn.execute(text("TRUNCATE TABLE manuais_tecnuv RESTART IDENTITY"))
            
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) >= 5:
                    titulo = tds[1].text.strip()
                    categoria = tds[2].text.strip()
                    subcategoria = tds[3].text.strip()
                    
                    link_tag = tds[4].find('a')
                    if link_tag:
                        # Regra de Negócio: Ignorar Manuais em formato de Vídeo
                        classes_link = link_tag.get('class', [])
                        if 'link-video' in classes_link:
                            continue
                            
                        href = link_tag.get('href', '')
                        if href and href != '#':
                            query_insert = text("""
                                INSERT INTO manuais_tecnuv (titulo, categoria, subcategoria, link_acesso)
                                VALUES (:t, :c, :s, :l)
                            """)
                            conn.execute(query_insert, {"t": titulo, "c": categoria, "s": subcategoria, "l": href})
                            sucesso += 1
                            
        print(f"✅ [PSY - Assistente WikiSuporte] Biblioteca de Manuais atualizada: {sucesso} documentos em PDF extraídos!")

    def processar_html_releases(self, html_content):
        """
        Extrai as Notas de Atualização e utiliza Expressões Regulares para encontrar 
        os números de chamados corrigidos, cruzando-os com a base ativa.
        """
        print("🤖 [PSY - Assistente WikiSuporte] A caçar Correções nos Releases...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Encontra o bloco de texto de atualização
        textareas = soup.find_all('textarea')
        
        sucesso = 0
        with self.engine.begin() as conn:
            # Cria um Release "Fantasma" Genérico para atrelar as correções de hoje, caso não haja a data extraída
            query_release = text("INSERT INTO releases_tecnuv (versao, notas_atualizacao) VALUES ('Último Release', 'Processamento Automático') RETURNING id_release")
            id_release_atual = conn.execute(query_release).scalar()
            
            for ta in textareas:
                texto_release = ta.text
                
                # A MÁGICA: Expressão Regular para encontrar padrões como (13555) ou (12495)
                chamados_corrigidos = re.findall(r'\((\d{4,5})\)', texto_release)
                
                for numero_chamado in chamados_corrigidos:
                    try:
                        # Tenta inserir na tabela de correções
                        query_insert = text("""
                            INSERT INTO release_chamados_correcao (id_release, nr_chamado, validado_epsy) 
                            VALUES (:id_rel, :nr, FALSE)
                            ON CONFLICT (id_release, nr_chamado) DO NOTHING
                        """)
                        conn.execute(query_insert, {"id_rel": id_release_atual, "nr": int(numero_chamado)})
                        sucesso += 1
                    except: pass
                    
        print(f"✅ [PSY - Assistente WikiSuporte] Varredura de Código finalizada: {sucesso} possíveis chamados corrigidos pela Tecnuv identificados.")


    def processar_html_tickets(self, html_content):
        """
        Extrai os tickets da EPSY fazendo Deep Scraping no HTML fornecido com Isolamento de Transações.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr')
        
        sucesso = 0
        erros = 0
        
        # MUDANÇA ARQUITETURAL: Usamos connect() em vez de begin() 
        # para nós mesmos controlarmos as transações linha a linha!
        with self.engine.connect() as conn:
            for linha in linhas:
                tds = linha.find_all('td')
                
                if len(tds) < 7:
                    continue
                
                id_bruto = tds[0].text.strip()
                id_limpo = re.sub(r'\D', '', id_bruto)
                if not id_limpo:
                    continue 
                
                # ==========================================
                # 🛡️ INÍCIO DA TRANSAÇÃO ISOLADA DO TICKET
                # ==========================================
                trans = conn.begin() 
                try:
                    nr_ticket = int(id_limpo)
                    cliente_nome = tds[1].text.strip()
                    assunto = tds[2].text.strip()
                    nome_analista_epsy = tds[4].text.strip()
                    status_atual = tds[5].text.strip()
                    
                    chamado_vinc_str = re.sub(r'\D', '', tds[6].text.strip())
                    chamado_vinculado = int(chamado_vinc_str) if chamado_vinc_str else None
                    
                    # A CORREÇÃO DA CASCATA: Se a Tecnuv mandar 0, nós anulamos.
                    if chamado_vinculado == 0:
                        chamado_vinculado = None
                        
                    data_ab_str = tds[3].text.strip()
                    data_abertura = None
                    if data_ab_str:
                        try:
                            data_abertura = datetime.strptime(data_ab_str, "%d/%m/%Y %H:%M:%S")
                        except ValueError:
                            try:
                                data_abertura = datetime.strptime(data_ab_str, "%d/%m/%Y %H:%M")
                            except: pass

                    primeiro_nome = nome_analista_epsy.split()[0] if nome_analista_epsy else ''
                    id_analista_epsy = None
                    if primeiro_nome:
                        id_analista_epsy = conn.execute(
                            text("SELECT id FROM usuarios WHERE nome ILIKE :b LIMIT 1"), 
                            {"b": f"%{primeiro_nome}%"}
                        ).scalar()

                    # O COFRE SECRETO
                    tempo_aberto_str = None
                    avaliacao = None
                    data_ultima_interacao = None
                    ultima_mensagem = None
                    
                    icone_info = linha.find('a', class_='dcontexto')
                    if icone_info:
                        html_interno = str(icone_info)
                        
                        m_tempo = re.search(r'Ticket ficou aberto por:</font>.*?<font[^>]*>(.*?)</font>', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_tempo: tempo_aberto_str = m_tempo.group(1).replace('<br>', '').strip()
                            
                        m_interacao = re.search(r'Última Alteração:</font>.*?<font[^>]*>.*?(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_interacao:
                            try:
                                data_ultima_interacao = datetime.strptime(m_interacao.group(1).strip(), "%d/%m/%Y %H:%M:%S")
                            except: pass
                                
                        m_msg = re.search(r'Última Mensagem:</font>.*?<font[^>]*>(.*?)</font>', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_msg:
                            ultima_mensagem = re.sub(r'<br\s*/?>', ' | ', m_msg.group(1)).strip()
                            
                        m_ava = re.search(r'Avaliação:</font>.*?<img[^>]*src="[^"]*?(\d)star\.png"', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_ava: avaliacao = m_ava.group(1).strip()

                    # ==========================================
                    # UPSERT SEGURO
                    # ==========================================
                    query_insert = text("""
                        INSERT INTO tickets_epsy (
                            nr_ticket, cliente_nome, assunto, data_abertura, 
                            nome_analista_epsy, id_analista_epsy, status_atual, chamado_vinculado,
                            tempo_aberto_str, avaliacao, data_ultima_interacao, ultima_mensagem
                        )
                        VALUES (
                            :nr_ticket, :cliente_nome, :assunto, :data_abertura, 
                            :nome_analista_epsy, :id_analista_epsy, :status_atual, :chamado_vinculado,
                            :tempo_aberto_str, :avaliacao, :data_ultima_interacao, :ultima_mensagem
                        )
                        ON CONFLICT (nr_ticket) DO UPDATE 
                        SET 
                            status_atual = EXCLUDED.status_atual,
                            chamado_vinculado = EXCLUDED.chamado_vinculado,
                            nome_analista_epsy = EXCLUDED.nome_analista_epsy,
                            id_analista_epsy = EXCLUDED.id_analista_epsy,
                            tempo_aberto_str = EXCLUDED.tempo_aberto_str,
                            avaliacao = EXCLUDED.avaliacao,
                            data_ultima_interacao = EXCLUDED.data_ultima_interacao,
                            ultima_mensagem = EXCLUDED.ultima_mensagem,
                            atualizado_em = CURRENT_TIMESTAMP
                    """)
                    
                    conn.execute(query_insert, {
                        "nr_ticket": nr_ticket, "cliente_nome": cliente_nome, "assunto": assunto, 
                        "data_abertura": data_abertura, "nome_analista_epsy": nome_analista_epsy, 
                        "id_analista_epsy": id_analista_epsy, "status_atual": status_atual, 
                        "chamado_vinculado": chamado_vinculado, "tempo_aberto_str": tempo_aberto_str, 
                        "avaliacao": avaliacao, "data_ultima_interacao": data_ultima_interacao, 
                        "ultima_mensagem": ultima_mensagem
                    })
                    
                    # CONFIRMA A TRANSAÇÃO (O Ticket deu certo!)
                    trans.commit() 
                    sucesso += 1
                    
                except Exception as e:
                    # CANCELA A TRANSAÇÃO (O Ticket deu errado, mas salva o resto da página!)
                    trans.rollback() 
                    erros += 1
                    print(f"⚠️ Erro isolado no ticket ID {id_bruto}: {e}")
                    
        print(f"✅ [PSY - Assistente WikiSuporte] Página processada. +{sucesso} tickets salvos | {erros} ignorados.")


    def sincronizar_vinculos_goto(self):
        """
        Vare a tabela do GoTo e vincula os telefones aos clientes usando a chave LGPD.
        Deve ser chamada automaticamente após cadastrar um novo cliente ou subir um CSV.
        """
        print("🔄 [Automático] Iniciando sincronização de vínculos GoTo (LGPD)...")
        
        # O text() do SQLAlchemy prepara a query para receber variáveis seguras
        sql_update = text("""
            UPDATE atendimentos_goto ag
            SET id_cliente = ct.id_cliente
            FROM clientes_telefones ct
            WHERE 
                ag.participantes LIKE '%' || pgp_sym_decrypt(ct.numero_criptografado::bytea, :chave_lgpd) || '%'
                AND ag.id_cliente IS NULL;
        """)
        
        try:
            # Executa a query injetando a chave secreta do config.py
            resultado = self.session.execute(sql_update, {"chave_lgpd": Config.LGPD_SECRET_KEY})
            self.session.commit() # Salva a transação!
            
            # resultado.rowcount nos diz exatamente quantas linhas foram "amarradas"
            linhas_afetadas = resultado.rowcount
            print(f"✅ Vínculos sincronizados! {linhas_afetadas} ligações órfãs foram conectadas a clientes.")
            
            return linhas_afetadas
            
        except Exception as e:
            self.session.rollback() # Evita o efeito dominó se der erro
            print(f"❌ Erro crítico ao sincronizar clientes GoTo: {e}")
            return 0


    def sincronizar_vinculos_multi360(self):
        """
        Varre a tabela do Multi360 e vincula os telefones aos clientes usando a chave LGPD.
        """
        print("🔄 [Automático] Iniciando sincronização de vínculos Multi360 (LGPD)...")
        
        sql_update = text("""
            UPDATE atendimentos_multi360 am
            SET id_cliente = ct.id_cliente
            FROM clientes_telefones ct
            WHERE 
                -- Como o número vem limpo, o LIKE funciona perfeitamente com o dado descriptografado
                am.numero LIKE '%' || pgp_sym_decrypt(ct.numero_criptografado::bytea, :chave_lgpd) || '%'
                AND am.id_cliente IS NULL;
        """)
        
        try:
            resultado = self.session.execute(sql_update, {"chave_lgpd": Config.LGPD_SECRET_KEY})
            self.session.commit()
            
            linhas_afetadas = resultado.rowcount
            print(f"✅ Vínculos Multi360 sincronizados! {linhas_afetadas} chats órfãos foram conectados.")
            return linhas_afetadas
            
        except Exception as e:
            self.session.rollback()
            print(f"❌ Erro crítico ao sincronizar clientes Multi360: {e}")
            return 0