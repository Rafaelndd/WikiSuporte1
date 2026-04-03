import os
import requests
from dotenv import load_dotenv

# Carrega a chave segura do .env
load_dotenv()
API_KEY = os.getenv("CLICKUP_API_KEY")

# As listas que você acabou de mapear
LISTA_SUPORTE_ATIVO = "901113360407"
LISTA_SUPORTE_CONCLUIDO = "901113360635"

def buscar_tickets_wiki(list_id):
    """
    Conecta na lista do ClickUp e devolve as tarefas formatadas.
    """
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task?archived=false"

    headers = {
        "Authorization": API_KEY,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() 
        
        dados_clickup = response.json()
        tickets = []
        
        # O ClickUp devolve muitos dados. Aqui filtramos só o que o WikiSuporte precisa:
        for task in dados_clickup.get('tasks', []):
            ticket = {
                "id_clickup": task.get('id'),
                "titulo": task.get('name'),
                "status": task.get('status', {}).get('status', 'Sem status'),
                "prioridade": task.get('priority', {}).get('priority', 'Normal') if task.get('priority') else 'Normal',
                "criado_por": task.get('creator', {}).get('username', 'Desconhecido'),
                "link_direto": task.get('url')
            }
            tickets.append(ticket)
            
        return tickets

    except requests.exceptions.RequestException as e:
        print(f"🚨 Nico avisa: Falha na comunicação com o ClickUp! Erro: {e}")
        return []

# ==========================================
# TESTE RÁPIDO DO SERVIÇO
# ==========================================
if __name__ == "__main__":
    print("Buscando demandas ativas...\n")
    demandas = buscar_tickets_wiki(LISTA_SUPORTE_ATIVO)
    
    if not demandas:
        print("Nenhuma demanda encontrada ou houve um erro.")
    else:
        for d in demandas:
            print(f"[{d['status'].upper()}] {d['titulo']} (Prioridade: {d['prioridade']})")
            print(f"Link: {d['link_direto']}\n")