import pandas as pd
import re
from datetime import datetime
import io
import hashlib
import os

# ==========================================
# CONFIGURAÇÕES DE SEGURANÇA (LGPD)
# ==========================================

# A chave secreta (SALT) para o embaralhamento. 
SALT = os.getenv("APP_SALT_KEY", "chave_secreta_wiki_suporte_2026")

def gerar_hash_lgpd(texto: str) -> str:
    """Gera um Hash irreversível (SHA-256) do dado sensível."""
    if not texto or pd.isna(texto) or texto == "":
        return ""
    dado_com_salt = f"{texto}{SALT}".encode('utf-8')
    return hashlib.sha256(dado_com_salt).hexdigest()

def mascarar_dado_lgpd(texto: str, tipo: str = "telefone") -> str:
    """Mascara os dados para que fiquem seguros na base de dados e no Dashboard."""
    if not texto or pd.isna(texto) or texto == "":
        return ""
    
    texto_str = str(texto)
    if tipo == "telefone":
        # Retorna: (**) *****-1234
        return f"(**) *****-{texto_str[-4:]}" if len(texto_str) >= 4 else "****"
    elif tipo == "nome":
        # Substitui o nome real do cliente
        return "CLIENTE_CONFIDENCIAL"
    return "****"

# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA
# ==========================================

def extrair_apenas_numeros(texto) -> str:
    """Remove letras e caracteres especiais, mantendo apenas dígitos."""
    if pd.isna(texto):
        return ""
    return re.sub(r'\D', '', str(texto))

def padronizar_texto(texto) -> str:
    """Remove espaços duplos, espaços nas extremidades e padroniza para Maiúsculas."""
    if pd.isna(texto):
        return ""
    return re.sub(r'\s+', ' ', str(texto)).strip().upper()


# ==========================================
# FUNÇÃO PRINCIPAL DE LEITURA DE ARQUIVO
# ==========================================

def ler_arquivo_dinamico(arquivo) -> pd.DataFrame:
    """
    Identifica a extensão do arquivo enviado pelo Streamlit 
    e utiliza o motor correto do Pandas (read_csv ou read_excel).
    """
    # O Streamlit UploadedFile possui o atributo .name
    nome_arquivo = arquivo.name.lower()
    
    if nome_arquivo.endswith('.xlsx'):
        # Requer a biblioteca 'openpyxl' instalada
        return pd.read_excel(arquivo)
    else:
        # Padrão CSV com a nossa "mágica do Excel" (separador dinâmico)
        return pd.read_csv(arquivo, sep=None, engine='python')

# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_goto
# ==========================================

# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_goto
# ==========================================

def processar_csv_goto(arquivo: io.BytesIO) -> pd.DataFrame:
    try:
        # A MÁGICA DO EXCEL NO PANDAS: sep=None obriga o Pandas a descobrir sozinho
        # se o arquivo usa vírgula, ponto e vírgula ou tabulação, e separa as colunas perfeitamente.
        df_bruto = ler_arquivo_dinamico(arquivo)
        df_limpo = pd.DataFrame()

        # 1. Tratamento Inteligente da Data (O verdadeiro causador do erro)
        data_col = df_bruto.get('Data [America/Sao_Paulo]')
        
        # O format='ISO8601' é o que impede que a data do GoTo (sem milissegundos) vire Nula!
        datas_convertidas = pd.to_datetime(data_col, format='ISO8601', errors='coerce')
        
        # Remove o fuso horário (timezone) para compatibilidade perfeita com o banco de dados
        if datas_convertidas.dt.tz is not None:
            datas_convertidas = datas_convertidas.dt.tz_localize(None)
            
        df_limpo['data_chamada'] = datas_convertidas

        # 2. Extração Base
        df_limpo['id_conversa'] = df_bruto.get('Conversation space id', '').astype(str).str.strip().replace('nan', '')
        df_limpo['duracao_ms'] = pd.to_numeric(df_bruto.get('Duração [milissegundos]'), errors='coerce').astype('Int64')
        df_limpo['direcao'] = df_bruto.get('Direção', pd.Series(dtype=str)).apply(padronizar_texto)
        df_limpo['resultado'] = df_bruto.get('Resultado da chamada', pd.Series(dtype=str)).apply(padronizar_texto)
        
        # 3. Segurança e LGPD
        telefone_raw = df_bruto.get('De', pd.Series(dtype=str)).apply(extrair_apenas_numeros)
        df_limpo['telefone_hash'] = telefone_raw.apply(gerar_hash_lgpd)
        df_limpo['telefone_origem'] = telefone_raw.apply(lambda x: mascarar_dado_lgpd(x, "telefone"))
        
        df_limpo['participantes'] = df_bruto.get('Participantes', '').astype(str).replace('nan', '')
        df_limpo['gravado'] = df_bruto.get('Gravações', 'false').astype(str).str.lower()
        df_limpo['data_importacao'] = datetime.now()

        # 4. AUTO-CURA: GERAÇÃO DE ID SINTÉTICO (Sem descartar NENHUMA linha)
        def resolver_id_faltante(row):
            id_original = row['id_conversa']
            if id_original != '':
                return id_original
                
            # Cria um ID sintético inquebrável baseado na data, telefone e duração
            assinatura_evento = f"{row['data_chamada']}_{row['telefone_hash']}_{row['duracao_ms']}"
            hash_sintetico = hashlib.md5(assinatura_evento.encode('utf-8')).hexdigest()
            return f"SINTETICO_{hash_sintetico}"

        df_limpo['id_conversa'] = df_limpo.apply(resolver_id_faltante, axis=1)

        # RETIRAMOS O DROPNA: Nenhuma informação será descartada ou jogada fora!
        return df_limpo
        
    except Exception as e:
        raise ValueError(f"Erro no processamento GoTo: {e}")

# ==========================================
# PROCESSAMENTO PARA A TABELA: atendimentos_multi360
# ==========================================

def processar_csv_multi360(arquivo: io.BytesIO) -> pd.DataFrame:
    try:
        df_bruto = ler_arquivo_dinamico(arquivo)
        df_limpo = pd.DataFrame()

        if 'PROTOCOLO' in df_bruto.columns:
            df_limpo['protocolo'] = pd.to_numeric(df_bruto['PROTOCOLO'], errors='coerce').astype('Int64')
            
        if 'ORIGEM' in df_bruto.columns:
            df_limpo['origem'] = df_bruto['ORIGEM'].apply(padronizar_texto)
            
        if 'STATUS' in df_bruto.columns:
            df_limpo['status'] = df_bruto['STATUS'].apply(padronizar_texto)
            
        if 'ATENDENTE' in df_bruto.columns:
            df_limpo['atendente'] = df_bruto['ATENDENTE'].astype(str).str.strip().replace('nan', '')
            
        if 'DEPARTAMENTO' in df_bruto.columns:
            df_limpo['departamento'] = df_bruto['DEPARTAMENTO'].astype(str).str.strip().replace('nan', '')
            
        # LGPD: Anonimização de Nomes
        if 'NOME' in df_bruto.columns:
            df_limpo['nome_contato'] = df_bruto['NOME'].apply(lambda x: mascarar_dado_lgpd(x, "nome"))
            
        # LGPD: Hashing e Mascaramento de Telefones do WhatsApp
        if 'NUMERO' in df_bruto.columns:
            num_raw = df_bruto['NUMERO'].apply(extrair_apenas_numeros)
            df_limpo['telefone_hash'] = num_raw.apply(gerar_hash_lgpd)
            df_limpo['numero_telefone'] = num_raw.apply(lambda x: mascarar_dado_lgpd(x, "telefone"))
            
        if 'DATA' in df_bruto.columns:
            df_limpo['data_inicio'] = pd.to_datetime(df_bruto['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'DATAFINALIZACAO' in df_bruto.columns:
            df_limpo['data_finalizacao'] = pd.to_datetime(df_bruto['DATAFINALIZACAO'], format='%d/%m/%Y %H:%M', errors='coerce')
        
        # --- BLOCO DE DATAS NO SEU processador_csv.py ---
        if 'DATA' in df_bruto.columns:
            df_limpo['data_inicio'] = pd.to_datetime(df_bruto['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'DATAFINALIZACAO' in df_bruto.columns:
            df_limpo['data_finalizacao'] = pd.to_datetime(df_bruto['DATAFINALIZACAO'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        
        if 'DATAULTIMAMENSAGEM' in df_bruto.columns:
            # Tenta converter a data da última mensagem
            df_limpo['data_ultima_mensagem'] = pd.to_datetime(df_bruto['DATAULTIMAMENSAGEM'], format='%d/%m/%Y %H:%M', errors='coerce')
            
        if 'AVALIACAO' in df_bruto.columns:
            df_limpo['avaliacao'] = pd.to_numeric(df_bruto['AVALIACAO'], errors='coerce').astype('Int64')
            
        df_limpo['data_importacao'] = datetime.now()

        return df_limpo
    except Exception as e:
        raise ValueError(f"Falha estrutural ao processar o CSV do Multi360. Detalhes: {e}")

    
# =====================================================================
# 2. A MÁGICA AUTOMÁTICA DA TEIA DE ARANHA (LGPD)
# =====================================================================
    with st.spinner("🕸️ Sincronizando ligações e chats órfãos do passado..."):
                        
    # Dispara a varredura para o GoTo (Ligações)
        linhas_goto = oraculo.sincronizar_vinculos_goto()
                        
    # Dispara a varredura para o Multi360 (WhatsApp)
        linhas_multi360 = oraculo.sincronizar_vinculos_multi360()
                        
        total_linhas = linhas_goto + linhas_multi360
                      
        if total_linhas > 0:
            st.info(f"🚀 Incrível! O sistema vinculou **{linhas_goto} ligações** e **{linhas_multi360} chats** antigos a este cliente.")
        else:
            st.info("Nenhum atendimento antigo pendente foi encontrado para este telefone específico.")
# =====================================================================