import os
import time
import requests
from google import genai
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# --- 1. CONFIGURAÇÕES E CREDENCIAIS ---
DATABASE_URL = "postgresql://postgres:19983101@localhost:5455/central_chamados"
PASTA_PDFS = r"C:\WikiSuporte\uploads_wiki"

# É mandatório que a variável GEMINI_API_KEY esteja configurada no ambiente
CHAVE_GEMINI = os.environ.get("GEMINI_API_KEY") 

# Inicializa o NOVO cliente do Google GenAI
client = genai.Client(api_key=CHAVE_GEMINI)

# --- 2. INICIALIZAÇÃO E AUTO-RECUPERAÇÃO ---
if not os.path.exists(PASTA_PDFS):
    os.makedirs(PASTA_PDFS)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def garantir_estrutura_banco():
    """Garante que a coluna texto_extraido exista antes de iniciar o processamento."""
    print("Verificando integridade da tabela base_conhecimento...")
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE base_conhecimento ADD COLUMN IF NOT EXISTS texto_extraido TEXT;"))
        print("✅ Estrutura do banco validada com sucesso.\n")
    except Exception as e:
        print(f"❌ Falha crítica ao alterar a estrutura do banco: {e}")
        exit(1)

def extrair_texto_e_imagens_com_ia(caminho_pdf):
    """Envia o PDF para a IA usando a NOVA arquitetura do SDK."""
    ficheiro_gemini = None
    try:
        print(f"   -> Enviando arquivo para análise da IA (Nova API)...")
        # Novo método de upload
        ficheiro_gemini = client.files.upload(file=caminho_pdf, config={'mime_type': 'application/pdf'})
        
        prompt = (
            "Você é um analista técnico sênior. Leia atentamente este manual de suporte. "
            "Extraia todo o texto contido nele. Além disso, sempre que encontrar uma imagem, tela "
            "ou 'print screen', descreva detalhadamente o que a imagem mostra e qual ação "
            "está sendo demonstrada no sistema. Formate a saída de forma limpa, focando na informação técnica."
        )
        
        print(f"   -> Processando extração multimodal...")
        # Novo método de geração de conteúdo
        resposta = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[ficheiro_gemini, prompt]
        )
        
        return resposta.text

    except Exception as e:
        print(f"   -> Erro no processamento da IA: {e}")
        return None
    finally:
        # Limpeza obrigatória na nuvem do Google usando o novo SDK
        if ficheiro_gemini:
            try:
                client.files.delete(name=ficheiro_gemini.name)
            except Exception as delete_error:
                print(f"   -> Aviso: Não foi possível deletar o arquivo na nuvem: {delete_error}")

def processar_teste_piloto():
    # A trava de segurança LIMIT 5 continua ativa para validação
    query = text("""
        SELECT id, conteudo 
        FROM base_conhecimento 
        WHERE conteudo LIKE 'URL_DOCUMENTO:%' 
        AND texto_extraido IS NULL
        LIMIT 5
    """)
    registros = session.execute(query).fetchall()
    
    if not registros:
        print("Nenhum manual pendente de processamento no momento.")
        return

    print(f"Iniciando Teste Piloto com {len(registros)} manuais...\n")

    for registro in registros:
        doc_id = registro[0]
        url = registro[1].replace("URL_DOCUMENTO: ", "").strip()
        nome_arquivo = url.split("/")[-1]
        caminho_local = os.path.join(PASTA_PDFS, nome_arquivo)

        try:
            print(f"[ID: {doc_id}] Baixando PDF: {nome_arquivo}...")
            resposta_http = requests.get(url, timeout=15)
            resposta_http.raise_for_status()
            
            with open(caminho_local, "wb") as f:
                f.write(resposta_http.content)
            
            texto_rico = extrair_texto_e_imagens_com_ia(caminho_local)
            
            if texto_rico:
                update_query = text("UPDATE base_conhecimento SET texto_extraido = :texto WHERE id = :id")
                session.execute(update_query, {"texto": texto_rico, "id": doc_id})
                session.commit()
                print(f"[ID: {doc_id}] ✅ Extração salva com sucesso!")
            
            print("   -> Pausando 15 segundos para resfriamento da API...\n")
            time.sleep(15)
                
        except Exception as e:
            session.rollback()
            print(f"[ID: {doc_id}] ❌ Erro na operação: {e}\n")

if __name__ == "__main__":
    # Garante que o banco está pronto antes de tentar qualquer extração
    garantir_estrutura_banco()
    processar_teste_piloto()