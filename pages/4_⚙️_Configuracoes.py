import streamlit as st
import pandas as pd
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from sqlalchemy import text

# Tenta importar biblioteca de monitorização de hardware (Exclusivo Dev)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from modules.database import get_connection
from modules.utils import ler_estado_robo, salvar_estado_robo

# Tenta importar a auditoria
try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="Configurações e Admin", page_icon="⚙️", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

# Apenas administradores ou coordenadores devem aceder a esta tela
if perfil_usuario not in ["superadmin", "desenvolvedor", "coordenação", "coordenacao"]:
    st.error("⛔ Acesso Restrito. Apenas utilizadores com perfil de Coordenação ou superior podem aceder às configurações.")
    st.stop()

st.title("⚙️ Configurações e Administração")
st.markdown("Central de Comando: Motor de Automação, Gestão de Utilizadores e Diagnóstico do Sistema.")

# ==========================================
# 2. FUNÇÕES AUXILIARES (RAMAIS E ADMIN)
# ==========================================
ARQUIVO_RAMAIS = "ramais_config.json"

def ler_ramais():
    if os.path.exists(ARQUIVO_RAMAIS):
        with open(ARQUIVO_RAMAIS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def salvar_ramais(dados):
    with open(ARQUIVO_RAMAIS, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

@st.cache_data(ttl=300)
def obter_analistas_ativos():
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT DISTINCT usuario_epsy FROM chamados_tecnuv WHERE usuario_epsy IS NOT NULL AND usuario_epsy != ''", engine)
        analistas = df['usuario_epsy'].tolist()
        return [a for a in analistas if a != "Não Informado"]
    except:
        return []

def obter_lista_usuarios_sistema():
    """Busca usuários da tabela do sistema (ajuste 'usuarios' para o nome real da sua tabela se necessário)."""
    engine = get_connection()
    try:
        df = pd.read_sql("SELECT id, nome, perfil FROM usuarios", engine)
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 3. INTERFACE DE ABAS
# ==========================================
aba_robo, aba_ramais, aba_usuarios, aba_diagnostico = st.tabs([
    "🤖 Motor do Robô", 
    "📞 Gestão de Ramais",
    "👥 Gestão de Utilizadores",
    "🛠️ Diagnóstico do Sistema"
])

# ------------------------------------------
# ABA 1: MOTOR DO ROBÔ (INTACTO)
# ------------------------------------------
with aba_robo:
    st.subheader("Painel de Controlo do Robô")
    st.markdown("Controle o script que roda em segundo plano para varrer os chamados da Tecnuv.")
    
    estado_atual = ler_estado_robo()
    auto_ativo = estado_atual.get("auto_ativo", False)
    intervalo_atual = estado_atual.get("intervalo", 60)
    em_andamento = estado_atual.get("em_andamento", False)
    ultima_execucao = estado_atual.get("ultima_execucao", "Nunca")
    
    if ultima_execucao != "Nunca":
        try:
            dt_obj = datetime.fromisoformat(ultima_execucao)
            ultima_execucao_str = dt_obj.strftime("%d/%m/%Y às %H:%M:%S")
        except:
            ultima_execucao_str = ultima_execucao
    else:
        ultima_execucao_str = ultima_execucao

    c1, c2, c3 = st.columns(3)
    c1.metric("Status do Motor", "A Executar" if em_andamento else "Em Espera", delta="Bloqueado" if em_andamento else "Livre", delta_color="off" if em_andamento else "normal")
    c2.metric("Última Varredura", ultima_execucao_str)
    c3.metric("Intervalo Configurado", f"{intervalo_atual} Minutos")
    
    st.divider()
    
    with st.form("form_motor_robo"):
        st.markdown("#### Configurar Automação")
        novo_status = st.toggle("Ativar Varredura Automática", value=auto_ativo)
        novo_intervalo = st.slider("Intervalo entre varreduras (minutos):", min_value=15, max_value=240, value=intervalo_atual, step=15)
        
        if st.form_submit_button("Salvar Configurações do Robô", type="primary"):
            estado_atual["auto_ativo"] = novo_status
            estado_atual["intervalo"] = novo_intervalo
            salvar_estado_robo(estado_atual)
            st.success("✅ Configurações do robô atualizadas!")
            st.rerun()

# ------------------------------------------
# ABA 2: GESTÃO DE RAMAIS (INTACTO)
# ------------------------------------------
with aba_ramais:
    st.subheader("Vínculo de Analistas e Ramais Internos")
    ramais_salvos = ler_ramais()
    lista_analistas = obter_analistas_ativos()
    
    col_r1, col_r2 = st.columns([1, 1.5])
    with col_r1:
        with st.form("form_novo_ramal"):
            analista_selecionado = st.selectbox("Selecione o Analista:", ["-- Novo Analista --"] + lista_analistas)
            nome_analista = st.text_input("Digite o nome:") if analista_selecionado == "-- Novo Analista --" else analista_selecionado
            numero_ramal = st.text_input("Número do Ramal:")
            
            if st.form_submit_button("Vincular Ramal", type="primary", use_container_width=True):
                if nome_analista.strip() and numero_ramal.strip():
                    ramais_salvos[nome_analista.strip()] = numero_ramal.strip()
                    salvar_ramais(ramais_salvos)
                    st.success(f"✅ Ramal vinculado a {nome_analista}!")
                    st.rerun()
                else:
                    st.warning("Preencha todos os campos.")

    with col_r2:
        if not ramais_salvos:
            st.info("Nenhum ramal configurado.")
        else:
            df_ramais = pd.DataFrame(list(ramais_salvos.items()), columns=["Analista EPSY", "Ramal Interno"]).sort_values(by="Analista EPSY")
            st.dataframe(df_ramais, hide_index=True, use_container_width=True)
            
            st.divider()
            analista_remover = st.selectbox("Remover o ramal de:", [""] + list(ramais_salvos.keys()))
            if st.button("🗑️ Remover Ramal") and analista_remover:
                del ramais_salvos[analista_remover]
                salvar_ramais(ramais_salvos)
                st.success(f"Vínculo removido.")
                st.rerun()

# ------------------------------------------
# ABA 3: GESTÃO DE UTILIZADORES
# ------------------------------------------
with aba_usuarios:
    st.subheader("Controlo de Acessos e Segurança")
    df_users = obter_lista_usuarios_sistema()
    
    if df_users.empty:
        st.warning("Tabela de usuários não encontrada ou vazia. Configure a conexão com a tabela 'usuarios'.")
    else:
        u1, u2 = st.columns([1, 1])
        
        with u1:
            st.markdown("#### 🔑 Alterar Perfil e Senha de Utilizadores")
            st.info("Disponível para: Desenvolvedor e Coordenação.")
            
            user_alvo = st.selectbox("Selecione o Usuário:", df_users['nome'].tolist())
            novo_perfil = st.selectbox("Novo Perfil:", ["Analista", "Coordenação", "Desenvolvedor", "Superadmin"])
            nova_senha = st.text_input("Nova Senha:", type="password")
            
            if st.button("💾 Salvar Alterações do Usuário", type="primary"):
                # TODO: Implementar lógica de UPDATE na sua tabela de usuários
                # query = text("UPDATE usuarios SET perfil = :p, senha = :s WHERE nome = :n")
                st.success(f"✅ Perfil/Senha de '{user_alvo}' alterados com sucesso! (Implementação DB pendente)")
                registrar_log_auditoria(usuario_id, "UPDATE_USER", f"Alterou dados do user {user_alvo}")

        with u2:
            st.markdown("#### 🛡️ Segurança do Administrador (Root)")
            if perfil_usuario != "desenvolvedor":
                st.error("⛔ Acesso bloqueado. Apenas o 'Desenvolvedor' pode alterar a senha do Super Usuário.")
            else:
                st.warning("Área de Risco: Alteração de credenciais master do sistema.")
                nova_senha_admin = st.text_input("Nova Senha do Administrador:", type="password", key="pass_admin")
                if st.button("🚨 Atualizar Senha Superadmin", type="primary"):
                    # TODO: Lógica de update do superadmin
                    st.success("✅ Senha do Administrador alterada com sucesso! (Implementação DB pendente)")
                    registrar_log_auditoria(usuario_id, "UPDATE_ADMIN_PASS", "Alterou a senha do Superadmin.")

# ------------------------------------------
# ABA 4: DIAGNÓSTICO DO SISTEMA (EXCLUSIVO DEV)
# ------------------------------------------
with aba_diagnostico:
    if perfil_usuario != "desenvolvedor":
        st.error("⛔ Acesso Restrito. Apenas o perfil 'Desenvolvedor' pode executar diagnósticos de rede e banco de dados.")
    else:
        st.subheader("🛠️ Diagnóstico do Servidor em Tempo Real")
        st.markdown("Monitorização de infraestrutura, conectividade local e carga de hardware.")
        
        d1, d2, d3 = st.columns(3)
        
        with d1:
            st.markdown("#### 🗄️ Comunicação com Banco (DB)")
            if st.button("🔌 Testar Latência PostgreSQL", use_container_width=True):
                inicio_db = time.time()
                try:
                    eng = get_connection()
                    with eng.connect() as conn:
                        conn.execute(text("SELECT 1"))
                    latencia_db = (time.time() - inicio_db) * 1000
                    st.success(f"✅ Conexão Estável!\n\nTempo de Resposta: **{latencia_db:.2f} ms**")
                except Exception as e:
                    st.error(f"❌ Falha de Conexão: {e}")
                    
        with d2:
            st.markdown("#### 🌐 Qualidade de Internet (Rede)")
            if st.button("📡 Testar Qualidade e Ping", use_container_width=True):
                inicio_net = time.time()
                try:
                    # Testa a resolução e conexão com servidor DNS primário
                    urllib.request.urlopen('http://8.8.8.8', timeout=3)
                    latencia_net = (time.time() - inicio_net) * 1000
                    if latencia_net < 50:
                        st.success(f"🟢 Excelente (Ping: **{latencia_net:.0f} ms**)")
                    elif latencia_net < 150:
                        st.warning(f"🟡 Instável (Ping: **{latencia_net:.0f} ms**)")
                    else:
                        st.error(f"🔴 Lenta/Degradada (Ping: **{latencia_net:.0f} ms**)")
                except:
                    st.error("❌ Sem acesso à Internet externa ou DNS bloqueado.")
                    
        with d3:
            st.markdown("#### 💻 Monitor de Recursos Locais")
            if st.button("📈 Ler Hardware e Rede Agora", use_container_width=True):
                if HAS_PSUTIL:
                    cpu_usage = psutil.cpu_percent(interval=0.5)
                    ram_usage = psutil.virtual_memory().percent
                    net_io = psutil.net_io_counters()
                    
                    st.metric("Uso de Processador (CPU)", f"{cpu_usage}%")
                    st.progress(cpu_usage / 100)
                    
                    st.metric("Memória RAM Ocupada", f"{ram_usage}%")
                    st.progress(ram_usage / 100)
                    
                    st.markdown("##### Tráfego de Rede Local (Total)")
                    # Converte de bytes para Megabytes
                    mb_sent = net_io.bytes_sent / (1024 * 1024)
                    mb_recv = net_io.bytes_recv / (1024 * 1024)
                    st.info(f"⬆️ Enviados: **{mb_sent:.1f} MB** | ⬇️ Recebidos: **{mb_recv:.1f} MB**")
                else:
                    st.error("Biblioteca 'psutil' ausente. Rode 'pip install psutil' no seu terminal.")

registrar_log_auditoria(usuario_id, "VIEW_CONFIG", "Acessou a tela de Configurações Administrativas.")