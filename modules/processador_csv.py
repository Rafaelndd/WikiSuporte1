import pandas as pd
import re

# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA
# ==========================================

def limpar_html(texto):
    """Remove tags HTML de um texto usando Expressões Regulares."""
    if pd.isna(texto):
        return texto
    texto_string = str(texto)
    # Substitui qualquer coisa entre < e > por vazio
    texto_limpo = re.sub(r'<.*?>', '', texto_string)
    return texto_limpo

def extrair_apenas_numeros(texto):
    """Remove letras e caracteres especiais, mantendo apenas números."""
    if pd.isna(texto):
        return texto
    texto_string = str(texto)
    # \D significa "tudo que não é dígito"
    numeros = re.sub(r'\D', '', texto_string)
    return numeros

def padronizar_texto(texto):
    """Remove espaços duplos, espaços nas pontas e padroniza para Maiúsculas."""
    if pd.isna(texto):
        return texto
    texto_string = str(texto)
    # Substitui múltiplos espaços por um só e remove espaços nas pontas (strip)
    texto_limpo = re.sub(r'\s+', ' ', texto_string).strip().upper()
    return texto_limpo

# ==========================================
# FUNÇÕES DE PROCESSAMENTO DOS ARQUIVOS
# ==========================================

def processar_goto(caminho_arquivo):
    """Lê, limpa e padroniza o CSV do GoTo."""
    df = pd.read_csv(caminho_arquivo)
    
    # Exemplo de mapeamento de colunas (Ajuste conforme as colunas reais do seu CSV)
    # Vamos supor que existam colunas como 'Data', 'De', 'Assunto', 'Motivo', etc.
    df_padrao = pd.DataFrame()
    
    # 1. Padronização de Colunas e Datas
    if 'Data [America/Sao_Paulo]' in df.columns:
        df_padrao['data_abertura'] = pd.to_datetime(df['Data [America/Sao_Paulo]'], errors='coerce')
    
    # 2. Limpeza de Telefones (De / Participantes)
    df_padrao['telefone'] = df['De'].apply(extrair_apenas_numeros)
    
    # 3. Limpeza de HTML e Texto (Assunto e Motivo)
    # Usamos try/except caso a coluna não exista no CSV testado
    df_padrao['assunto'] = df.get('Assunto', '').apply(limpar_html).apply(padronizar_texto)
    df_padrao['motivo'] = df.get('Motivo', '').apply(limpar_html).apply(padronizar_texto)
    
    # 4. Colunas fixas
    df_padrao['canal'] = 'GOTO'
    df_padrao['status'] = df.get('Resultado da chamada', '').apply(padronizar_texto)
    
    return df_padrao

def processar_multi360(caminho_arquivo):
    """Lê, limpa e padroniza o CSV do Multi360."""
    # Multi360 costuma separar por vírgula. Vamos ler o arquivo.
    df = pd.read_csv(caminho_arquivo)
    
    df_padrao = pd.DataFrame()
    
    # 1. Mapeamento e conversão de datas
    df_padrao['data_abertura'] = pd.to_datetime(df['DATA'], format='%d/%m/%Y %H:%M', errors='coerce')
    
    # 2. Textos e Telefones
    df_padrao['cliente'] = df['NOME'].apply(padronizar_texto)
    df_padrao['telefone'] = df['NUMERO'].apply(extrair_apenas_numeros)
    df_padrao['motivo'] = df['MOTIVO'].apply(padronizar_texto)
    df_padrao['status'] = df['STATUS'].apply(padronizar_texto)
    
    # 3. Colunas fixas
    df_padrao['canal'] = 'MULTI360'
    df_padrao['assunto'] = '' # Multi360 pode não ter assunto, mantemos vazio para manter a mesma estrutura
    
    return df_padrao