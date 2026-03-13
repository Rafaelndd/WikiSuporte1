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
        print("🤖 [PSY - Assistente] A processar HTML da Biblioteca de Manuais (Modo Delta Sync)...")
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr')
        
        inseridos = 0
        atualizados = 0
        ignorados_iguais = 0
        ignorados_video = 0
        erros = 0
        
        with self.engine.connect() as conn:
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) < 5:
                    continue
                    
                trans = conn.begin()
                try:
                    nr_str = re.sub(r'\D', '', tds[0].text.strip())
                    if not nr_str:
                        trans.rollback()
                        continue
                    nr_documento = int(nr_str)
                    
                    link_tag = tds[4].find('a')
                    if not link_tag:
                        trans.rollback()
                        continue
                        
                    classes_link = link_tag.get('class', [])
                    icone_video = link_tag.find('span', class_='glyphicon-facetime-video')
                    
                    if 'link-video' in classes_link or icone_video:
                        ignorados_video += 1
                        trans.rollback()
                        continue
                        
                    url_pdf = link_tag.get('href')
                    if not url_pdf:
                        trans.rollback()
                        continue
                        
                    titulo = tds[1].text.strip()
                    categoria = tds[2].text.strip()
                    subcategoria = tds[3].text.strip()
                    conteudo = f"URL_DOCUMENTO: {url_pdf}"
                    
                    # ==========================================
                    # 🔍 O MOTOR DE DELTA SYNC DOS MANUAIS
                    # ==========================================
                    doc_banco = conn.execute(
                        text("SELECT titulo, conteudo FROM base_conhecimento WHERE origem = 'MANUAL_HELPDESK' AND nr_documento = :nr"), 
                        {"nr": nr_documento}
                    ).fetchone()
                    
                    if doc_banco:
                        db_titulo, db_conteudo = doc_banco
                        # Se o título e o PDF não mudaram, NADA MUDOU!
                        if db_titulo == titulo and db_conteudo == conteudo:
                            ignorados_iguais += 1
                            trans.commit()
                            continue # Pula a gravação
                        else:
                            atualizados += 1
                    else:
                        inseridos += 1

                    # ==========================================
                    # UPSERT
                    # ==========================================
                    query_upsert = text("""
                        INSERT INTO base_conhecimento (nr_documento, origem, titulo, categoria, subcategoria, conteudo, status)
                        VALUES (:nr, 'MANUAL_HELPDESK', :tit, :cat, :subcat, :cont, 'APROVADO')
                        ON CONFLICT (origem, nr_documento) DO UPDATE 
                        SET titulo = EXCLUDED.titulo, categoria = EXCLUDED.categoria,
                            subcategoria = EXCLUDED.subcategoria, conteudo = EXCLUDED.conteudo,
                            atualizado_em = CURRENT_TIMESTAMP
                    """)
                    
                    conn.execute(query_upsert, {"nr": nr_documento, "tit": titulo, "cat": categoria, "subcat": subcategoria, "cont": conteudo})
                    trans.commit()
                    
                except Exception as e:
                    trans.rollback()
                    erros += 1
                    print(f"⚠️ Erro ao processar o manual nº {nr_str}: {e}")
                    
        print(f"✅ [PSY - Assistente] Manuais: {inseridos} Novos | {atualizados} Atualizados | {ignorados_iguais} Intocados (Ignorados) | {ignorados_video} Vídeos pulados.")


    def processar_html_releases(self, html_content):
        """
        Extrai as Notas de Atualização e persiste no novo modelo (releases, chamados, ciclos_homologacao).
        """
        print("🤖 [PSY - Assistente WikiSuporte] A caçar Correções nos Releases...")
        try:
            from services.db_homologacao import processar_release_completo
        except ImportError:
            print("⚠️ db_homologacao não disponível. Pulando processamento de releases.")
            return

        from services.db_homologacao import (
            get_helpdesk_release_head,
            set_helpdesk_release_head,
            _extrair_versao_do_titulo,
        )

        soup = BeautifulSoup(html_content, 'html.parser')
        textareas = soup.find_all('textarea')
        total_vinculados = 0
        total_ciclos = 0
        if not textareas:
            print("⚠️ Nenhum textarea de release no HTML.")
            return

        ta = textareas[0]
        texto_release = (ta.text or "").strip()
        if not texto_release:
            return
        first_line = next(
            (ln.strip() for ln in texto_release.splitlines() if ln.strip()),
            "Release",
        )
        titulo_link = first_line[:2000]
        ver_norm = _extrair_versao_do_titulo(first_line) or _extrair_versao_do_titulo(texto_release[:800])
        db_titulo, db_ver = get_helpdesk_release_head()
        if titulo_link and db_titulo == titulo_link:
            print(f"⏭️ [Releases HTML] Igual ao último sync ({db_ver}). Pulando.")
            return
        versao = first_line[:50].strip()
        try:
            qtd_v, qtd_c = processar_release_completo(
                versao=versao,
                texto_completo=texto_release,
                autor="Processamento Automático (OraculoLogistica)",
                nome_arquivo=titulo_link[:255],
            )
            total_vinculados += qtd_v
            total_ciclos += qtd_c
            set_helpdesk_release_head(titulo_link=titulo_link, versao_norm=ver_norm or db_ver)
        except Exception as ex:
            print(f"⚠️ Erro ao processar release '{versao}': {ex}")

        print(f"✅ [PSY - Assistente] Releases (1º bloco): {total_vinculados} vinculados, {total_ciclos} ciclos.")


    def processar_html_tickets(self, html_content):
        """
        Extrai os tickets da EPSY fazendo Sincronização Delta (Apenas novos ou alterados).
        Retorna um dicionário com as estatísticas para o Motor decidir se continua paginando.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr')
        
        inseridos = 0
        atualizados = 0
        ignorados_iguais = 0
        erros = 0
        
        with self.engine.connect() as conn:
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) < 7:
                    continue
                
                id_bruto = tds[0].text.strip()
                id_limpo = re.sub(r'\D', '', id_bruto)
                if not id_limpo:
                    continue 
                
                trans = conn.begin() 
                try:
                    nr_ticket = int(id_limpo)
                    cliente_nome = tds[1].text.strip()
                    assunto = tds[2].text.strip()
                    nome_analista_epsy = tds[4].text.strip()
                    status_atual = tds[5].text.strip()
                    
                    chamado_vinc_str = re.sub(r'\D', '', tds[6].text.strip())
                    chamado_vinculado = int(chamado_vinc_str) if chamado_vinc_str else None
                    if chamado_vinculado == 0: chamado_vinculado = None
                        
                    data_ab_str = tds[3].text.strip()
                    data_abertura = None
                    if data_ab_str:
                        try: data_abertura = datetime.strptime(data_ab_str, "%d/%m/%Y %H:%M:%S")
                        except ValueError:
                            try: data_abertura = datetime.strptime(data_ab_str, "%d/%m/%Y %H:%M")
                            except: pass

                    primeiro_nome = nome_analista_epsy.split()[0] if nome_analista_epsy else ''
                    id_analista_epsy = None
                    if primeiro_nome:
                        id_analista_epsy = conn.execute(
                            text("SELECT id FROM usuarios WHERE nome ILIKE :b LIMIT 1"), 
                            {"b": f"%{primeiro_nome}%"}
                        ).scalar()

                    # ==========================================
                    # O COFRE SECRETO
                    # ==========================================
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
                            try: data_ultima_interacao = datetime.strptime(m_interacao.group(1).strip(), "%d/%m/%Y %H:%M:%S")
                            except: pass
                                
                        m_msg = re.search(r'Última Mensagem:</font>.*?<font[^>]*>(.*?)</font>', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_msg: ultima_mensagem = re.sub(r'<br\s*/?>', ' | ', m_msg.group(1)).strip()
                            
                        m_ava = re.search(r'Avaliação:</font>.*?<img[^>]*src="[^"]*?(\d)star\.png"', html_interno, re.IGNORECASE | re.DOTALL)
                        if m_ava: avaliacao = m_ava.group(1).strip()

                    # ==========================================
                    # 🔍 O MOTOR DE DELTA SYNC (A sua nova regra!)
                    # ==========================================
                    ticket_banco = conn.execute(
                        text("SELECT status_atual, data_ultima_interacao FROM tickets_epsy WHERE nr_ticket = :nr"), 
                        {"nr": nr_ticket}
                    ).fetchone()
                    
                    if ticket_banco:
                        db_status, db_interacao = ticket_banco
                        # Se o status é o mesmo E a data da última mensagem é a mesma, NADA MUDOU!
                        if db_status == status_atual and db_interacao == data_ultima_interacao:
                            ignorados_iguais += 1
                            trans.commit()
                            continue # Pula a gravação e vai para o próximo ticket!
                        else:
                            atualizados += 1
                    else:
                        inseridos += 1

                    # ==========================================
                    # UPSERT SEGURO (Só chega aqui se for Novo ou Alterado)
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
                    
                    trans.commit() 
                    
                except Exception as e:
                    trans.rollback() 
                    erros += 1
                    print(f"⚠️ Erro isolado no ticket ID {id_bruto}: {e}")
                    
        print(f"✅ [PSY - Assistente] Página processada: {inseridos} novos | {atualizados} atualizados | {ignorados_iguais} intocados (ignorados).")
        
        # O Oráculo devolve os números para o Motor tomar uma decisão
        return {"inseridos": inseridos, "atualizados": atualizados, "ignorados_iguais": ignorados_iguais}


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

    def obter_ids_wikis_sincronizadas(self):
        """
        Retorna uma lista com os IDs das Wikis que já estão no nosso Banco de Dados RAG.
        Isso evita que o robô mergulhe em páginas antigas desnecessariamente.
        """
        with self.engine.connect() as conn:
            resultado = conn.execute(text("SELECT nr_documento FROM base_conhecimento WHERE origem = 'WIKI_HELPDESK'"))
            # Retorna um "Set" (conjunto) para buscas ultra-rápidas no Python
            return {linha[0] for linha in resultado}


    def processar_e_salvar_wiki_interna(self, html_content, id_wiki):
        """
        Extrai o Título, o Texto rico e os Anexos de dentro da página individual da Wiki.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Extrai o Título
        input_titulo = soup.find('input', id='w_titulo')
        titulo = input_titulo['value'].strip() if input_titulo and input_titulo.has_attr('value') else f"Wiki Sem Título {id_wiki}"
        
        # 2. Extrai a Descrição (O Corpo da Wiki)
        textarea_desc = soup.find('textarea', id='w_desc')
        conteudo = textarea_desc.text.strip() if textarea_desc else ""
        
        # 3. Mapeia os Anexos (Imagens e Arquivos soltos)
        anexos = []
        for a_tag in soup.find_all('a', href=True):
            if '_uploads/wiki/' in a_tag['href']:
                anexos.append(a_tag['href'])
                
        # Junta os anexos ao final do texto para a IA do Gemini poder referenciá-los
        if anexos:
            conteudo += "\n\n[LINKS DE ANEXOS/IMAGENS]:\n" + "\n".join(anexos)
            
        # 4. Grava no nosso "Cérebro IA"
        with self.engine.begin() as conn:
            query_upsert = text("""
                INSERT INTO base_conhecimento (
                    nr_documento, origem, titulo, categoria, subcategoria, conteudo, status
                ) VALUES (
                    :nr, 'WIKI_HELPDESK', :tit, 'WIKI', 'DICAS DE SUPORTE', :cont, 'APROVADO'
                )
                ON CONFLICT (origem, nr_documento) DO UPDATE 
                SET titulo = EXCLUDED.titulo,
                    conteudo = EXCLUDED.conteudo,
                    atualizado_em = CURRENT_TIMESTAMP
            """)
            conn.execute(query_upsert, {
                "nr": id_wiki, "tit": titulo, "cont": conteudo
            })