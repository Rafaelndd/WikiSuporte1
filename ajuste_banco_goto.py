import os
import sys
import pandas as pd
import re
from sqlalchemy import text

# Garante que o Python encontre os módulos do seu projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from modules.database import get_connection
except ImportError:
    print("❌ Erro: Não foi possível importar get_connection de modules.database")
    sys.exit(1)

def corrigir_analistas_goto():
    print("🔍 Iniciando ajuste do banco: Mapeamento de Ramais e Transferências (Correção de Tronco)...")
    engine = get_connection()
    
    # ========================================================
    # 1. TABELA DE CRUZAMENTO E REGRAS DE ISOLAMENTO
    # ========================================================
    mapa_ramais = {
        "0000": {"id": 3, "nome": "admin"},
        "5335": {"id": 4, "nome": "RENATO"},
        "5333": {"id": 5, "nome": "AGNALDO"},
        "5331": {"id": 6, "nome": "BRUNO"},
        "5340": {"id": 7, "nome": "EMIL"},
        "5332": {"id": 8, "nome": "DANIEL"},
        "5344": {"id": 9, "nome": "MARCELO"},
        "5336": {"id": 10, "nome": "ADILTON"},
        "5339": {"id": 11, "nome": "LUIS"},
        "5343": {"id": 12, "nome": "JOAO"},
        "5341": {"id": 13, "nome": "GABRIEL"},
        "5338": {"id": 14, "nome": "RAFAEL NASCIMENTO"},
        "5337": {"id": 15, "nome": "RAFAEL FREITAS"}
    }
    
    # Ramais que ficam em observação
    ramais_em_analise = ["5360", "5364", "5365"]

    try:
        with engine.connect() as conn:
            # 2. Busca todos os registros sem dono
            query_busca = text("""
                SELECT id_interno, participantes 
                FROM atendimentos_goto 
                WHERE id_analista_epsy IS NULL
            """)
            
            df_fantasmas = pd.read_sql(query_busca, conn)
            
            if df_fantasmas.empty:
                print("✅ Nenhum registro sem ID de analista encontrado. Banco de dados limpo!")
                return
            
            print(f"⚠️ Analisando {len(df_fantasmas)} registros com a Regex Blindada...")
            
            atualizacoes = []
            
            for index, row in df_fantasmas.iterrows():
                id_registro = row['id_interno']
                participantes = str(row['participantes']).upper()
                
                novo_id = None
                novo_nome = None
                
                # A MÁGICA DA REGEX CORRIGIDA:
                # (?<!\d) garante que antes dos 4 dígitos NÃO exista outro número.
                # Isso impede que o final de "+554835215365" seja confundido com o ramal "5365".
                match_ramal = re.search(r'(?<!\d)(\d{4}):', participantes)
                
                if match_ramal:
                    ramal = match_ramal.group(1)
                    
                    if ramal in mapa_ramais:
                        # Ramal da equipe
                        novo_id = mapa_ramais[ramal]["id"]
                        novo_nome = mapa_ramais[ramal]["nome"]
                    elif ramal in ramais_em_analise:
                        # Ramais em análise (agora protegidos contra falsos positivos dos números de telefone)
                        novo_nome = f"Ramal {ramal} (Em Análise)"
                    else:
                        novo_nome = f"Ramal {ramal} (Não Cadastrado)"
                
                else:
                    # Se não tem um ramal isolado, e possui formato de telefone externo (+55), 
                    # ou qualquer outra anomalia sem ramal interno: É Transferência!
                    novo_nome = "Transferência entre ramais"
                
                atualizacoes.append({
                    "id_interno_val": id_registro, 
                    "novo_id_val": novo_id,
                    "novo_nome_val": novo_nome
                })
            
            # 3. Injeta as correções
            print("💾 Gravando as correções no PostgreSQL...")
            query_update = text("""
                UPDATE atendimentos_goto 
                SET id_analista_epsy = :novo_id_val,
                    nome_analista_epsy = :novo_nome_val
                WHERE id_interno = :id_interno_val
            """)
            
            for dados in atualizacoes:
                conn.execute(query_update, dados)
            
            conn.commit()
                
            print(f"🎯 Auditoria Concluída! {len(atualizacoes)} chamadas classificadas perfeitamente.")
            
    except Exception as e:
        print(f"❌ Erro crítico durante a execução do script: {e}")

if __name__ == "__main__":
    corrigir_analistas_goto()