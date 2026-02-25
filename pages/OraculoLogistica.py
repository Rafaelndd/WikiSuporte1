import re
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
from sqlalchemy import text

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
        print("🤖 [Oráculo] A processar HTML de Plantões...")
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.find_all('tr', class_='small')
        
        sucesso = 0
        with self.engine.begin() as conn:
            # Prevenção de duplicados: Apaga os plantões do mês atual antes de inserir a nova escala raspada
            conn.execute(text("DELETE FROM plantoes_epsy WHERE EXTRACT(MONTH FROM data_hora_entrada) = EXTRACT(MONTH FROM CURRENT_DATE)"))
            
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) >= 5:
                    nome_plantonista = tds[1].text.strip()
                    entrada_str = tds[2].text.strip() # Formato: 02/02/2026 / 18:00:00
                    saida_str = tds[3].text.strip()
                    
                    try:
                        # Limpa a string da data removendo a barra isolada
                        entrada_limpa = entrada_str.replace(' / ', ' ')
                        saida_limpa = saida_str.replace(' / ', ' ')
                        
                        dt_entrada = datetime.strptime(entrada_limpa, "%d/%m/%Y %H:%M:%S")
                        dt_saida = datetime.strptime(saida_limpa, "%d/%m/%Y %H:%M:%S")
                        
                        # Tenta encontrar o ID do analista logado na tabela usuarios_dashboard usando o primeiro nome
                        primeiro_nome = nome_plantonista.split()[0]
                        query_user = text("SELECT id FROM usuarios_dashboard WHERE nome ILIKE :busca LIMIT 1")
                        user_id = conn.execute(query_user, {"busca": f"%{primeiro_nome}%"}).scalar()
                        
                        # Insere o plantão no banco
                        query_insert = text("""
                            INSERT INTO plantoes_epsy (nome_plantonista, id_usuario_epsy, data_hora_entrada, data_hora_saida) 
                            VALUES (:nome, :uid, :entrada, :saida)
                        """)
                        conn.execute(query_insert, {
                            "nome": nome_plantonista, 
                            "uid": user_id, # Pode ser None se for alguém da Tecnuv, mas a tabela aceita
                            "entrada": dt_entrada, 
                            "saida": dt_saida
                        })
                        sucesso += 1
                    except Exception as e:
                        print(f"⚠️ Erro ao processar linha de plantão ({nome_plantonista}): {e}")
                        
        print(f"✅ [Oráculo] Escala atualizada: {sucesso} plantões inseridos com sucesso!")

    def processar_html_manuais(self, html_content):
        """
        Raspa a tabela de manuais. Ignora ficheiros que sejam vídeos (YouTube).
        """
        print("🤖 [Oráculo] A processar HTML de Manuais...")
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
                            
        print(f"✅ [Oráculo] Biblioteca de Manuais atualizada: {sucesso} documentos em PDF extraídos!")

    def processar_html_releases(self, html_content):
        """
        Extrai as Notas de Atualização e utiliza Expressões Regulares para encontrar 
        os números de chamados corrigidos, cruzando-os com a base ativa.
        """
        print("🤖 [Oráculo] A caçar Correções nos Releases...")
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
                    
        print(f"✅ [Oráculo] Varredura de Código finalizada: {sucesso} possíveis chamados corrigidos pela Tecnuv identificados.")

    def processar_html_tickets(self, html_content):
        """
        Extrai os tickets que os clientes abrem contra a EPSY e amarra ao usuário responsável.
        """
        print("🤖 [Oráculo] A processar HTML da Fila de Tickets...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # A tabela de tickets costuma ter um <tbody> sob o thead_gray
        linhas = soup.find_all('tr', class_='small') # Ajuste a class baseando-se no HTML real
        
        sucesso = 0
        with self.engine.begin() as conn:
            for linha in linhas:
                tds = linha.find_all('td')
                if len(tds) >= 7:
                    try:
                        id_ticket = int(tds[0].text.strip())
                        cliente = tds[1].text.strip()
                        assunto = tds[2].text.strip()
                        data_ab_str = tds[3].text.strip()
                        operador = tds[4].text.strip()
                        status = tds[5].text.strip()
                        
                        # Extrai o Chamado Vinculado (Se houver)
                        chamado_vinc_str = tds[6].text.strip()
                        chamado_vinc = int(chamado_vinc_str) if chamado_vinc_str.isdigit() else None
                        
                        # Busca o ID da EPSY
                        primeiro_nome = operador.split()[0]
                        user_id = conn.execute(text("SELECT id FROM usuarios_dashboard WHERE nome ILIKE :b LIMIT 1"), {"b": f"%{primeiro_nome}%"}).scalar()
                        
                        query_insert = text("""
                            INSERT INTO tickets_epsy (id_ticket, cliente_nome, assunto, status, operador_nome, id_usuario_epsy, chamado_vinculado)
                            VALUES (:idt, :cli, :ass, :st, :op, :uid, :cv)
                            ON CONFLICT (id_ticket) DO UPDATE 
                            SET status = :st, chamado_vinculado = :cv, operador_nome = :op
                        """)
                        conn.execute(query_insert, {
                            "idt": id_ticket, "cli": cliente, "ass": assunto, 
                            "st": status, "op": operador, "uid": user_id, "cv": chamado_vinc
                        })
                        sucesso += 1
                    except Exception as e:
                        pass # Ignora cabeçalhos ou linhas corrompidas
                        
        print(f"✅ [Oráculo] Tickets atualizados: {sucesso} tickets sincronizados com a base EPSY.")

# --- FUNÇÃO PARA TESTES LOCAIS (Simulação) ---
if __name__ == "__main__":
    print("Iniciando testes do Oráculo Logístico...")
    robo = OraculoLogistica()
    
    # Exemplo de como você vai chamar isto futuramente quando tiver os HTMLs salvos localmente ou via Selenium:
    # with open("plantoes.html", "r", encoding="utf-8") as f:
    #     robo.processar_html_plantoes(f.read())
    
    print("Módulo OraculoLogistica pronto para ser importado pelo motor Selenium!")