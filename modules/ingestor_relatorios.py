import pandas as pd
import re
from sqlalchemy import text
from modules.database import get_connection

def limpar_telefone(numero):
    """Remove tudo que não for número de um telefone."""
    if pd.isna(numero):
        return ""
    return re.sub(r'\D', '', str(numero))

def processar_e_salvar_csv(arquivo_csv):
    engine = get_connection()
    nome_arquivo = arquivo_csv.name
    
    try:
        df = pd.read_csv(arquivo_csv, sep=None, engine='python')
    except Exception as e:
        return False, f"Falha ao ler o arquivo CSV: {e}"

    # ---------------------------------------------------------
    # ROTA A: É UM ARQUIVO DO GOTO (TELEFONIA)
    # ---------------------------------------------------------
    if 'Conversation space id' in df.columns:
        # 1. Validação do Nome do Arquivo via Regex
        padrao_nome = r"call-report-grouped-by-user_(\d{8})_(\d{8})\.csv"
        match = re.match(padrao_nome, nome_arquivo)
        
        if not match:
            return False, "❌ Arquivo Rejeitado! O nome do arquivo GoTo deve seguir o padrão: call-report-grouped-by-user_AAAAMMDD_AAAAMMDD.csv"
            
        # Extrai as datas do nome do arquivo (Apenas para log/validação)
        data_ini_str, data_fim_str = match.groups()
        
        try:
            df_limpo = pd.DataFrame()
            df_limpo['id_conversa'] = df['Conversation space id']
            datas_sp = pd.to_datetime(df['Data [America/Sao_Paulo]'], errors='coerce')
            df_limpo['data_chamada'] = datas_sp.dt.tz_localize(None) 
            df_limpo['duracao_ms'] = df['Duração [milissegundos]']
            df_limpo['direcao'] = df['Direção']
            df_limpo['resultado'] = df['Resultado da chamada']
            
            # 2. Padronização de Telefones (Apenas Números)
            df_limpo['telefone_origem'] = df['De'].apply(limpar_telefone)
            
            df_limpo['participantes'] = df['Participantes']
            df_limpo['gravado'] = df['Gravações'].astype(str)

            # Dropa linhas sem data de chamada (crítico para a chave única)
            df_limpo = df_limpo.dropna(subset=['data_chamada'])

            # 3. Upsert Inteligente: Deleta os registros nesse período exato antes de inserir
            # Isso impede duplicação mesmo para os registros com ID vazio
            data_min = df_limpo['data_chamada'].min()
            data_max = df_limpo['data_chamada'].max()
            
            with engine.begin() as conn:
                query_delete = text("DELETE FROM atendimentos_goto WHERE data_chamada >= :dmin AND data_chamada <= :dmax")
                conn.execute(query_delete, {"dmin": data_min, "dmax": data_max})
                
                df_limpo.to_sql('atendimentos_goto', conn, if_exists='append', index=False)
                
            return True, f"✅ Sucesso! {len(df_limpo)} ligações do GoTo importadas. Período: {data_min.strftime('%d/%m/%Y')} a {data_max.strftime('%d/%m/%Y')}"

        except Exception as e:
            return False, f"Erro ao processar arquivo GoTo: {e}"

    # ---------------------------------------------------------
    # ROTA B: É UM ARQUIVO DO MULTI360 (WHATSAPP)
    # ---------------------------------------------------------
    elif 'PROTOCOLO' in df.columns:
        try:
            df_limpo = pd.DataFrame()
            df_limpo['protocolo'] = df['PROTOCOLO']
            df_limpo['origem'] = df['ORIGEM']
            df_limpo['status'] = df['STATUS']
            df_limpo['atendente'] = df['ATENDENTE']
            df_limpo['departamento'] = df['DEPARTAMENTO']
            df_limpo['nome_contato'] = df['NOME']
            df_limpo['numero_telefone'] = df['NUMERO'].apply(limpar_telefone)
            df_limpo['avaliacao'] = df['AVALIACAO']
            
            df_limpo['data_inicio'] = pd.to_datetime(df['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
            df_limpo['data_finalizacao'] = pd.to_datetime(df['DATAFINALIZACAO'], format='%d/%m/%Y %H:%M', errors='coerce')
            
            df_limpo = df_limpo.dropna(subset=['protocolo'])
            
            # Descobre o período automático e informa o usuário
            data_min = df_limpo['data_inicio'].min()
            data_max = df_limpo['data_inicio'].max()

            lista_protocolos = df_limpo['protocolo'].tolist()
            with engine.begin() as conn:
                if lista_protocolos:
                    query_delete = text("DELETE FROM atendimentos_multi360 WHERE protocolo = ANY(:ids)")
                    conn.execute(query_delete, {"ids": lista_protocolos})
                
                df_limpo.to_sql('atendimentos_multi360', conn, if_exists='append', index=False)
                
            mensagem = f"✅ Sucesso! {len(df_limpo)} atendimentos Multi360 importados.\nPeríodo identificado: {data_min.strftime('%d/%m/%Y')} a {data_max.strftime('%d/%m/%Y')}"
            return True, mensagem
            
        except Exception as e:
            return False, f"Erro ao processar arquivo Multi360: {e}"

    else:
        return False, "❌ Formato desconhecido. Envie um CSV do Multi360 ou GoTo."