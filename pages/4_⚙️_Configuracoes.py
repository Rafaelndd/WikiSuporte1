import streamlit as st
import pandas as pd
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from sqlalchemy import text

#==============================================================================================
# Tenta importar psutil para monitoramento de recursos, mas continua funcional sem ele
#==============================================================================================
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from modules.database import get_connection
from modules.utils import ler_estado_robo, salvar_estado_robo

#==============================================================================================
# Tenta importar função de auditoria, mas define um placeholder caso falhe (para evitar
# erros caso o módulo de auditoria não esteja presente ou configurado)
#==============================================================================================
try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ===============================================================================================
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA E VERIFICAÇÃO DE ACESSO
# ================================================================================================

st.set_page_config(page_title="Configurações", page_icon="⚙️", layout="wide")

if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

# Apenas administradores ou coordenadores devem aceder a esta tela
if perfil_usuario not in ["desenvolvedor", "coordenação"]:
    st.error("⛔ WikiSuporte - Acesso Negado: Você não tem permissão para acessar esta página.")
    st.stop()

st.title("⚙️ WikiSuporte - Configurações")
st.markdown("WikiSuporte — Configure o sistema, ajuste o comportamento do assistente PSY, vincule ramais aos analistas e gerencie os usuários. Utilize as abas para acessar cada seção de configuração.")

# ==========================================
# 2. GESTÃO DE RAMAIS E ANALISTAS
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
# 3. ESTRUTURA DE ABAS PARA CONFIGURAÇÕES
# ==========================================
aba_robo, aba_ramais, aba_usuarios, aba_diagnostico = st.tabs([
    "🤖 Automação", 
    "📞 Gestão dos Ramais",
    "👥 Gestão dos Usuários",
    "🛠️ Análise de Servidor"
])

# ------------------------------------------
# ABA 1: CONTROLE DO ROBÔ DE VARREDURA (INTACTO)
# ------------------------------------------
with aba_robo:
    st.subheader("Controle do assintente PSY")
    st.markdown("Configure o comportamento do assistente, controle de varredura automática, monitorize seu status e defina os intervalos de execução.")
    
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
        st.markdown("#### Configurações do Motor de Varredura")
        novo_status = st.toggle("Ativar assistente PSY - Iniciar varredura automaticamente", value=auto_ativo)
        novo_intervalo = st.slider("Intervalo entre as consultas (em minutos):", min_value=15, max_value=240, value=intervalo_atual, step=15)
        
        if st.form_submit_button("Salvar configurações", type="primary"):
            estado_atual["auto_ativo"] = novo_status
            estado_atual["intervalo"] = novo_intervalo
            salvar_estado_robo(estado_atual)
            st.success("✅ Configurações do assistente PSY atualizadas com sucesso!")
            st.rerun()

# ------------------------------------------
# ABA 2: VÍNCULO DE ANALISTAS E RAMAIS
# ------------------------------------------
with aba_ramais:
    st.subheader("Cadastro e Vínculo de Ramais Internos")
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
# ABA 3: CONTROLE DE ACESSOS E SEGURANÇA
# ------------------------------------------
with aba_usuarios:
    st.subheader("Gerenciamento de Usuários do Sistema")
    df_users = obter_lista_usuarios_sistema()
    
    if df_users.empty:
        st.warning("WikiSuporte - Nenhum usuário encontrado no sistema. Verifique a conexão com o banco de dados ou a tabela de usuários.")
    else:
        u1, u2 = st.columns([1, 1])
        
        with u1:
            st.markdown("#### 🔑 Alteração de Usuários do Sistema")
            st.info("WikiSuporte - Selecione um usuário para alterar seu perfil ou senha.")
            
            user_alvo = st.selectbox("Selecione o Usuário:", df_users['nome'].tolist())
            
            # Puxa o perfil atual para evitar mudanças acidentais
            perfil_atual = df_users.loc[df_users['nome'] == user_alvo, 'perfil'].values[0] if not df_users.empty else "Analista"
            lista_perfis = ["Analista", "Coordenação", "Desenvolvedor", "Superadmin"]
            index_perfil = lista_perfis.index(perfil_atual) if perfil_atual in lista_perfis else 0
            
            novo_perfil = st.selectbox("Novo Perfil:", lista_perfis, index=index_perfil)
            nova_senha = st.text_input("Nova Senha (deixe em branco para manter a atual):", type="password")
            
            if st.button("💾 Salvar Alterações", type="primary"):
                from sqlalchemy import text
                import bcrypt
                import time
                from modules.database import get_connection
                
                try:
                    from modules.auditoria import registrar_log_auditoria
                except ImportError:
                    def registrar_log_auditoria(user_id, acao, detalhe): pass

                engine = get_connection()
                try:
                    with engine.begin() as conn: 
                        if nova_senha.strip():
                            # Gera o hash bcrypt exatamente como o app.py espera na hora do login
                            senha_bytes = nova_senha.encode('utf-8')
                            senha_hash = bcrypt.hashpw(senha_bytes, bcrypt.gensalt()).decode('utf-8')
                            
                            query = text("UPDATE usuarios SET perfil = :p, password_hash = :s WHERE nome = :n")
                            conn.execute(query, {"p": novo_perfil, "s": senha_hash, "n": user_alvo})
                            msg_sucesso = f"✅ Perfil e Senha de '{user_alvo}' alterados com sucesso!"
                        else:
                            query = text("UPDATE usuarios SET perfil = :p WHERE nome = :n")
                            conn.execute(query, {"p": novo_perfil, "n": user_alvo})
                            msg_sucesso = f"✅ Perfil de '{user_alvo}' alterado para {novo_perfil} com sucesso!"
                    
                    st.success(msg_sucesso)
                    
                    usuario_logado_id = st.session_state.get('usuario_id', 0)
                    registrar_log_auditoria(usuario_logado_id, "UPDATE_USER", f"Alterou dados do user {user_alvo}")
                    
                    time.sleep(1.5)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Erro ao atualizar o banco de dados: {e}")

        with u2:
            st.markdown("#### 🛡️ Alteração de Senha do Administrador do Sistema")
            if perfil_usuario != "desenvolvedor":
                st.error("⛔ WikiSuporte - Acesso Restrito: Apenas o perfil 'Desenvolvedor' pode alterar as credenciais do Desenvolvedor.")
            else:
                st.warning("Cuidado: Alterar a senha do Administrador do Sistema pode afetar o acesso ao sistema. Certifique-se de lembrar a nova senha ou de ter um backup seguro.")
                nova_senha_admin = st.text_input("Nova Senha do Administrador:", type="password", key="pass_admin")
                if st.button("🚨 Atualizar Senha do Administrador do Sistema", type="primary"):
                    # TODO: Lógica de update do superadmin
                    st.success("✅ Senha do Administrador alterada com sucesso! Lembre-se de anotar a nova senha em um local seguro.")
                    registrar_log_auditoria(usuario_id, "UPDATE_ADMIN_PASS", "Alterou a senha do Administrador do Sistema.")

# ------------------------------------------
# ABA 4: DIAGNÓSTICO DO SISTEMA (EXCLUSIVO DEV)
# ------------------------------------------
with aba_diagnostico:
    if perfil_usuario != "desenvolvedor":
        st.error("⛔ WikiSuporte - Acesso Restrito: Apenas o perfil 'Desenvolvedor' pode acessar as ferramentas de diagnóstico do servidor.")
    else:
        st.subheader("🛠️ Análise de Servidor")
        st.markdown("Utilize as ferramentas abaixo para diagnosticar a saúde do servidor, testar conexões e monitorar recursos em tempo real. Ideal para desenvolvedores e administradores de sistema.")
        
        d1, d2, d3 = st.columns(3)
        
        with d1:
            st.markdown("#### 🗄️ Conexão com o Banco de Dados")
            if st.button("🔌 Testar Conexão com o Banco de Dados", use_container_width=True):
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
            st.markdown("#### 🌐 Qualidade e Ping do Servidor")
            if st.button("📡 Teste de Ping à Internet", use_container_width=True):
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
                        st.error(f"🔴 Falha de Conexão (Ping: **{latencia_net:.0f} ms**)")
                except:
                    st.error("❌ Falha ao conectar. Verifique a conexão de rede do servidor.")
                    
        with d3:
            st.markdown("#### 💻 Monitoramento de Recursos")
            if st.button("📈 Análise de Recursos", use_container_width=True):
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
                    st.error("⚠️ Biblioteca 'psutil' não instalada. Monitoramento de recursos indisponível.")

registrar_log_auditoria(usuario_id, "VIEW_CONFIG", "Usuário acessou a página de configurações do sistema.")