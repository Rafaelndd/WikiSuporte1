import os
import json
from datetime import datetime
import streamlit as st



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

# 1. Centralizamos os dados das patentes
NIVEIS_CONHECIMENTO = [
    {"xp": 1000000, "nome": "Expert", "icon": "💠", "cor": "#FFFFFF"},
    {"xp": 950000, "nome": "Lenda do Suporte", "icon": "🔱", "cor": "#1E90FF"},
    {"xp": 850000, "nome": "Referência Técnica", "icon": "💎", "cor": "#B9F2FF"},
    {"xp": 700000, "nome": "Analista Mestre", "icon": "☄️", "cor": "#808080"},
    {"xp": 550000, "nome": "Analista Pleno", "icon": "⚡", "cor": "#00FFFF"},
    {"xp": 400000, "nome": "Analista Jr", "icon": "🧿", "cor": "#0000FF"},
    {"xp": 250000, "nome": "Especialista Sênior", "icon": "🔮", "cor": "#9932CC"},
    {"xp": 150000, "nome": "Especialista N2", "icon": "🦾", "cor": "#778899"},
    {"xp": 100000, "nome": "Especialista N1", "icon": "💾", "cor": "#4682B4"},
    {"xp": 75000, "nome": "Contribuidor Pleno", "icon": "💠", "cor": "#E0E0E0"},
    {"xp": 50000, "nome": "Contribuidor Ativo", "icon": "🥈", "cor": "#C0C0C0"},
    {"xp": 20000, "nome": "Contribuidor Jr", "icon": "🛡️", "cor": "#708090"},
    {"xp": 10000, "nome": "Novato Consistente", "icon": "⚙️", "cor": "#888"},
    {"xp": 5000, "nome": "Novato Proativo", "icon": "🥉", "cor": "#B87333"},
    {"xp": 1000, "nome": "Novato Aspirante", "icon": "🌑", "cor": "#444"}
]

# 2. Função para saber a patente atual baseada no XP
def calcular_patente(xp):
    for n in NIVEIS_CONHECIMENTO:
        if xp >= n['xp']:
            return n
    return {"xp": 0, "nome": "Estagiário", "icon": "🌱", "cor": "#777"}

# 3. Função para garantir que o XP exista em todas as páginas
def inicializar_usuario():
    if "xp" not in st.session_state:
        st.session_state.xp = 0  # Valor inicial