import requests
import os
from dotenv import load_dotenv

# Carrega a chave segura do .env
load_dotenv()
MINHA_CHAVE = os.getenv("CLICKUP_API_KEY")
if not MINHA_CHAVE:
    raise SystemExit("Configure a variável CLICKUP_API_KEY para executar o mapeamento do ClickUp.")

# O ID da Epsy Sistemas que já descobrimos!
TEAM_ID = "9011536670"

headers = {
    "Authorization": MINHA_CHAVE,
    "Content-Type": "application/json"
}

print("Radar ClickUp ativado! Mapeando sua estrutura... Isso pode levar alguns segundos.\n")

# Passo 1: Buscar todos os Spaces
spaces_url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/space"
spaces_response = requests.get(spaces_url, headers=headers, timeout=20).json()

# Iterar sobre cada Space encontrado
for space in spaces_response.get('spaces', []):
    print(f"🚀 SPACE: {space['name']} (ID: {space['id']})")

    # Passo 2: Buscar Pastas (Folders) dentro deste Space
    folders_url = f"https://api.clickup.com/api/v2/space/{space['id']}/folder"
    folders_response = requests.get(folders_url, headers=headers, timeout=20).json()

    for folder in folders_response.get('folders', []):
        print(f"  📂 FOLDER: {folder['name']} (ID: {folder['id']})")

        # Passo 3: Buscar Listas dentro desta Pasta
        lists_url = f"https://api.clickup.com/api/v2/folder/{folder['id']}/list"
        lists_response = requests.get(lists_url, headers=headers, timeout=20).json()

        for lst in lists_response.get('lists', []):
            print(f"    📋 LISTA: {lst['name']} (ID: {lst['id']})")

    # Passo 4: Buscar Listas "soltas" (Folderless) direto no Space
    folderless_url = f"https://api.clickup.com/api/v2/space/{space['id']}/list"
    folderless_response = requests.get(folderless_url, headers=headers, timeout=20).json()

    for lst in folderless_response.get('lists', []):
        print(f"  📋 LISTA (Sem pasta): {lst['name']} (ID: {lst['id']})")
        
    print("-" * 40) # Apenas um separador visual
    
print("\nMapeamento concluído!")