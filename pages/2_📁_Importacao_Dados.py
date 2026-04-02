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
from config_ramais import RAMAIS_EXCLUIR, RAMAL_NOME_ESPECIAL
from services.auth_guard import require_profile

load_dotenv()

# Importa as suas funções de LGPD e limpeza
from modules.processador_csv import (
    processar_csv_goto,
    processar_csv_multi360,
    ler_arquivo_dinamico,
    processar_agent_calls_goto,
    extrair_agent_calls_do_zip,
    _is_agent_calls_csv,
)

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
def _garantir_tabela_goto_agent_calls(conn):
    """Cria a tabela goto_agent_calls se não existir (migração sob demanda)."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS goto_agent_calls (
            contact_id VARCHAR(255) PRIMARY KEY,
            queue_name VARCHAR(255),
            contact_creation_time TIMESTAMP WITH TIME ZONE,
            contact_resolution_time TIMESTAMP WITH TIME ZONE,
            time_in_queue_millis BIGINT,
            talk_time_millis BIGINT,
            wrap_time_millis BIGINT,
            handle_time_millis BIGINT,
            contact_resolution VARCHAR(100),
            contact_type VARCHAR(100),
            contact_participant_value VARCHAR(255),
            agent_name VARCHAR(255),
            telefone_hash VARCHAR(256),
            telefone_origem VARCHAR(50),
            data_importacao TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """))


def salvar_no_banco(df, nome_tabela, tipo_arquivo):
    engine = get_connection()
    try:
        with engine.begin() as conn:
            if tipo_arquivo == "GOTO":
                data_min = df['data_chamada'].min()
                data_max = df['data_chamada'].max()
                query_delete = text("DELETE FROM atendimentos_goto WHERE data_chamada >= :dmin AND data_chamada <= :dmax")
                conn.execute(query_delete, {"dmin": data_min, "dmax": data_max})
            elif tipo_arquivo == "GOTO_AGENT_CALLS":
                _garantir_tabela_goto_agent_calls(conn)
                col = "contact_creation_time"
                if col in df.columns and not df[col].isna().all():
                    data_min = df[col].min()
                    data_max = df[col].max()
                    conn.execute(
                        text("DELETE FROM goto_agent_calls WHERE contact_creation_time >= :dmin AND contact_creation_time <= :dmax"),
                        {"dmin": data_min, "dmax": data_max},
                    )
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


def _obter_mapa_ramal_analista():
    """Retorna dicionário ramal -> (id_usuario, nome). Exclui 5355; inclui 5366=Caixa Parado, 5365=Chamador, 5364=Jairo (TEF)."""
    engine = get_connection()
    mapa = {}
    try:
        df_u = pd.read_sql(
            text("SELECT id, nome, ramal FROM usuarios WHERE ramal IS NOT NULL AND TRIM(ramal) <> '' AND ativo = TRUE"),
            engine,
        )
        if not df_u.empty:
            for _, row in df_u.iterrows():
                r = str(row["ramal"]).strip()
                if r not in RAMAIS_EXCLUIR:
                    mapa[r] = (int(row["id"]), str(row["nome"]).strip())
    except Exception:
        pass
    # Ramais especiais (rotulos): 5366 Caixa Parado, 5365 Chamador, 5364 Jairo
    for ramal, nome in RAMAL_NOME_ESPECIAL.items():
        if ramal in RAMAIS_EXCLUIR:
            continue
        r = str(ramal).strip()
        if r not in mapa:
            # Jairo (5364) pode ter id em usuarios; demais (None, nome)
            try:
                df_j = pd.read_sql(text("SELECT id FROM usuarios WHERE UPPER(TRIM(nome)) = :n AND ativo = TRUE"), engine, params={"n": nome.strip().upper()})
                uid = int(df_j.iloc[0]["id"]) if not df_j.empty else None
            except Exception:
                uid = None
            mapa[r] = (uid, nome)
    if not mapa:
        try:
            path_ramais = os.path.join(os.path.dirname(__file__), "..", "ramais_config.json")
            if not os.path.exists(path_ramais):
                path_ramais = "ramais_config.json"
            if os.path.exists(path_ramais):
                import json
                with open(path_ramais, "r", encoding="utf-8") as f:
                    nome_para_ramal = json.load(f)
                df_u = pd.read_sql(text("SELECT id, nome FROM usuarios WHERE ativo = TRUE"), engine)
                mapa_nome_id = {str(row["nome"]).strip().upper(): (int(row["id"]), str(row["nome"]).strip()) for _, row in df_u.iterrows()}
                for nome, ramal in nome_para_ramal.items():
                    r = str(ramal).strip()
                    if r not in RAMAIS_EXCLUIR:
                        mapa[r] = mapa_nome_id.get(str(nome).strip().upper(), (None, str(nome).strip()))
        except Exception:
            pass
    return mapa

# 🌟 REGRA CIRÚRGICA DE PLANTÃO CRUZADO (Ciclos exatos do Regime Normal)
def is_plantao_normal(dt):
    if pd.isnull(dt): return False
    wd = dt.weekday() 
    time_val = dt.time()
    
    # 5=Sábado, 6=Domingo: Integral (Contínuo)
    if wd in [5, 6]: 
        return True
        
    # 0=Segunda-feira: Plantão do FDS encerra às 07:30. O novo começa às 18:20.
    if wd == 0: 
        if time_val <= datetime.time(7, 30): return True
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
        arquivo_upload = st.file_uploader(
            "📂 Selecione o seu arquivo de atendimento (CSV, XLSX ou ZIP com agent-calls):",
            type=['csv', 'xlsx', 'zip'],
            key="up_import_mensal",
        )
    if arquivo_upload:
        tipo_identificado, df_processado, erro_processamento = None, None, None
        if arquivo_upload.name.lower().endswith('.zip'):
            zip_bytes = io.BytesIO(arquivo_upload.read())
            csv_io, nome_zip = extrair_agent_calls_do_zip(zip_bytes)
            if csv_io is None:
                st.error("❌ O ZIP não contém um arquivo 'agent-calls_*.csv'. Exporte o relatório Agent Calls do GoTo ou anexe o CSV diretamente.")
                st.stop()
            st.session_state['import_agent_calls_bytes'] = csv_io.read()
            df_preview = pd.read_csv(io.BytesIO(st.session_state['import_agent_calls_bytes']), nrows=15)
        else:
            if 'import_agent_calls_bytes' in st.session_state:
                del st.session_state['import_agent_calls_bytes']
            df_preview = ler_arquivo_dinamico(arquivo_upload)

        is_goto_conversations = 'Conversation space id' in df_preview.columns
        is_goto_call_report = not is_goto_conversations and any(
            df_preview[col].astype(str).str.contains("Chamada perdida|Encerrada com sucesso|Chamada do plano de discagem", case=False, na=False).any()
            for col in df_preview.columns
        )
        is_goto_user_activity = 'Queue Name' in df_preview.columns and 'Start Time (local)' in df_preview.columns
        is_goto_agent_calls = _is_agent_calls_csv(df_preview)
        is_multi360 = 'PROTOCOLO' in df_preview.columns
        
        if is_goto_conversations or is_goto_call_report: 
            tipo_identificado = "GOTO"
        elif is_goto_agent_calls:
            tipo_identificado = "GOTO_AGENT_CALLS"
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
                if tipo_identificado == "GOTO":
                    arquivo_upload.seek(0)
                    df_processado = processar_csv_goto(arquivo_upload)
                    nome_tabela_bd = "atendimentos_goto"
                elif tipo_identificado == "GOTO_AGENT_CALLS":
                    if "import_agent_calls_bytes" in st.session_state:
                        df_processado = processar_agent_calls_goto(io.BytesIO(st.session_state["import_agent_calls_bytes"]))
                    else:
                        arquivo_upload.seek(0)
                        df_processado = processar_agent_calls_goto(arquivo_upload)
                    nome_tabela_bd = "goto_agent_calls"
                else:
                    arquivo_upload.seek(0)
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
                    # Vincular atendimentos aos ramais dos analistas (nome_analista_epsy, id_analista_epsy)
                    mapa_ramal = _obter_mapa_ramal_analista()
                    if mapa_ramal:
                        def identificar_analista(row):
                            texto = (str(row.get("participantes", "")) + " " + str(row.get("telefone_origem", ""))).strip()
                            for ramal, (uid, nome) in mapa_ramal.items():
                                if ramal and ramal in texto:
                                    return (uid, nome)
                            return (None, None)
                        aplicado = df_processado.apply(identificar_analista, axis=1)
                        df_processado["id_analista_epsy"] = aplicado.apply(lambda x: x[0])
                        df_processado["nome_analista_epsy"] = aplicado.apply(lambda x: x[1])
                    else:
                        df_processado["id_analista_epsy"] = None
                        df_processado["nome_analista_epsy"] = None
                    with st.spinner("🔄 Cruzando telefones com os cadastros dos clientes..."):
                        try:
                            from services.clientes_service import obter_mapa_hash_cliente
                            mapa_hash = obter_mapa_hash_cliente()
                            df_processado["cliente_nome"] = df_processado["telefone_hash"].map(mapa_hash)
                            # Sem cadastro: deixar o número em claro (telefone_origem), sem mensagem de tratamento
                            idx_sem = df_processado["cliente_nome"].isna()
                            df_processado.loc[idx_sem, "cliente_nome"] = df_processado.loc[idx_sem, "telefone_origem"].astype(str).replace("nan", "").replace("<NA>", "")
                            df_processado["cliente_nome"] = df_processado["cliente_nome"].fillna("")
                            st.session_state["import_df_processado"] = df_processado.copy()
                            st.session_state["import_nome_tabela"] = nome_tabela_bd
                            st.session_state["import_tipo"] = tipo_identificado
                            st.session_state["import_arquivo_nome"] = arquivo_upload.name
                        except ImportError:
                            df_processado["cliente_nome"] = df_processado.get("telefone_origem", pd.Series(dtype=str)).astype(str).replace("nan", "")
                            st.session_state["import_df_processado"] = df_processado.copy()
                            st.session_state["import_nome_tabela"] = nome_tabela_bd
                            st.session_state["import_tipo"] = tipo_identificado
                            st.session_state["import_arquivo_nome"] = arquivo_upload.name
                        except Exception as e:
                            st.warning(f"⚠️ Erro ao identificar clientes: {e}")
                            df_processado["cliente_nome"] = df_processado.get("telefone_origem", pd.Series(dtype=str)).astype(str).replace("nan", "")
                            st.session_state["import_df_processado"] = df_processado.copy()
                            st.session_state["import_nome_tabela"] = nome_tabela_bd
                            st.session_state["import_tipo"] = tipo_identificado
                            st.session_state["import_arquivo_nome"] = arquivo_upload.name

                if tipo_identificado == "MULTI360":
                    with st.spinner("🔄 Cruzando com CRM..."):
                        try:
                            from services.clientes_service import obter_mapa_hash_cliente
                            mapa_hash = obter_mapa_hash_cliente()
                            df_processado['cliente_nome'] = df_processado['telefone_hash'].map(mapa_hash).fillna("Não Identificado")
                        except Exception:
                            df_processado['cliente_nome'] = df_processado.get('cliente_nome', "Não Identificado")

                if tipo_identificado == "GOTO_AGENT_CALLS":
                    st.success(f"📞 **Relatório Agent Calls:** {len(df_processado)} chamadas atendidas (Contact Resolution = COMPLETED). Salve no banco para o Dashboard usar estes números.")
                    st.session_state['import_df_processado'] = df_processado.copy()
                    st.session_state['import_nome_tabela'] = nome_tabela_bd
                    st.session_state['import_tipo'] = tipo_identificado
                    st.session_state['import_arquivo_nome'] = arquivo_upload.name

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
                            for k in ['import_df_processado', 'import_numero_sem_vinculo', 'import_nome_tabela', 'import_tipo', 'import_arquivo_nome', 'import_agent_calls_bytes']:
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
                        st.caption("Ciclo Automático: Seg a Qui (18:20 às 07:30). FDS Contínuo: Sexta 18:20 até Segunda às 07:30.")
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
                        
                        # Mapa ramal -> nome (inclui especiais: 5366=Caixa Parado, 5365=Chamador, 5364=Jairo; exclui 5355)
                        mapa_ramal_full = _obter_mapa_ramal_analista()
                        mapa_ramais = {r: nome for r, (_, nome) in mapa_ramal_full.items()}

                        def identificar_atendente(row):
                            texto_busca = str(row.get('participantes', '')) + " " + str(row.get('telefone_origem', ''))
                            if "5355" in texto_busca:
                                return "Sistema / Sem Ramal"
                            for ramal, nome in mapa_ramais.items():
                                if ramal in texto_busca:
                                    return nome
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

                            def _sanitize_filename_component(value: str) -> str:
                                # Windows: <>:"/\|?* são inválidos em nomes de arquivo
                                v = re.sub(r'[<>:"/\\|?*]+', " ", str(value or "")).strip()
                                v = re.sub(r"\s+", " ", v)
                                return v or "Sem nome"

                            def _truncate_filename(value: str, max_len: int = 180) -> str:
                                v = str(value or "").strip()
                                if len(v) <= max_len:
                                    return v
                                return v[: max_len - 1].rstrip() + "…"

                            def _format_date_ptbr_for_filename(dt: pd.Timestamp | datetime.datetime) -> str:
                                d = pd.to_datetime(dt, errors="coerce")
                                if pd.isna(d):
                                    return datetime.datetime.now().strftime("%d-%m-%Y")
                                # "dd/mm/aaaa" é o formato brasileiro, mas "/" não pode no Windows; usamos "-"
                                return d.strftime("%d-%m-%Y")

                            # Regra de nome do arquivo do Plantão:
                            # - Se plantão abranger sábado+domingo: "Plantão Fim de semana <data-do-sábado>"
                            # - Caso contrário: "Plantão <Nome do Plantonista> <data de entrada>"
                            data_inicio_plantao = df_limpo["Data_Real"].min()
                            atendentes_unicos = [a for a in df_limpo["Atendente"].dropna().unique().tolist() if str(a).strip()]

                            dias_semana_presentes = set(pd.to_datetime(df_limpo["Data_Real"]).dt.weekday.dropna().tolist())
                            eh_fim_de_semana = (5 in dias_semana_presentes) and (6 in dias_semana_presentes)
                            if eh_fim_de_semana:
                                # garante que a data usada é a do sábado
                                datas_sabado = pd.to_datetime(df_limpo["Data_Real"]).loc[
                                    pd.to_datetime(df_limpo["Data_Real"]).dt.weekday == 5
                                ]
                                data_base = datas_sabado.min() if not datas_sabado.empty else data_inicio_plantao
                                nome_arq = f"Plantão Fim de semana {_format_date_ptbr_for_filename(data_base)}"
                            else:
                                data_base = data_inicio_plantao
                                if len(atendentes_unicos) == 1:
                                    nome_base = _sanitize_filename_component(atendentes_unicos[0])
                                else:
                                    # Lista todos os plantonistas presentes no arquivo (nomes únicos)
                                    nomes = [_sanitize_filename_component(n) for n in atendentes_unicos]
                                    nomes = [n for n in nomes if n and n != "Sem nome"]
                                    nomes = sorted(set(nomes), key=str.casefold)
                                    nome_base = " + ".join(nomes) if nomes else "Sem nome"
                                nome_arq = f"Plantão {nome_base} {_format_date_ptbr_for_filename(data_base)}"
                            nome_arq = _sanitize_filename_component(nome_arq)
                            nome_arq = _truncate_filename(nome_arq, max_len=180)
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