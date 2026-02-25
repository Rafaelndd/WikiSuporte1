import os
import json
from datetime import datetime

# ==========================================
# GESTÃO DE ESTADO DO ROBÔ (COOLDOWN E LOGS)
# ==========================================
ARQUIVO_ESTADO_ROBO = "robo_state.json"

def ler_estado_robo():
    if os.path.exists(ARQUIVO_ESTADO_ROBO):
        try:
            with open(ARQUIVO_ESTADO_ROBO, 'r') as f:
                return json.load(f)
        except: pass
    return {"ultima_execucao": None, "em_andamento": False, "auto_ativo": False}

def salvar_estado_robo(estado):
    with open(ARQUIVO_ESTADO_ROBO, 'w') as f:
        json.dump(estado, f)

def ler_logs_robo(caminho_arquivo="oraculo_engine.log", ultimas_linhas=50):
    if not os.path.exists(caminho_arquivo):
        return "Nenhum registo encontrado."
    try:
        with open(caminho_arquivo, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()
            return "".join(linhas[-ultimas_linhas:])
    except Exception as e:
        return f"Erro ao ler log: {e}"