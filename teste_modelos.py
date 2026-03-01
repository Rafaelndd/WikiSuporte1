import os
import google.generativeai as genai
from dotenv import load_dotenv

# Carrega a sua chave do .env
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("🔍 Modelos disponíveis para a SUA Chave de API:")
print("-" * 50)

# Pergunta aos servidores do Google a lista real
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Erro ao listar modelos: {e}")