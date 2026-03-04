import streamlit as st
import pandas as pd
import re
import io
import datetime
import os
from sqlalchemy import text
from modules.database import get_connection

# Importa as suas funções de LGPD e limpeza
from modules.processador_csv import processar_csv_goto, processar_csv_multi360, ler_arquivo_dinamico

try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

try:
    import modules.oraculo as oraculo
except:
    oraculo = None

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="WikiSuporte </>", page_icon="📊", layout="wide")
if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()
nome_usuario = str(st.session_state.get('usuario_nome', 'Sistema'))

if perfil_usuario not in ["desenvolvedor", "coordenação"]:
    st.error("⛔ Acesso Negado: Você não tem permissão para acessar esta página.")
    st.stop()

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
        
    # 0=Segunda-feira: Plantão do FDS encerra às 07:00. O novo começa às 18:30.
    if wd == 0: 
        if time_val <= datetime.time(7, 0): return True
        if time_val >= datetime.time(18, 30): return True
        return False
        
    # 1=Terça a 4=Sexta: O da madrugada encerra 07:30. O novo começa 18:30.
    if wd in [1, 2, 3, 4]: 
        if time_val <= datetime.time(7, 30): return True
        if time_val >= datetime.time(18, 30): return True
        return False

# ==========================================
# 3. INTERFACE DE USUÁRIO (UX) - ABAS
# ==========================================
st.title("📁 Importação e Exportação de Relatórios")
st.markdown("Importe relatórios mensais, faça a gestão do CRM de clientes e extraia análises de Plantão diário.")

aba1, aba2, aba3 = st.tabs(["📥 Importar Mensal / Relatórios", "🔗 Cadastrar Clientes (CRM)", "🌙 Extrator de Plantões Diário"])

# ------------------------------------------
# ABA 1: IMPORTAÇÃO DE ARQUIVOS (MENSAL)
# ------------------------------------------
with aba1:
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
            st.error("❌ O arquivo 'User Activity' do GoTo é utilizado para fatiar plantão. Por favor, utilize a Aba **'🌙 Extrator de Plantões Diário'** para esse arquivo.")
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
                    st.warning(f"🤖 **PSY alerta:** Este arquivo cobre apenas **{int(dias_arquivo)} dia(s)**. Parece um Relatório de Plantão.")
                    liberar = st.checkbox("Eu confirmo que este é um arquivo MENSAL válido. Desbloquear importação.")
                    if not liberar: bloqueio_plantao = True

            if not bloqueio_plantao:
                if tipo_identificado == "GOTO":
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
                            
                            def extrair_numero_cliente(row):
                                if str(row.get('direcao', '')).lower() == 'recebida':
                                    return apenas_numeros(row.get('telefone_origem', ''))
                                else:
                                    nums = re.findall(r'\+55\d+', str(row.get('participantes', '')))
                                    if nums: return apenas_numeros(nums[0])
                                    return apenas_numeros(row.get('telefone_origem', ''))

                            numeros_para_busca = df_processado.apply(extrair_numero_cliente, axis=1)
                            df_processado['cliente_nome'] = numeros_para_busca.map(mapa_clientes).fillna("Não Identificado")
                            
                            sucesso_crm = len(df_processado[df_processado['cliente_nome'] != "Não Identificado"])
                            st.success(f"🎯 **Identificação Concluída:** {sucesso_crm} chamadas foram vinculadas a clientes cadastrados!")
                        except Exception as e:
                            st.warning(f"⚠️ Aviso: O cruzamento com o CRM falhou. Erro: {e}")
                            df_processado['cliente_nome'] = "Não Identificado"

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
                
                if st.button("💾 Confirmar e Salvar Mensal no Banco", type="primary", width='stretch'):
                    with st.spinner("Gravando dados no WikiSuporte..."):
                        sucesso, msg = salvar_no_banco(df_processado, nome_tabela_bd, tipo_identificado)
                        if sucesso:
                            st.success(f"🎉 Fantástico! {len(df_processado)} registros foram salvos no banco.")
                            registrar_log_auditoria(usuario_id, "IMPORT_CSV", f"Importou arquivo MENSAL {arquivo_upload.name}")
                        else: st.error(f"❌ Erro ao salvar o arquivo: {msg}")

# ------------------------------------------
# ABA 2: VÍNCULO DE CLIENTES (CRM)
# ------------------------------------------
with aba2:
    st.markdown("### 🔗 Cadastro de Clientes (CRM)")
    st.caption("Cadastre o nome do cliente e associe seus números de telefone (CNPJ). Isso fará com que o Dashboard identifique as ligações por nome.")
    col_crm1, col_crm2 = st.columns([1.5, 1])
    
    with col_crm1:
        with st.container(border=True):
            with st.form("form_crm"):
                nome_cliente = st.text_input("Razão Social / Nome do Cliente (Obrigatório):", placeholder="Ex: Posto Avenida LTDA")
                cnpj_limpo = apenas_numeros(st.text_input("CNPJ do Cliente (Opcional):", placeholder="Ex: 00.000.000/0000-00"))
                telefone_limpo = apenas_numeros(st.text_input("Telefone ou WhatsApp (Obrigatório):", placeholder="Ex: 4899999999"))
                
                btn_vincular = st.form_submit_button("🔗 Salvar e Vincular Cliente", type="primary", width='stretch')
                
                if btn_vincular:
                    if nome_cliente and telefone_limpo:
                        try:
                            engine = get_connection()
                            with engine.begin() as conn:
                                query_check = text("""
                                    SELECT id_cliente FROM clientes_crm 
                                    WHERE razao_social ILIKE :nome 
                                       OR (:cnpj != '' AND cnpj IS NOT NULL AND cnpj = :cnpj) 
                                    LIMIT 1
                                """)
                                id_cliente = conn.execute(query_check, {"nome": f"%{nome_cliente}%", "cnpj": cnpj_limpo}).scalar()
                                
                                if not id_cliente:
                                    query_insert_cliente = text("""
                                        INSERT INTO clientes_crm (razao_social, cnpj, id_analista_epsy, nome_analista_epsy)
                                        VALUES (:nome, :cnpj, :id_an, :nome_an)
                                        RETURNING id_cliente
                                    """)
                                    id_cliente = conn.execute(query_insert_cliente, {
                                        "nome": nome_cliente.strip().upper(), "cnpj": cnpj_limpo, 
                                        "id_an": usuario_id, "nome_an": nome_usuario
                                    }).scalar()
                                
                                query_insert_tel = text("""
                                    INSERT INTO clientes_telefones (id_cliente, numero, origem_dado)
                                    VALUES (:id_c, :tel, 'VINCULO_MANUAL')
                                """)
                                conn.execute(query_insert_tel, {"id_c": id_cliente, "tel": telefone_limpo})

                            st.success(f"✅ Sucesso! O cliente **{nome_cliente.upper()}** agora está mapeado com o número **{telefone_limpo}**.")
                            registrar_log_auditoria(usuario_id, "VINCULO_CRM", f"Vinculou tel {telefone_limpo} ao cliente {nome_cliente}")
                            
                            if oraculo:
                                with st.spinner("🕸️ Acionando sincronização externa..."):
                                    linhas_afetadas = oraculo.sincronizar_vinculos_goto()
                                    if linhas_afetadas > 0: st.info(f"🚀 Oráculo sincronizou {linhas_afetadas} registros legados.")
                                    
                        except Exception as e:
                            st.error(f"❌ Erro ao gravar cliente no banco de dados. Detalhe: {e}")
                    else: 
                        st.warning("⚠️ Preencha no mínimo o Nome do Cliente e o Telefone.")

    with col_crm2:
        with st.container(border=True):
            st.markdown("#### 📊 Validação de Cadastro")
            st.caption("Os dados serão salvos de forma limpa, e o controle de segurança será feito pela própria Engine do banco de dados (PostgreSQL).")
            if nome_cliente: st.success(f"👤 **Cliente:** {nome_cliente.upper()}")
            if cnpj_limpo: st.success(f"🏢 **CNPJ:** {cnpj_limpo}")
            if telefone_limpo: st.success(f"📞 **Telefone:** {telefone_limpo}")

# ------------------------------------------
# ABA 3: ANÁLISE DE PLANTÕES (GOTO)
# ------------------------------------------
with aba3:
    st.subheader("Extrator Inteligente de Plantões")
    st.info("🤖 **PSY:** Olá! Faça o upload do arquivo do GoTo. Eu buscarei automaticamente no arquivo inteiro quais ligações pertencem ao plantão, separando cada plantonista caso haja imprevistos e substituições!")
    
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
            st.error("❌ Formato não suportado. Por favor, envie um relatório 'Call Reports' ou 'User Activity' do GoTo.")
        else:
            arquivo_plantao.seek(0)
            with st.spinner("Limpando e formatando dados da Telefonia..."):
                
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
                st.error(f"🤖 **PSY bloqueou a extração:** \n\nEste arquivo abrange **{int(dias_arquivo_plantao)} dias**. Relatórios de plantão costumam ter no máximo 3 ou 4 dias.\n\n👉 Para o mês todo, use a aba '📥 Importar Mensal'.")
            else:
                df_goto = df_goto_bruto[df_goto_bruto['duracao_ms'].fillna(0) > 0].copy()
                
                if df_goto.empty:
                    st.warning("⚠️ **PSY informa:** Todas as chamadas deste arquivo eram perdidas ou abandonadas (Duração 0).")
                else:
                    st.divider()
                    st.markdown("#### ⚙️ Configuração do Regime do Plantão")
                    
                    # 🎯 BOTÃO PARA ESCOLHER OS REGIMES (OS DOIS ESTÃO ATIVOS)
                    regime = st.radio("Selecione o regime a ser operado neste arquivo:", 
                                      ["Normal (Seg-Sex e Fim de Semana Padrão)", "Especial (Feriados Nacionais/Locais ou Escalas Customizadas)"])
                    
                    df_plantao_filtrado = pd.DataFrame()
                    
                    if regime == "Normal (Seg-Sex e Fim de Semana Padrão)":
                        st.caption("Ciclo Automático: Seg a Qui (18:30 às 07:30). FDS Contínuo: Sexta 18:30 até Segunda às 07:00.")
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
                            st.warning("⚠️ **PSY informa:** Analisei o período, mas todos os registros eram chamadas não atendidas por humanos (URA/Sistema).")
                        else:
                            st.success(f"🎯 **PSY diz:** Temos **{len(df_limpo)} atendimentos reais**! Salvando no banco...")
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
                            txt_content = "Relatório Oficial de Atendimentos - Plantão\n" + "="*60 + "\n\n"
                            
                            lista_dfs_export = []
                            analistas_unicos = df_limpo['Atendente'].unique()
                            
                            # Separa os atendimentos por analista e calcula o total dinâmico de cada um
                            for analista in analistas_unicos:
                                df_grupo = df_limpo[df_limpo['Atendente'] == analista].drop(columns=['Data_Real', 'Data_Fim_Real'])
                                
                                txt_content += f"👤 ATENDENTE: {analista}\n" + "-"*60 + "\n"
                                for _, row in df_grupo.iterrows():
                                    txt_content += f"Data: {row['Data']}   Início: {row['Horário inicio atendimento']}   Fim: {row['Horário fim do atendimento']}   Total (Min): {row['Total (Minutos)']}\n"
                                
                                txt_content += f"\n-> TOTAL DE ATENDIMENTOS ({analista}): {len(df_grupo)}\n" + "="*60 + "\n\n"
                                
                                lista_dfs_export.append(df_grupo)
                                lista_dfs_export.append(pd.DataFrame([{'Data': '', 'Horário inicio atendimento': '', 'Horário fim do atendimento': '', 'Atendente': f'TOTAL {analista}', 'Total (Minutos)': f'{len(df_grupo)} atendimentos'}]))
                                lista_dfs_export.append(pd.DataFrame([{'Data': '', 'Horário inicio atendimento': '', 'Horário fim do atendimento': '', 'Atendente': '', 'Total (Minutos)': ''}]))

                            df_final_export = pd.concat(lista_dfs_export, ignore_index=True).iloc[:-1]
                            
                            with st.container(border=True): st.dataframe(df_final_export, width='stretch', hide_index=True)
                            
                            csv_content = df_final_export.to_csv(index=False, sep=';', decimal=',')
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer: df_final_export.to_excel(writer, index=False, sheet_name='Plantao_Separado')
                            excel_content = output.getvalue()
                            
                            st.markdown("#### 📥 Baixar Relatórios")
                            c_txt, c_xls, c_csv = st.columns(3)
                            nome_arq = f"Plantao_Oficial_{datetime.datetime.now().strftime('%d%m%Y')}"
                            c_txt.download_button("📄 Exportar TXT Formatado", txt_content, f"{nome_arq}.txt", "text/plain", width='stretch')
                            c_xls.download_button("📊 Exportar Excel (.xlsx)", excel_content, f"{nome_arq}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')
                            c_csv.download_button("📑 Exportar CSV", csv_content, f"{nome_arq}.csv", "text/csv", width='stretch')

                            st.divider()
                            
                            if st.button("🧹 Limpar Tela e Enviar Novo Arquivo", width='stretch'):
                                st.session_state['plantao_uploader_key'] += 1
                                if 'df_plantao_filtrado' in st.session_state: del st.session_state['df_plantao_filtrado']
                                st.rerun()
                    
                    elif st.session_state.get('df_plantao_filtrado') is not None and st.session_state['df_plantao_filtrado'].empty:
                        st.info("🤖 **PSY:** O arquivo é válido, mas não ocorreram atendimentos nesse horário de plantão específico.")