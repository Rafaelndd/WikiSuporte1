"""
WikiSuporte.
Desenvolvido por: [Rafael D. Nascimento]
Data: 2026-02-19
Descrição: Dashboard de Suporte Técnico para gestão avançada e BI do suporte técnico, com foco em segurança, LGPD e experiência do usuário.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from modules.database import get_connection
from modules.auditoria import registrar_log_auditoria 
import bcrypt  
from datetime import datetime, timedelta
import random
from tela_crm import tela_vinculacao_crm
from modules.processador_csv import processar_csv_goto, processar_csv_multi360
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert
import os
import time
from robo_tecnuv import OraculoBot # Importa a sua classe do robô

#_______________________________________________________________________________#
# 1. CONFIGURAÇÃO INICIAL DA PÁGINA E ESTILO
#_______________________________________________________________________________#
st.set_page_config(
    page_title="WikiSuporte - Dashboard de Suporte Técnico",
    page_icon="mascote/psy_braco_cruzado_aposto.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 5% 5% 5% 10%;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DEFINIÇÃO DE PERMISSÕES (RBAC) E MENU
# ==========================================
MENU_CONFIGURACOES = {
    1: "01- Alterar senha dos usuários",
    2: "02- Alterar Perfil dos usuários",
    3: "03- Visualizar Relatórios com dados dos chamados",
    4: "04- Visualizar Relatórios (Multi360 & Goto)",
    5: "05- Visualizar Dashboard com dados dos chamados",
    6: "06- Visualizar Dashboard (Multi360 & Goto)",
    7: "07- Visualizar usuários ativos",
    8: "08- Visualizar contribuições dos usuários",
    9: "09- Testar comunicação com Banco de dados",
    10: "10- Testar qualidade da internet na Rede",
    11: "11- Monitor de recursos do servidor",
    12: "12- Alterar senha do usuário Administrador (Super Usuário)",
    13: "13- Configurar Robô"
}

def obter_opcoes_por_perfil(perfil_usuario):
    """Filtra o menu de configurações baseado no perfil em lowercase."""
    perfil = str(perfil_usuario).strip().lower()
    
    if perfil == "superadmin":
        permitidos = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    elif perfil == "coordenação" or perfil == "coordenacao":
        permitidos = [1, 2, 3, 4, 5, 6, 7, 8]
    else: 
        permitidos = [3, 5, 8]
        
    return [MENU_CONFIGURACOES[i] for i in permitidos]

# ==========================================
# 3. FUNÇÕES DE SEGURANÇA E LGPD
# ==========================================
def verificar_login(username, senha_digitada):
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT id, password_hash, perfil FROM usuarios_dashboard WHERE username = :u AND ativo = TRUE")
            resultado = conn.execute(query, {"u": username}).fetchone()
            
            if resultado:
                usuario_id = resultado[0]
                senha_hash_banco = resultado[1].encode('utf-8')
                perfil = resultado[2]
                
                if bcrypt.checkpw(senha_digitada.encode('utf-8'), senha_hash_banco):
                    return True, usuario_id, perfil
    except Exception as e:
        st.error(f"O WikiSuporte encontrou um erro durante a autenticação: {e}")
    
    return False, None, None

def verificar_aceite_termos(usuario_id):
    engine = get_connection()
    try:
        with engine.connect() as conn:
            query = text("SELECT 1 FROM logs_auditoria_sistema WHERE usuario_id = :u AND acao = 'ACEITE_TERMOS' LIMIT 1")
            resultado = conn.execute(query, {"u": usuario_id}).fetchone()
            return bool(resultado)
    except Exception as e:
        return False

def exibir_termos_uso():
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    st.title("WikiSuporte - Termo de Uso e Confidencialidade")
    st.warning("**Atenção:** Este é um ambiente restrito e protegido. O acesso e uso deste sistema estão sujeitos a termos de uso e de confidencialidade e proteção de dados. Leia atentamente antes de prosseguir.")
    
    st.markdown("""
    ### 📜 Termo de Uso e Confidencialidade de Dados (LGPD)
    Este sistema processa dados pessoais e informações estratégicas protegidas pela **Lei Geral de Proteção de Dados (Lei nº 13.709/2018)**.
    Ao acessar o WikiSuporte, você assume o compromisso de sigilo e responsabilidade conforme as cláusulas abaixo:
    
    **1. Confidencialidade e Proteção de Dados**
    Os dados exibidos (nomes de clientes, telefones, históricos de chamados e mensagens) são estritamente confidenciais.
    É **terminantemente proibido**:
    * Compartilhar capturas de tela (prints), relatórios ou credenciais com terceiros não autorizados.
    * Utilizar os dados para fins pessoais ou alheios à operação de suporte técnico.
    * Armazenar exportações de dados em dispositivos pessoais ou nuvens públicas não homologadas.
    
    **2. Monitoramento e Auditoria**
    Para fins de segurança e compliance, **todas as ações realizadas neste sistema são registradas em logs de auditoria.**.
    Isso inclui, mas não se limita a: acessos, visualizações de dados, exportações, alterações de configurações e tentativas de acesso.

    **3. Responsabilidade**
    O acesso e uso deste sistema são de responsabilidade exclusiva do usuário autenticado. E o mesmo se compromete a cumprir integralmente este termo.
    """)
    
    aceito = st.checkbox("Eu li e concordo com os termos de uso e confidencialidade acima.")
    
    if st.button("Confirmar Acesso"):
        if aceito:
            st.session_state['termos_aceitos'] = True
            registrar_log_auditoria(st.session_state.get('usuario_id', 0), "ACEITE_TERMOS", "Usuário aceitou os termos.")
            st.rerun() 
        else:
            st.error("Você deve aceitar os termos para utilizar o WikiSuporte.")

# ==========================================
# 4. BARREIRA DE ACESSO (LOGIN E TIMEOUT)
# ==========================================
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False

if st.session_state['autenticado']:
    agora = datetime.now()
    ultimo_acesso = st.session_state.get('ultimo_acesso', agora)
    if agora - ultimo_acesso > timedelta(minutes=15):
        st.session_state.clear() 
        st.warning("⏱️ Sua sessão expirou por inatividade (15 minutos). Faça login novamente.")
        st.stop()
    else:
        st.session_state['ultimo_acesso'] = agora

if not st.session_state['autenticado']:
    st.markdown("""<style>[data-testid="stSidebarNav"] {display: none;}</style>""", unsafe_allow_html=True)

    with st.sidebar:
        try: st.image("mascote/psy_braco_cruzado_aposto.png", use_container_width=True)
        except: pass
        
        st.markdown("## 👋 Olá! Bem-vindo(a) ao WikiSuporte")
        st.info("**Versão 1.0.0** (Beta)")
        
        st.markdown("### 🤖 O que é o WikiSuporte?")
        st.markdown("O WikiSuporte é um dashboard de suporte técnico desenvolvido para centralizar, analisar e proteger os dados dos atendimentos. Ele automatiza a coleta de dados, oferece visualizações avançadas e garante a segurança e conformidade com a LGPD.")
        
        frases = ["A persistência realiza o impossível.", "Falar é barato. Mostre-me o código."]
        st.info(f"💡 ** Pensamento do dia:**\n\n_{random.choice(frases)}_")
        st.divider()
        st.caption("WikiSuporte — Sistema desenvolvido por Rafael D. Nascimento. © 2026. Todos os direitos reservados.")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>Acesso ao WikiSuporte</h2>", unsafe_allow_html=True)
        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite seu nome de usuário")
            senha = st.text_input("Senha", type="password")
            btn_login = st.form_submit_button("Entrar no WikiSuporte", use_container_width=True)
            
        if btn_login:
            sucesso, user_id, user_perfil = verificar_login(usuario, senha)
            if sucesso:
                st.session_state['autenticado'] = True
                st.session_state['usuario_id'] = user_id
                st.session_state['perfil'] = user_perfil 
                st.session_state['termos_aceitos'] = verificar_aceite_termos(user_id)
                st.session_state['ultimo_acesso'] = datetime.now() 
                registrar_log_auditoria(user_id, "LOGIN", "Login realizado com sucesso.")
                st.rerun() 
            else:
                st.error("Usuário inativo ou senha incorreta.")
    st.stop()

if not st.session_state.get('termos_aceitos'):
    exibir_termos_uso()
    st.stop() 

# ==========================================
# 4.1 FUNÇÃO AUXILIAR PARA LER LOGS DO ROBÔ (OPCIONAL)
# ==========================================



def ler_logs_robo(caminho_arquivo="oraculo_engine.log", ultimas_linhas=50):
    """Lê as últimas linhas do ficheiro de log gerado pelo robô invisível."""
    if not os.path.exists(caminho_arquivo):
        return "Nenhum registo encontrado. O robô ainda não foi executado ou o ficheiro não existe."
    try:
        # A CIRURGIA: Adicionamos errors="replace" para evitar o travamento com acentos e cedilhas
        with open(caminho_arquivo, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()
            return "".join(linhas[-ultimas_linhas:])
    except Exception as e:
        return f"Erro ao tentar ler o ficheiro de logs: {e}"

# ==========================================
# 5. CAMADA DE DADOS COM CACHE
# ==========================================
@st.cache_data(ttl=300) 
def carregar_fila_tecnuv():
    engine = get_connection()
    query = """
        SELECT 
            nr_chamado AS "Chamado",
            cliente_nome AS "Cliente",
            atendente_tecnuv AS "Atendente",
            status_atual AS "Status",
            assunto_html AS "Assunto",
            motivo_abertura_html AS "Motivo",
            ultima_alteracao_tecnuv AS "Última Interação (Tecnuv)"
        FROM chamados_tecnuv
        ORDER BY ultima_alteracao_tecnuv DESC NULLS LAST
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
            for col in ["Assunto", "Motivo"]:
                if col in df.columns:
                    df[col] = df[col].str.replace(r'<br\s*/?>', ' ', regex=True)
                    df[col] = df[col].str.replace(r'<[^>]+>', '', regex=True)
                    df[col] = df[col].str.replace(r'\s+', ' ', regex=True).str.strip()

            if "Última Interação (Tecnuv)" in df.columns:
                df["Última Interação (Tecnuv)"] = pd.to_datetime(df["Última Interação (Tecnuv)"])
            return df
    except Exception as e:
        st.error(f"Erro ao ligar à base de dados: {e}")
        return pd.DataFrame()

# ==========================================
# 6. SIDEBAR DEFINITIVA (NOVO LAYOUT)
# ==========================================
nome_usuario = st.session_state.get('usuario_nome', 'Usuário')
perfil_usuario = st.session_state.get('perfil', 'analista de suporte').lower()

try: st.sidebar.image("mascote/psy_braco_cruzado_aposto.png", width=120)
except Exception: pass

st.sidebar.markdown(f"### Olá, {nome_usuario}!")
st.sidebar.caption(f"🛡️ Perfil: {perfil_usuario.title()}")
st.sidebar.divider()

opcoes_menu_principal = [
    "Home", 
    "Configurações", 
    "Importar arquivos de atendimentos (GoTo | Multi360)", 
    "Privacidade", 
    "Sobre"
]
menu_principal = st.sidebar.radio("Navegação Principal", opcoes_menu_principal)

submenu_escolhido = None
if menu_principal == "Configurações":
    st.sidebar.markdown("---")
    opcoes_disponiveis = obter_opcoes_por_perfil(perfil_usuario)
    submenu_escolhido = st.sidebar.selectbox("Opções de Configuração:", opcoes_disponiveis)

st.sidebar.divider()
if st.sidebar.button("🚪 Sair", use_container_width=True):
    registrar_log_auditoria(st.session_state.get('usuario_id'), "LOGOUT", "Usuário encerrou a sessão.")
    st.session_state.clear()
    st.rerun()

# ==========================================
# 7. ROTEAMENTO DAS TELAS
# ==========================================
col_logo, col_titulo = st.columns([1, 11])
with col_logo:
    try: st.image("mascote/psy_notebook.png", width=70)
    except: pass
with col_titulo:
    st.title("WikiSuporte - Dashboard de Suporte Técnico")
    st.markdown("Tudo sobre o suporte em um único lugar!")

if menu_principal == "Home":
    st.write(f"Bem-vindo(a) ao WikiSuporte, {nome_usuario}! Use o menu lateral para navegar pelas funcionalidades disponíveis. Seu perfil de acesso é: **{perfil_usuario.title()}**.")

elif menu_principal == "Importar arquivos de atendimentos (GoTo | Multi360)":
    st.header("Gestão de Dados e CRM")
    aba_importacao, aba_crm = st.tabs(["📂 Importar arquivos de atendimentos do suporte", "🔗 Cadastro de CRM"])
    
    with aba_importacao:
        st.markdown("Faça o upload dos arquivos de atendimentos do suporte, e deixe o WikiSuporte fazer a mágica e transformar os dados para você!")
        origem_dados = st.radio("Selecione a origem dos dados:", ("GoTo (Central)", "Multi360 (WhatsApp)"), horizontal=True)
        
        # O file_uploader agora aceita excel graças à nossa última alteração!
        arquivo_upload = st.file_uploader("Selecione um arquivo de atendimentos:", type=["csv", "xlsx"])
        
        if arquivo_upload is not None:
            try:
                # 1. Barra de Progresso da Leitura (ETL)
                barra_leitura = st.progress(10, text="Analisando o arquivo e transformando os dados...")
                
                if origem_dados == "GoTo (Telefonia)":
                    df_processado = processar_csv_goto(arquivo_upload)
                    nome_tabela_destino = "atendimentos_goto"
                else:
                    df_processado = processar_csv_multi360(arquivo_upload)
                    nome_tabela_destino = "atendimentos_multi360"
                
                barra_leitura.progress(100, text=f"✅ Analisando os dados, encontramos {len(df_processado)} registros.")
                
                st.write("Tratamento dos dados concluído! Aqui estão as primeiras linhas do arquivo processado:")
                st.dataframe(df_processado.head(5), use_container_width=True)
                
                # Funções de Upsert alinhadas corretamente
                def postgres_upsert_goto(table, conn, keys, data_iter):
                    data = [dict(zip(keys, row)) for row in data_iter]
                    insert_stmt = insert(table.table).values(data)
                    upsert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=['id_conversa'])
                    conn.execute(upsert_stmt)

                def postgres_upsert_multi360(table, conn, keys, data_iter):
                    data = [dict(zip(keys, row)) for row in data_iter]
                    insert_stmt = insert(table.table).values(data)
                    colunas_atualizacao = {c.name: c for c in insert_stmt.excluded if c.name != 'protocolo'}
                    upsert_stmt = insert_stmt.on_conflict_do_update(
                        index_elements=['protocolo'], set_=colunas_atualizacao
                    )
                    conn.execute(upsert_stmt)

                st.warning("O WikiSuporte irá iniciar a gravação dos dados na base de dados. Este processo pode levar alguns minutos dependendo do tamanho do arquivo. Por favor, aguarde e não feche a janela.")
                
                if st.button("Salvar arquivo", type="primary"):
                    # 2. Barra de Progresso Real da Base de Dados
                    barra_gravacao = st.progress(0, text="Preparando para gravar os dados no banco de dados...")
                    
                    try:
                        engine = get_connection()
                        metodo_upsert = postgres_upsert_goto if origem_dados == "GoTo (Telefonia)" else postgres_upsert_multi360
                        
                        total_linhas = len(df_processado)
                        tamanho_lote = 1000  # Grava de 1000 em 1000 para não travar
                        
                        # Loop de divisão em lotes (Chunks) para atualizar a barra em tempo real
                        for start_idx in range(0, total_linhas, tamanho_lote):
                            end_idx = min(start_idx + tamanho_lote, total_linhas)
                            lote_atual = df_processado.iloc[start_idx:end_idx]
                            
                            # Calcula a percentagem e atualiza a interface
                            percentagem = int((end_idx / total_linhas) * 100)
                            texto_status = f"Inserindo dados do arquivo: {end_idx} de {total_linhas} registos processados ({percentagem}%)..."
                            barra_gravacao.progress(percentagem, text=texto_status)
                            
                            # Grava apenas o lote atual
                            lote_atual.to_sql(
                                name=nome_tabela_destino, 
                                con=engine, 
                                if_exists='append',
                                index=False, 
                                method=metodo_upsert
                            )
                        
                        # Conclusão e Celebração Visual
                        registrar_log_auditoria(st.session_state.get('usuario_id'), "UPSERT_CSV", f"Processou {total_linhas} registos.")
                        barra_gravacao.progress(100, text="Gravando os dados no banco de dados...")
                        # Efeito visual moderno de sucesso do Streamlit
                        st.balloons()
                        st.success(f"✅ O WikiSuporte processou e gravou registos seu arquivo com sucesso! 🎉")
                        
                        
                    except Exception as e:
                        barra_gravacao.empty() # Remove a barra se der erro
                        st.error(f"❌ O WikiSporte encontrou um erro durante a gravação dos dados: {e}")
            except Exception as e:
                st.error(f"❌ O WikiSuporte encontrou um erro durante o processamento dos dados: {e}")

    with aba_crm:
        tela_vinculacao_crm()

elif menu_principal == "Configurações":
    if submenu_escolhido:
        st.subheader(submenu_escolhido)
        
        # O Dashboard de Chamados original foi reaproveitado e mapeado para a Opção 5
        if submenu_escolhido == MENU_CONFIGURACOES[5]:
            df_chamados = carregar_fila_tecnuv()
            if not df_chamados.empty:
                st.divider()

                col_filtro1, col_filtro2 = st.columns(2)
                status_unicos = df_chamados['Status'].dropna().unique().tolist()
                filtro_status = col_filtro1.multiselect("Filtrar por Status:", options=status_unicos, default=status_unicos)
                
                clientes_unicos = df_chamados['Cliente'].dropna().unique().tolist()
                filtro_cliente = col_filtro2.multiselect("Filtrar por Cliente (Opcional):", options=clientes_unicos)
                
                df_filtrado = df_chamados[df_chamados['Status'].isin(filtro_status)]
                if filtro_cliente: 
                    df_filtrado = df_filtrado[df_filtrado['Cliente'].isin(filtro_cliente)]

                st.divider()
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total de Chamados", len(df_filtrado))
                col2.metric("Em Desenvolvimento", len(df_filtrado[df_filtrado['Status'].str.contains('Desenvolvimento', case=False, na=False)]))
                col3.metric("Pendentes", len(df_filtrado[df_filtrado['Status'].str.contains('Pendente', case=False, na=False)]))
                col4.metric("Sem Atendente", len(df_filtrado[df_filtrado['Atendente'] == 'Não Atribuído']))

                st.divider()
                graf_col1, graf_col2 = st.columns(2)
                with graf_col1:
                    df_status_count = df_filtrado['Status'].value_counts().reset_index()
                    df_status_count.columns = ['Status', 'Quantidade']
                    fig_status = px.bar(df_status_count, x='Quantidade', y='Status', orientation='h', title="Volume por Status", color='Quantidade', color_continuous_scale='Blues')
                    fig_status.update_layout(showlegend=False, xaxis_title="", yaxis_title="")
                    st.plotly_chart(fig_status, use_container_width=True)

                with graf_col2:
                    df_clientes_count = df_filtrado['Cliente'].value_counts().head(10).reset_index()
                    df_clientes_count.columns = ['Cliente', 'Quantidade']
                    fig_clientes = px.pie(df_clientes_count, names='Cliente', values='Quantidade', hole=0.4, title="Top 10 Clientes")
                    fig_clientes.update_traces(textposition='inside', textinfo='percent+value')
                    st.plotly_chart(fig_clientes, use_container_width=True)

                st.divider()
                df_exibicao = df_filtrado.copy()
                df_exibicao["Última Interação (Tecnuv)"] = df_exibicao["Última Interação (Tecnuv)"].dt.strftime('%d/%m/%Y %H:%M')
                st.dataframe(df_exibicao, use_container_width=True, hide_index=True, height=400)
                
                if perfil_usuario == "superadmin":
                    if st.button("Atualizar Dados (Limpar Cache)"):
                        st.cache_data.clear()
                        st.rerun()

        # ==========================================
        # OPÇÃO 13: PAINEL DE CONTROLO DO ROBÔ
        # ==========================================
        elif submenu_escolhido == MENU_CONFIGURACOES[13]:
          
            
            st.header("🤖 Painel de Controlo do Robô WikiSuporte")
            st.markdown("Configure a varredura invisível no Helpdesk (Tecnuv) e monitore os logs.")
            
            # 1. Configuração Visual
            col_tempo, col_status = st.columns(2)
            with col_tempo:
                intervalo_minutos = st.number_input("Frequência da Varredura Automática (em minutos):", min_value=1, max_value=1440, value=15, step=1)
            
            with col_status:
                st.write("Status do Motor Automático:")
                robo_ativo = st.toggle("Ativar Varredura em Segundo Plano", value=False)
                if robo_ativo:
                    st.success(f"✅ Robô ativado! Próxima varredura em {intervalo_minutos} minutos.")
                else:
                    st.warning("⏸️ Motor automático pausado.")
            
            st.divider()
            
            # 2. Execução Manual do Robô Invisível
            st.subheader("Disparo Manual (Modo Invisível)")
            st.write("Dispare a varredura agora para forçar a sincronização imediata.")
            
            if st.button("🚀 Iniciar Varredura Manual Agora", type="primary"):
                with st.status("A inicializar o Robô WikiSuporte...", expanded=True) as status_robo:
                    st.write("👻 O robô invisível está a trabalhar em background...")
                    
                    try:
                        robo = OraculoBot()
                        if robo.login():
                            st.write("✅ Login bem sucedido no Tecnuv. A configurar filtros...")
                            if robo.configurar_filtros():
                                st.write("🔍 A varrer a tabela de chamados...")
                                robo.varrer_tabela()
                                
                                st.write("🔄 A verificar falhas de raspagem (Auto-cura)...")
                                robo.recuperar_falhas_raspagem()
                                
                                status_robo.update(label="Varredura concluída com sucesso!", state="complete", expanded=False)
                                st.success("🎉 O Robô finalizou a varredura no Tecnuv de forma invisível!")
                                registrar_log_auditoria(st.session_state.get('usuario_id'), "ROBO_SUCESSO", "Varredura manual executada sem erros.")
                            else:
                                status_robo.update(label="Falha ao configurar filtros.", state="error", expanded=True)
                        else:
                            status_robo.update(label="Falha na autenticação do Tecnuv.", state="error", expanded=True)
                            
                    except Exception as e:
                        status_robo.update(label="Erro crítico durante a execução!", state="error", expanded=True)
                        st.error(f"Erro capturado: {e}")
            
            st.divider()
            
            # 3. Terminal de Logs Virtual
            st.subheader("📜 Monitor de Logs (Terminal Virtual)")
            col_titulo_log, col_botao_log = st.columns([4, 1])
            with col_botao_log:
                if st.button("🔄 Atualizar Logs", use_container_width=True):
                    st.rerun()
            
            # Chama a função que lê o ficheiro oraculo_engine.log
            texto_logs = ler_logs_robo(ultimas_linhas=50)
            st.code(texto_logs, language="bash")
            st.caption("Ficheiro: `oraculo_engine.log`")

        # ==========================================
        # RESTANTE DO MENU DE CONFIGURAÇÕES
        # ==========================================
        else:
            st.info("Funcionalidade em desenvolvimento pelo WikiSuporte.")

elif menu_principal == "Privacidade":
    st.title("🔒 Privacidade e LGPD")
    st.write("Todos os dados sensíveis (como telefones e CNPJs) são anonimizados no banco de dados através de algoritmos de Hashing (SHA-256). O WikiSuporte protege os dados de ponta a ponta.")

elif menu_principal == "Sobre":
    st.title("ℹ️ Sobre o Sistema")
    st.write("WikiSuporte - Versão 1.0. Desenvolvido para gestão avançada e BI do suporte técnico.")