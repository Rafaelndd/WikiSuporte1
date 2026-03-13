import os
import streamlit as st
import pandas as pd
import re
import io
import datetime
import os
from sqlalchemy import text
from modules.database import get_connection
from modules.processador_csv import gerar_hash_lgpd
from dotenv import load_dotenv
from services.auth_guard import require_profile

load_dotenv()

# Importa as suas funções de LGPD e limpeza
from modules.processador_csv import processar_csv_goto, processar_csv_multi360, ler_arquivo_dinamico

# Importa o módulo de integração com a API do GoTo Connect
try:
    import goto_api
    GOTO_API_DISPONIVEL = True
except ImportError:
    goto_api = None
    GOTO_API_DISPONIVEL = False

try:
    from modules.auditoria import registrar_log_auditoria
except Exception:
    def registrar_log_auditoria(*args):  # type: ignore[override]
        pass

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="WikiSuporte", page_icon="📊", layout="wide")

# Exige login e restringe aos perfis dev / coordenador
perfil_usuario = require_profile(
    ["dev", "coordenador"],
    titulo_bloqueio="⛔ Acesso Negado: Você não tem permissão para acessar esta página.",
)

usuario_id = st.session_state.get("usuario_id")
nome_usuario = str(st.session_state.get("usuario_nome", "Sistema"))

# ==========================================
# 2. FUNÇÕES AUXILIARES DE BANCO DE DADOS E REGRAS
# ==========================================
def salvar_no_banco(df, nome_tabela, tipo_arquivo):
    engine = get_connection()
    try:
        with engine.begin() as conn:
            if tipo_arquivo == "GOTO":
                data_min = df['data_chamada'].min()
                data_max = df['data_chamada'].max()
                query_delete = text("DELETE FROM atendimentos_goto WHERE data_chamada >= :dmin AND data_chamada <= :dmax")
                conn.execute(query_delete, {"dmin": data_min, "dmax": data_max})
                
            elif tipo_arquivo == "MULTI360":
                lista_protocolos = df['protocolo'].dropna().tolist()
                if lista_protocolos:
                    query_delete = text("DELETE FROM atendimentos_multi360 WHERE protocolo = ANY(:ids)")
                    conn.execute(query_delete, {"ids": lista_protocolos})
            
            df.to_sql(nome_tabela, conn, if_exists='append', index=False)
            
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

def apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

# 🌟 REGRA CIRÚRGICA DE PLANTÃO CRUZADO (Ciclos exatos do Regime Normal)
def is_plantao_normal(dt):
    if pd.isnull(dt): return False
    wd = dt.weekday() 
    time_val = dt.time()
    
    # 5=Sábado, 6=Domingo: Integral (Contínuo)
    if wd in [5, 6]: 
        return True
        
    # 0=Segunda-feira: Plantão do FDS encerra às 07:00. O novo começa às 18:20.
    if wd == 0: 
        if time_val <= datetime.time(7, 0): return True
        if time_val >= datetime.time(18, 20): return True
        return False
        
    # 1=Terça a 4=Sexta: O da madrugada encerra 07:30. O novo começa 18:20.
    if wd in [1, 2, 3, 4]: 
        if time_val <= datetime.time(7, 30): return True
        if time_val >= datetime.time(18, 20): return True
        return False

# ==========================================
# 3. INTERFACE DE USUÁRIO (UX) - ABAS
# ==========================================
st.title("📁 Importação e Exportação de Relatórios")
st.markdown("Importe seus relatórios de atendimento do GoTo Connect e Multi360 para alimentar os dashboards do WikiSuporte! Siga as instruções abaixo para garantir que seus dados sejam processados corretamente.")
with st.expander("🤔 Como usar esta página?"):
    st.markdown(
        "**API GoTo:** conecta direto na nuvem (precisa de credenciais no `.env`). "
        "**Importar mensal:** envie o CSV/XLSX exportado do GoTo ou Multi360. "
        "**Plantões:** encaminhe o arquivo do plantão, e o sistema identifica automaticamente quais chamadas pertencem ao plantão com base na data/hora. "
        "Após importar, use **Salvar**; se aparecer cadastro de números sem cliente, preencha para melhorar os dashboards."
    )

aba1, aba2, aba3 = st.tabs([
    "🔌 Buscar via API GoTo",
    "📥 Importar Mensal / Relatórios",
    "📥 Extrator de Plantões Diário",
])

# ------------------------------------------
# ABA 1: INTEGRAÇÃO COM A API DO GOTO (PLANO PRINCIPAL)
# ------------------------------------------
with aba1:
    st.markdown("### 🔌 Buscar Atendimentos Diretamente da API GoTo Connect")
    st.success(
        "🚀 **Integração WikiSuporte e GoTo**\n"
        
        "Caso a API esteja indisponível, utilize a aba **📥 Importar Mensal** como Plano B."
    )

    if not GOTO_API_DISPONIVEL:
        st.error("❌ Módulo `goto_api` não encontrado. Certifique-se de que o arquivo `goto_api.py` está na raiz do projeto.")
        st.stop()

    # Verifica se as credenciais estão configuradas
    cid_env = os.getenv("GOTO_CLIENT_ID", "")
    csecret_env = os.getenv("GOTO_CLIENT_SECRET", "")
    credenciais_configuradas = bool(cid_env and csecret_env)

    with st.container(border=True):
        st.markdown("#### 🔑 Credenciais da API GoTo")
        if credenciais_configuradas:
            st.success("✅ Credenciais validadas com sucesso.")
            usar_env = st.checkbox("Usar as credenciais configuradas no sistema.", value=True, key="goto_usar_env")
        else:
            st.warning(
                "⚠️ Variáveis `GOTO_CLIENT_ID` e `GOTO_CLIENT_SECRET` não encontradas no `.env`. "
                "Preencha abaixo para continuar."
            )
            usar_env = False

        if not (credenciais_configuradas and usar_env):
            col_cid, col_csecret = st.columns(2)
            with col_cid:
                client_id_input = st.text_input("Client ID (GoTo):", type="default", key="goto_client_id_input")
            with col_csecret:
                client_secret_input = st.text_input("Client Secret / Senha:", type="password", key="goto_client_secret_input")
            client_id_final = client_id_input.strip() or cid_env
            client_secret_final = client_secret_input.strip() or csecret_env
        else:
            client_id_final = cid_env
            client_secret_final = csecret_env

    # Botão de teste de conectividade
    col_test, _ = st.columns([1, 3])
    with col_test:
        if st.button("🔍 Testar Conexão com a API", key="goto_testar_conexao"):
            with st.spinner("Testando conectividade com a API do GoTo..."):
                ok, msg = goto_api.verificar_conectividade(client_id_final, client_secret_final)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.divider()

    with st.container(border=True):
        st.markdown("#### 📅 Período de Busca")
        col_di, col_df = st.columns(2)
        with col_di:
            data_ini_api = st.date_input(
                "Data de Início:",
                value=datetime.date.today().replace(day=1),
                key="goto_data_inicio",
            )
            hora_ini_api = st.time_input("Hora de Início:", value=datetime.time(0, 0), key="goto_hora_inicio")
        with col_df:
            data_fim_api = st.date_input(
                "Data de Fim:",
                value=datetime.date.today(),
                key="goto_data_fim",
            )
            hora_fim_api = st.time_input("Hora de Fim:", value=datetime.time(23, 59), key="goto_hora_fim")

        dt_inicio_api = datetime.datetime.combine(data_ini_api, hora_ini_api)
        dt_fim_api = datetime.datetime.combine(data_fim_api, hora_fim_api)

        if dt_inicio_api >= dt_fim_api:
            st.error("⚠️ A data de início deve ser anterior à data de fim.")

    # Botão principal de busca
    if st.button("📡 Buscar Chamadas via API GoTo", type="primary", key="goto_buscar", disabled=(dt_inicio_api >= dt_fim_api)):
        if not client_id_final or not client_secret_final:
            st.error("❌ Informe as credenciais GoTo antes de buscar.")
        else:
            barra_progresso = st.progress(0, text="Iniciando busca na API do GoTo...")
            status_container = st.empty()

            def atualizar_progresso(pagina, total):
                msg = f"🔄 Carregando página {pagina}... ({total} registros no total)"
                barra_progresso.progress(min(pagina * 10, 95), text=msg)
                status_container.caption(msg)

            try:
                with st.spinner("Autenticando e buscando chamadas..."):
                    df_api = goto_api.buscar_atendimentos_goto(
                        data_inicio=dt_inicio_api,
                        data_fim=dt_fim_api,
                        client_id=client_id_final,
                        client_secret=client_secret_final,
                        callback_progresso=atualizar_progresso,
                    )

                barra_progresso.progress(100, text="✅ Busca concluída!")
                status_container.empty()

                if df_api.empty:
                    st.warning("⚠️ Nenhuma chamada encontrada para o período informado.")
                else:
                    st.success(f"🎯 **{len(df_api)} chamadas** encontradas para o período selecionado!")
                    st.session_state['df_goto_api'] = df_api

            except (ValueError, ConnectionError) as e:
                barra_progresso.empty()
                status_container.empty()
                st.error(f"❌ Erro ao buscar dados da API GoTo: {e}")
            except Exception as e:
                barra_progresso.empty()
                status_container.empty()
                st.error(f"❌ Erro inesperado: {e}")

    # Exibe e permite salvar os dados buscados via API
    df_goto_api = st.session_state.get('df_goto_api', pd.DataFrame())
    if not df_goto_api.empty:
        st.divider()
        st.markdown("#### 🔍 Pré-visualização dos Dados Obtidos via API")

        # Cruzamento com CRM (mesmo pipeline do upload manual)
        with st.spinner("🔄 Cruzando telefones com o banco de dados do CRM..."):
            try:
                engine = get_connection()
                with engine.connect() as conn:
                    df_crm = pd.read_sql(text("""
                        SELECT c.razao_social, t.numero as telefone_bd 
                        FROM clientes_telefones t
                        JOIN clientes_crm c ON t.id_cliente = c.id_cliente
                        WHERE t.numero IS NOT NULL AND t.numero != ''
                    """), conn)
                mapa_clientes = dict(zip(df_crm['telefone_bd'], df_crm['razao_social']))

                def extrair_numero_cliente_api(row):
                    if str(row.get('direcao', '')).upper() == 'RECEBIDA':
                        return re.sub(r'\D', '', str(row.get('telefone_origem', '')))
                    else:
                        nums = re.findall(r'\+55\d+', str(row.get('participantes', '')))
                        if nums:
                            return re.sub(r'\D', '', nums[0])
                        return re.sub(r'\D', '', str(row.get('telefone_origem', '')))

                numeros_api = df_goto_api.apply(extrair_numero_cliente_api, axis=1)
                df_goto_api['cliente_nome'] = numeros_api.map(mapa_clientes).fillna("Não Identificado")
                sucesso_crm_api = len(df_goto_api[df_goto_api['cliente_nome'] != "Não Identificado"])
                st.success(f"🎯 **{sucesso_crm_api} chamadas** vinculadas a clientes do CRM!")
                st.session_state['df_goto_api'] = df_goto_api
            except Exception as e:
                st.warning(f"⚠️ Cruzamento com cadastro dos clientes falhou: {e}")
                df_goto_api['cliente_nome'] = "Não Identificado"

        with st.container(border=True):
            st.dataframe(df_goto_api.head(10), use_container_width='stretch')

        with st.container(border=True):
            st.markdown("#### 📊 Resumo")
            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Total de Chamadas", len(df_goto_api))
            data_min_api = df_goto_api['data_chamada'].min()
            data_max_api = df_goto_api['data_chamada'].max()
            if pd.notna(data_min_api):
                col_r2.metric("Data Inicial", pd.to_datetime(data_min_api).strftime('%d/%m/%Y'))
            if pd.notna(data_max_api):
                col_r3.metric("Data Final", pd.to_datetime(data_max_api).strftime('%d/%m/%Y'))

        if st.button("💾 Salvar no Banco de Dados", type="primary", key="goto_salvar_api", use_container_width='stretch'):
            with st.spinner("Gravando dados no WikiSuporte..."):
                sucesso, msg = salvar_no_banco(df_goto_api, "atendimentos_goto", "GOTO")
                if sucesso:
                    st.success(f"✅ {len(df_goto_api)} registros salvos com sucesso!")
                    registrar_log_auditoria(usuario_id, "IMPORT_API_GOTO", f"Importado via API GoTo: {len(df_goto_api)} registros")
                    del st.session_state['df_goto_api']
                else:
                    st.error(f"❌ Erro ao salvar: {msg}")

# ------------------------------------------
# ABA 2: IMPORTAÇÃO DE ARQUIVOS (MENSAL) — PLANO B
# ------------------------------------------
with aba2:
    st.warning(
        "📋 **Upload Manual:** Use esta aba quando a API do GoTo estiver indisponível. "
        "Exporte o arquivo CSV/XLSX diretamente pelo portal GoTo e importe aqui."
    )
    st.info("💡 **Dica:** O sistema cruza os telefones com o CRM automaticamente para identificar o nome do cliente no Dashboard!")
    with st.container(border=True):
        arquivo_upload = st.file_uploader("📂 Selecione o seu arquivo de atendimento:", type=['csv', 'xlsx'], key="up_import_mensal")
    
    if arquivo_upload:
        df_preview = ler_arquivo_dinamico(arquivo_upload)
        tipo_identificado, df_processado, erro_processamento = None, None, None
        
        is_goto_conversations = 'Conversation space id' in df_preview.columns
        is_goto_user_activity = 'Queue Name' in df_preview.columns and 'Start Time (local)' in df_preview.columns
        is_multi360 = 'PROTOCOLO' in df_preview.columns
        
        if is_goto_conversations: 
            tipo_identificado = "GOTO"
        elif is_multi360: 
            tipo_identificado = "MULTI360"
        elif is_goto_user_activity:
            st.error("❌ O arquivo 'User Activity' do GoTo é utilizado para fatiar plantão. Por favor, utilize a Aba **Extrator de Plantões Diário'** para esse arquivo.")
            st.stop()
        else: 
            st.error("❌ Arquivo não reconhecido.")
            st.stop()
            
        with st.spinner(f"🔍 Processando arquivo do {tipo_identificado}..."):
            try:
                arquivo_upload.seek(0) 
                if tipo_identificado == "GOTO":
                    df_processado = processar_csv_goto(arquivo_upload)
                    nome_tabela_bd = "atendimentos_goto"
                else:
                    df_processado = processar_csv_multi360(arquivo_upload)
                    nome_tabela_bd = "atendimentos_multi360"
            except Exception as e: erro_processamento = str(e)
                
        if erro_processamento: 
            st.error(f"❌ Erro no processamento: {erro_processamento}")
        elif df_processado is not None and not df_processado.empty:
            
            bloqueio_plantao = False
            if tipo_identificado == "GOTO":
                if pd.api.types.is_datetime64_any_dtype(df_processado['data_chamada']):
                    dias_arquivo = (df_processado['data_chamada'].max() - df_processado['data_chamada'].min()).days
                else:
                    dt_temp = pd.to_datetime(df_processado['data_chamada'], errors='coerce')
                    dias_arquivo = (dt_temp.max() - dt_temp.min()).days
                
                if pd.isna(dias_arquivo): dias_arquivo = 0
                
                if dias_arquivo <= 5:
                    st.warning(f"**Aviso:** Este arquivo cobre apenas **{int(dias_arquivo)} dia(s)**. Parece um Relatório de Plantão.")
                    liberar = st.checkbox("Eu confirmo que este é um arquivo MENSAL válido. Desbloquear importação.")
                    if not liberar: bloqueio_plantao = True

            if not bloqueio_plantao:
                if tipo_identificado == "GOTO":
                    with st.spinner("🔄 Cruzando telefones com os cadastros dos clientes..."):
                        try:
                            from services.clientes_service import obter_mapa_hash_cliente
                            mapa_hash = obter_mapa_hash_cliente()
                            df_processado['cliente_nome'] = df_processado['telefone_hash'].map(mapa_hash).fillna("Não Identificado")
                            sucesso_crm = len(df_processado[df_processado['cliente_nome'] != "Não Identificado"])
                            st.success(f"🎯 **Identificação:** {sucesso_crm} chamadas vinculadas a clientes.")
                            # Números sem vínculo para cadastro opcional
                            hashes_sem_vinculo = df_processado[df_processado['cliente_nome'] == "Não Identificado"]['telefone_hash'].dropna().unique().tolist()
                            if hashes_sem_vinculo:
                                df_raw = ler_arquivo_dinamico(arquivo_upload)
                                col_de = df_raw.get('De', pd.Series(dtype=str))
                                numeros_raw = col_de.apply(apenas_numeros)
                                numeros_raw = numeros_raw[numeros_raw.str.len() >= 8]
                                mapa_raw_hash = {gerar_hash_lgpd(str(n)): str(n) for n in numeros_raw.unique() if n}
                                sem_vinculo_raw = [(mapa_raw_hash.get(h, ""), h) for h in hashes_sem_vinculo if mapa_raw_hash.get(h)]
                                st.session_state['import_numero_sem_vinculo'] = sem_vinculo_raw[:50]
                                st.info(f"📋 **{len(sem_vinculo_raw)}** números sem cliente vinculado. Deseja cadastrar antes de salvar?")
                            st.session_state['import_df_processado'] = df_processado.copy()
                            st.session_state['import_nome_tabela'] = nome_tabela_bd
                            st.session_state['import_tipo'] = tipo_identificado
                            st.session_state['import_arquivo_nome'] = arquivo_upload.name
                        except ImportError:
                            df_processado['cliente_nome'] = "Não Identificado"
                        except Exception as e:
                            st.warning(f"⚠️ Erro ao identificar clientes: {e}")
                            df_processado['cliente_nome'] = "Não Identificado"

                if tipo_identificado == "MULTI360":
                    with st.spinner("🔄 Cruzando com CRM..."):
                        try:
                            from services.clientes_service import obter_mapa_hash_cliente
                            mapa_hash = obter_mapa_hash_cliente()
                            df_processado['cliente_nome'] = df_processado['telefone_hash'].map(mapa_hash).fillna("Não Identificado")
                        except Exception:
                            df_processado['cliente_nome'] = df_processado.get('cliente_nome', "Não Identificado")

                # Cadastro one-by-one de números sem vínculo
                nums_sem_vinculo = st.session_state.get('import_numero_sem_vinculo', [])
                if nums_sem_vinculo and tipo_identificado == "GOTO":
                    with st.container(border=True):
                        st.markdown("#### 📞 Cadastrar clientes para números sem vínculo")
                        raw, _ = nums_sem_vinculo[0]
                        mask = f"(**) *****-{raw[-4:]}" if len(raw) >= 4 else "****"
                        st.caption(f"Número {mask} ({len(nums_sem_vinculo)} restantes)")
                        with st.form("form_cadastro_numero"):
                            razao_cad = st.text_input("Razão Social *", key="cad_razao")
                            cnpj_cad = st.text_input("CNPJ", key="cad_cnpj")
                            if st.form_submit_button("Salvar e próximo"):
                                if razao_cad.strip():
                                    try:
                                        from services.clientes_service import vincular_telefone_cliente
                                        ok, msg = vincular_telefone_cliente(razao_cad, raw, cnpj_cad)
                                        if ok:
                                            h = gerar_hash_lgpd(raw)
                                            df_p = st.session_state.get('import_df_processado')
                                            if df_p is not None and 'telefone_hash' in df_p.columns:
                                                df_p.loc[df_p['telefone_hash'] == h, 'cliente_nome'] = razao_cad.strip()
                                                st.session_state['import_df_processado'] = df_p
                                            st.session_state['import_numero_sem_vinculo'] = nums_sem_vinculo[1:]
                                            st.success("Cadastrado!")
                                            st.rerun()
                                        else:
                                            st.error(msg)
                                    except Exception as ex:
                                        st.error(str(ex))
                                else:
                                    st.warning("Informe a Razão Social.")
                        if st.button("Pular cadastro (continuar sem vincular estes)", key="pular_cad"):
                            st.session_state['import_numero_sem_vinculo'] = []
                            st.rerun()

                with st.container(border=True):
                    st.markdown("### 🔍 Pré-visualização dos Dados (Prontos para o Banco)")
                    st.dataframe(df_processado.head(5), width='stretch')
                
                with st.container(border=True):
                    st.markdown("#### 📊 Resumo do Arquivo Mensal")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total de Registros", len(df_processado))
                    if tipo_identificado == "GOTO":
                        col_m2.metric("Data Inicial", df_processado['data_chamada'].min().strftime('%d/%m/%Y'))
                        col_m3.metric("Data Final", df_processado['data_chamada'].max().strftime('%d/%m/%Y'))
                    else:
                        col_m2.metric("Data Inicial", df_processado['data_inicio'].min().strftime('%d/%m/%Y'))
                        col_m3.metric("Data Final", df_processado['data_inicio'].max().strftime('%d/%m/%Y'))
                
                if st.button("💾 Salvar", type="primary", width='stretch'):
                    df_para_salvar = st.session_state.get('import_df_processado', df_processado)
                    with st.spinner("Gravando dados no WikiSuporte..."):
                        sucesso, msg = salvar_no_banco(df_para_salvar, nome_tabela_bd, tipo_identificado)
                        if sucesso:
                            st.success(f"{len(df_para_salvar)} registros foram salvos com sucesso.")
                            registrar_log_auditoria(usuario_id, "IMPORT_CSV", f"Importado {arquivo_upload.name}")
                            for k in ['import_df_processado', 'import_numero_sem_vinculo', 'import_nome_tabela', 'import_tipo', 'import_arquivo_nome']:
                                st.session_state.pop(k, None)
                            st.rerun()
                        else: st.error(f"❌ Erro ao salvar o arquivo: {msg}")

# ------------------------------------------
# ABA 3: ANÁLISE DE PLANTÕES (GOTO)
# ------------------------------------------
with aba3:
    st.subheader("📥 Extrator de Plantões Diário - GoTo")
    st.info("**Faça o upload do arquivo do GoTo**.")
    
    if 'plantao_uploader_key' not in st.session_state:
        st.session_state['plantao_uploader_key'] = 0

    with st.container(border=True):
        arquivo_plantao = st.file_uploader("📂 Envie o arquivo GoTo ('Call Reports' ou 'User Activity'):", type=['csv', 'xlsx'], key=f"up_plantao_{st.session_state['plantao_uploader_key']}")
    
    if arquivo_plantao:
        df_preview_p = ler_arquivo_dinamico(arquivo_plantao)
        
        # 🛡️ Suporte Híbrido: Identifica qual é o formato exportado pelo GoTo
        is_goto_conversations = 'Conversation space id' in df_preview_p.columns
        is_goto_user_activity = 'Queue Name' in df_preview_p.columns and 'Start Time (local)' in df_preview_p.columns
        
        if not (is_goto_conversations or is_goto_user_activity):
            st.error("❌ Arquivo com formato não suportado.")
        else:
            arquivo_plantao.seek(0)
            with st.spinner("Limpando o arquivo..."):
                
                # Trata Arquivo Clássico: Call Reports Conversations
                if is_goto_conversations:
                    df_goto_bruto = processar_csv_goto(arquivo_plantao)
                    if 'Data [America/Sao_Paulo]' in df_goto_bruto.columns:
                        df_goto_bruto['data_chamada'] = pd.to_datetime(df_goto_bruto['Data [America/Sao_Paulo]'], format='mixed', errors='coerce')
                
                # Trata Arquivo Novo: User Activity
                else:
                    df_goto_bruto = ler_arquivo_dinamico(arquivo_plantao)
                    df_goto_bruto['data_chamada'] = pd.to_datetime(df_goto_bruto['Start Time (local)'].astype(str).str.replace(r' GMT-\d{2}:\d{2}', '', regex=True), format='mixed', errors='coerce')
                    df_goto_bruto['data_fim'] = pd.to_datetime(df_goto_bruto['End Time (local)'].astype(str).str.replace(r' GMT-\d{2}:\d{2}', '', regex=True), format='mixed', errors='coerce')
                    df_goto_bruto['duracao_ms'] = pd.to_numeric(df_goto_bruto['Duration'], errors='coerce').fillna(0) * 1000
                    df_goto_bruto['participantes'] = df_goto_bruto['From'].astype(str) + " " + df_goto_bruto['To'].astype(str)
                    df_goto_bruto['telefone_origem'] = df_goto_bruto['From'].astype(str)
                
            if pd.api.types.is_datetime64_any_dtype(df_goto_bruto['data_chamada']):
                dias_arquivo_plantao = (df_goto_bruto['data_chamada'].max() - df_goto_bruto['data_chamada'].min()).days
            else:
                dt_temp = pd.to_datetime(df_goto_bruto['data_chamada'], errors='coerce')
                dias_arquivo_plantao = (dt_temp.max() - dt_temp.min()).days
            
            if pd.isna(dias_arquivo_plantao): dias_arquivo_plantao = 0
            
            if dias_arquivo_plantao > 5:
                st.error(f"🤖 **Psy bloqueou a extração:** \n\nEste arquivo abrange **{int(dias_arquivo_plantao)} dias**. Relatórios de plantão costumam ter no máximo 3 ou 4 dias.\n\n👉 Para o mês todo, use a aba '📥 Importar Mensal'.")
            else:
                df_goto = df_goto_bruto[df_goto_bruto['duracao_ms'].fillna(0) > 0].copy()
                
                if df_goto.empty:
                    st.warning("⚠️ **Aviso:** Todas as chamadas deste arquivo eram perdidas ou abandonadas (Duração 0).")
                else:
                    st.divider()
                    st.markdown("#### ⚙️ Configuração do Regime do Plantão")
                    
                    # 🎯 BOTÃO PARA ESCOLHER OS REGIMES (OS DOIS ESTÃO ATIVOS)
                    regime = st.radio("Selecione o regime a ser operado neste arquivo:", 
                                      ["Normal (Seg-Sex e Fim de Semana Padrão)", "Especial (Feriados Nacionais/Locais ou Escalas Customizadas)"])
                    
                    df_plantao_filtrado = pd.DataFrame()
                    
                    if regime == "Normal (Seg-Sex e Fim de Semana Padrão)":
                        st.caption("Ciclo Automático: Seg a Qui (18:20 às 07:30). FDS Contínuo: Sexta 18:20 até Segunda às 07:00.")
                        mascara = df_goto['data_chamada'].apply(is_plantao_normal)
                        df_plantao_filtrado = df_goto[mascara].sort_values('data_chamada')
                        
                    else:
                        st.warning("Especifique a janela exata de tempo do plantão especial.")
                        c_dt1, c_dt2 = st.columns(2)
                        with c_dt1:
                            d_inicio = st.date_input("Data de Início da Escala")
                            h_inicio = st.time_input("Hora de Início da Escala", value=datetime.time(18, 0))
                        with c_dt2:
                            d_fim = st.date_input("Data de Término da Escala")
                            h_fim = st.time_input("Hora de Término da Escala", value=datetime.time(7, 30))
                        
                        inicio_selecionado = datetime.datetime.combine(d_inicio, h_inicio)
                        fim_selecionado = datetime.datetime.combine(d_fim, h_fim)
                        
                        if inicio_selecionado > fim_selecionado: 
                            st.error("Término não pode ser menor que Início.")
                        else:
                            mascara = (df_goto['data_chamada'] >= inicio_selecionado) & (df_goto['data_chamada'] <= fim_selecionado)
                            df_plantao_filtrado = df_goto[mascara].sort_values('data_chamada')

                    if st.button("🔍 Extrair Atendimentos", type="primary"):
                        st.session_state['df_plantao_filtrado'] = df_plantao_filtrado
                        
                    df_exibicao = st.session_state.get('df_plantao_filtrado', pd.DataFrame())
                    
                    if not df_exibicao.empty:
                        df_temp = pd.DataFrame()
                        df_temp['Data_Real'] = df_exibicao['data_chamada'] 
                        
                        # Se o arquivo já trouxe 'Data_fim' nativa (User Activity), usa ela. Se não (Call Reports), calcula.
                        if 'data_fim' in df_exibicao.columns:
                            df_temp['Data_Fim_Real'] = df_exibicao['data_fim']
                        else:
                            df_temp['Data_Fim_Real'] = df_exibicao['data_chamada'] + pd.to_timedelta(df_exibicao['duracao_ms'].fillna(0), unit='ms')
                            
                        df_temp['Data'] = df_temp['Data_Real'].dt.strftime('%d/%m/%Y')

                        # Arredonda para o minuto mais próximo e exibe apenas HH:MM
                        df_temp['Horário inicio atendimento'] = df_temp['Data_Real'].dt.round('min').dt.strftime('%H:%M')
                        df_temp['Horário fim do atendimento'] = df_temp['Data_Fim_Real'].dt.round('min').dt.strftime('%H:%M')
                        
                        mapa_ramais = {
                            "5335": "RENATO", "5333": "AGNALDO", "5331": "BRUNO", "5340": "EMIL",
                            "5332": "DANIEL", "5344": "MARCELO", "5336": "ADILTON", "5339": "LUIS",
                            "5343": "JOAO", "5341": "GABRIEL", "5338": "RAFAEL NASCIMENTO", "5337": "RAFAEL FREITAS"
                        }

                        # 🛡️ SCANNER MULTI-FORMATOS: Trata os ramais independentemente do arquivo GoTo escolhido
                        def identificar_atendente(row):
                            texto_busca = str(row.get('participantes', '')) + " " + str(row.get('telefone_origem', ''))
                            for ramal, nome in mapa_ramais.items():
                                if ramal in texto_busca: return nome
                                    
                            import re
                            match = re.search(r'(?<!\d)(\d{4}):', texto_busca)
                            if not match: match = re.search(r'\((\d{4})\)', texto_busca)
                            if not match: match = re.search(r'(?<!\d)(\d{4})\s', texto_busca)
                            
                            if match: return f"Ramal {match.group(1)} (Não Cadastrado)"
                            return "Sistema / Sem Ramal"

                        df_temp['Atendente'] = df_exibicao.apply(identificar_atendente, axis=1)
                        df_temp['Total (Minutos)'] = (df_exibicao['duracao_ms'].fillna(0) / 60000).round(2)
                        
                        mascara_validas = ~df_temp['Atendente'].isin(["Sistema / Sem Ramal"])
                        df_limpo = df_temp[mascara_validas].copy()
                        
                        if df_limpo.empty:
                            st.warning("⚠️ Arquivo analisado, mas nenhum atendimento real encontrado. Verifique se o arquivo está correto ou se o regime selecionado é adequado.")
                        else:
                            st.success(f"🎯 ** Foram identificados **{len(df_limpo)} atendimentos válidos**! Salvando no banco...")
                            df_limpo = df_limpo.sort_values(by=['Atendente', 'Data_Real'])
                            
                            # SALVAMENTO AUTOMÁTICO
                            engine = get_connection()
                            try:
                                df_usuarios = pd.read_sql(text("SELECT id, nome FROM usuarios WHERE ativo = TRUE"), engine)
                                mapa_ids_bd = {row['nome'].strip().upper(): (row['id'], row['nome']) for _, row in df_usuarios.iterrows()}
                                inseridos, ignorados = 0, 0
                                
                                with engine.begin() as conn_pl:
                                    for _, row in df_limpo.iterrows():
                                        analista_arquivo = row['Atendente'].strip().upper()
                                        if analista_arquivo in mapa_ids_bd:
                                            id_an, nome_banco = mapa_ids_bd[analista_arquivo]
                                            dt_in, dt_out = row['Data_Real'], row['Data_Fim_Real']
                                            
                                            query_check = text("SELECT id_plantao FROM plantoes_epsy WHERE id_analista_epsy = :id_an AND data_hora_entrada = :dt_in")
                                            existe = conn_pl.execute(query_check, {"id_an": id_an, "dt_in": dt_in}).fetchone()
                                            
                                            if not existe:
                                                query_pl = text("INSERT INTO plantoes_epsy (nome_analista_epsy, id_analista_epsy, data_hora_entrada, data_hora_saida) VALUES (:nome, :id_an, :dt_in, :dt_out)")
                                                conn_pl.execute(query_pl, {"nome": nome_banco, "id_an": id_an, "dt_in": dt_in, "dt_out": dt_out})
                                                inseridos += 1
                                            else: ignorados += 1
                                                
                                if inseridos > 0: st.success(f"✅ **{inseridos}** novas ligações registradas na escala de Plantões!")
                                if ignorados > 0: st.caption(f"🛡️ **{ignorados} ligações** já constavam no banco e foram ignoradas.")
                            except Exception as e: st.error(f"❌ Erro ao salvar: {e}")

                            # 🌟 LAYOUT DE EXPORTAÇÃO TXT SOLICITADO
                            txt_content = "Relatório de Atendimentos - Plantão\n" + "="*60 + "\n\n"
                            
                            lista_dfs_export = []
                            analistas_unicos = df_limpo['Atendente'].unique()
                            
                            # Separa os atendimentos por analista e calcula o total dinâmico de cada um
                            for analista in analistas_unicos:
                                df_grupo = df_limpo[df_limpo['Atendente'] == analista].drop(columns=['Data_Real', 'Data_Fim_Real'])
                                
                                # Mantém a construção do arquivo TXT intacta (que não sofre com o erro do PyArrow)
                                txt_content += f"👤 ATENDENTE: {analista}\n" + "-"*60 + "\n"
                                for _, row in df_grupo.iterrows():
                                    txt_content += f"Data: {row['Data']}   Início: {row['Horário inicio atendimento']}   Fim: {row['Horário fim do atendimento']}   Total (Min): {row['Total (Minutos)']}\n"
                                
                                txt_content += f"\n-> TOTAL DE ATENDIMENTOS ({analista}): {len(df_grupo)}\n" + "="*60 + "\n\n"
                                
                                # Prepara os dados para o Excel e Streamlit (sem o totalizador problemático)
                                lista_dfs_export.append(df_grupo)
                                
                                # ⚠️ CORREÇÃO DA LINHA EM BRANCO: Usamos None em 'Total (Minutos)' para não quebrar a tipagem numérica
                                lista_dfs_export.append(pd.DataFrame([{
                                    'Data': '', 
                                    'Horário inicio atendimento': '', 
                                    'Horário fim do atendimento': '', 
                                    'Atendente': '', 
                                    'Total (Minutos)': None 
                                }]))
                            df_final_export = pd.concat(lista_dfs_export, ignore_index=True).iloc[:-1]
                            
                            with st.container(border=True): st.dataframe(df_final_export, width='stretch', hide_index=True)
                            
                            csv_content = df_final_export.to_csv(index=False, sep=';', decimal=',')
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer: df_final_export.to_excel(writer, index=False, sheet_name='Plantao_Separado')
                            excel_content = output.getvalue()
                            
                            st.markdown("#### 📥 Baixar Relatórios")
                            c_txt, c_xls, c_csv = st.columns(3)
                            nome_arq = f"Plantao{datetime.datetime.now().strftime('%d%m%Y')}"
                            c_txt.download_button("📄 Exportar TXT Formatado", txt_content, f"{nome_arq}.txt", "text/plain", width='stretch')
                            c_xls.download_button("📊 Exportar Excel (.xlsx)", excel_content, f"{nome_arq}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')
                            c_csv.download_button("📑 Exportar CSV", csv_content, f"{nome_arq}.csv", "text/csv", width='stretch')

                            st.divider()
                            
                            if st.button("🧹 Limpar Tela e Enviar Novo Arquivo", width='stretch'):
                                st.session_state['plantao_uploader_key'] += 1
                                if 'df_plantao_filtrado' in st.session_state: del st.session_state['df_plantao_filtrado']
                                st.rerun()
                    
                    elif st.session_state.get('df_plantao_filtrado') is not None and st.session_state['df_plantao_filtrado'].empty:
                        st.info(" O arquivo é válido, mas não ocorreram atendimentos nesse horário de plantão específico.")