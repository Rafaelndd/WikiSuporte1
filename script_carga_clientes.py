import pandas as pd
from sqlalchemy import text
from modules.database import get_connection
import openpyxl

def executar_carga_clientes(caminho_excel):
    print("🚀 A iniciar a carga de clientes via ficheiro Excel...")
    
    # 1. Lendo o Excel (Muito mais estável que CSV)
    try:
        df = pd.read_excel(caminho_excel, engine='openpyxl')
        
        # Limpa espaços em branco ocultos nos nomes das colunas
        df.columns = df.columns.str.strip() 
        
        print(f"📦 Foram encontradas {len(df)} linhas no ficheiro.")
        print(f"📋 Colunas lidas: {list(df.columns)}")
    except Exception as e:
        print(f"❌ Erro ao ler o Excel: {e}")
        print("💡 Dica: Verifique se instalou o leitor rodando 'pip install openpyxl'")
        return

    # 2. Limpeza de dados (Tratando valores vazios e NaN do Pandas)
    df = df.fillna('')
    
    # 3. Conectando à Base de Dados
    engine = get_connection()
    
    inseridos = 0
    ignorados = 0
    
    with engine.begin() as conn: # Transação segura
        for index, row in df.iterrows():
            # Extraindo os dados da linha
            id_helpdesk = str(row.get('ID_CLIENTE_HELPDESK', '')).strip()
            nome_fantasia = str(row.get('Nome Fantasia', '')).strip()
            razao_social = str(row.get('Razão Social', '')).strip()
            cnpj = str(row.get('CNPJ', '')).strip()
            tipo_rede = str(row.get('Rede', '')).strip()
            versao = str(row.get('Versão', '')).strip()
            situacao = str(row.get('Situação', '')).strip()
            fone = str(row.get('Fone', '')).strip()
            
            # O Excel às vezes adiciona ".0" a números inteiros, vamos limpar isso
            if id_helpdesk.endswith('.0'):
                id_helpdesk = id_helpdesk[:-2]
            
            # Salta se não tiver CNPJ
            if not cnpj or cnpj == 'nan':
                ignorados += 1
                continue
                
            id_helpdesk_val = int(id_helpdesk) if id_helpdesk and id_helpdesk != 'nan' else None
            
            # --- INSERINDO NA TABELA MÃE (clientes_crm) ---
            query_crm = text("""
                INSERT INTO clientes_crm 
                (id_cliente_helpdesk, nome_cliente, razao_social, cnpj, tipo, versao_atual, situacao_cadastro, ativo, data_cadastro)
                VALUES 
                (:id_hd, :nome, :razao, :cnpj, :tipo, :versao, :situacao, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (cnpj) DO UPDATE SET 
                    id_cliente_helpdesk = EXCLUDED.id_cliente_helpdesk,
                    nome_cliente = EXCLUDED.nome_cliente,
                    versao_atual = EXCLUDED.versao_atual
                RETURNING id_cliente;
            """)
            
            try:
                result = conn.execute(query_crm, {
                    "id_hd": id_helpdesk_val,
                    "nome": nome_fantasia,
                    "razao": razao_social,
                    "cnpj": cnpj,
                    "tipo": tipo_rede,
                    "versao": versao,
                    "situacao": situacao
                })
                
                id_cliente_gerado = result.scalar()
                
                # --- INSERINDO NA TABELA SATÉLITE (clientes_telefones) ---
                if id_cliente_gerado and fone and fone != 'nan':
                    query_tel = text("""
                        INSERT INTO clientes_telefones (id_cliente, origem_dado, numero, data_cadastro)
                        VALUES (:id_cli, 'CARGA_INICIAL', :num, CURRENT_TIMESTAMP)
                    """)
                    conn.execute(query_tel, {"id_cli": id_cliente_gerado, "num": fone})
                    
                inseridos += 1
                
            except Exception as e:
                print(f"⚠️ Erro ao inserir o cliente {cnpj}: {e}")
                ignorados += 1
                
    print("-" * 40)
    print(f"✅ Carga Finalizada!")
    print(f"🟢 Clientes inseridos/atualizados: {inseridos}")
    print(f"🔴 Linhas ignoradas/com erro: {ignorados}")

if __name__ == "__main__":
    # Coloque o caminho exato do seu ficheiro .xlsx aqui
    caminho_do_arquivo = "cadastro_clientes2.xlsx"
    executar_carga_clientes(caminho_do_arquivo)