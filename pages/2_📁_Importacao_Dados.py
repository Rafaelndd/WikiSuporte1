import streamlit as st
import pandas as pd
import re
import io
import datetime
from sqlalchemy import text
from modules.database import get_connection

# Importa as suas funções brilhantes de LGPD e limpeza
from modules.processador_csv import processar_csv_goto, processar_csv_multi360, ler_arquivo_dinamico

# Tenta importar auditoria
try:
    from modules.auditoria import registrar_log_auditoria
except:
    def registrar_log_auditoria(*args): pass

# ==========================================
# 1. CADEADO DE SEGURANÇA E SESSÃO
# ==========================================
st.set_page_config(page_title="WikiSuporte </>", page_icon="📊", layout="wide")
if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

if perfil_usuario not in ["desenvolvedor", "coordenação"]:
    st.error("⛔ Acesso Negado: Você não tem permissão para acessar esta página.")
    st.stop()

# ==========================================
# 2. FUNÇÕES AUXILIARES DE BANCO DE DADOS
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

def is_plantao_normal(dt):
    if pd.isnull(dt): return False
    wd = dt.weekday() 
    time_val = dt.time()
    
    if wd in [5, 6]: return True
    if wd in [0, 1, 2, 3]:
        if time_val <= datetime.time(7, 30): return True
        if time_val >= datetime.time(18, 0): return True
        return False
    if wd == 4:
        if time_val <= datetime.time(7, 30): return True
        if time_val >= datetime.time(18, 30): return True
        return False

# ==========================================
# 3. INTERFACE DE USUÁRIO (UX) - ABAS
# ==========================================
st.title("📁 Importação e Exportação de Relatórios")
st.markdown("Gerencie a importação de arquivos mensais, vincule clientes ao CRM e extraia plantões de telefonia com rapidez.")

aba1, aba2, aba3 = st.tabs(["📥 Importação GoTo / Multi360", "🔗 Cadastrar Clientes (CRM)", "Extrator de Plantões - GoTo"])

# ------------------------------------------
# ABA 1: IMPORTAÇÃO DE ARQUIVOS (MENSAL)
# ------------------------------------------
with aba1:
    
    with st.container(border=True):
        arquivo_upload = st.file_uploader("📂 Selecione um arquivo:", type=['csv', 'xlsx'], key="up_import")
    
    if arquivo_upload:
        df_preview = ler_arquivo_dinamico(arquivo_upload)
        tipo_identificado, df_processado, erro_processamento = None, None, None
        
        if 'Conversation space id' in df_preview.columns: tipo_identificado = "GOTO"
        elif 'PROTOCOLO' in df_preview.columns: tipo_identificado = "MULTI360"
        else: st.error("❌ Arquivo não reconhecido."); st.stop()
            
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
            # 🛡️ TRAVA INTELIGENTE: Bloqueia se for curto demais, MAS PERMITE OVERRIDE!
            if tipo_identificado == "GOTO":
                if pd.api.types.is_datetime64_any_dtype(df_processado['data_chamada']):
                    dias_arquivo = (df_processado['data_chamada'].max() - df_processado['data_chamada'].min()).days
                else:
                    dt_temp = pd.to_datetime(df_processado['data_chamada'], errors='coerce')
                    dias_arquivo = (dt_temp.max() - dt_temp.min()).days
                
                if pd.isna(dias_arquivo): dias_arquivo = 0
                
                if dias_arquivo <= 5:
                    st.warning(f"🤖 **PSY alerta:** Este arquivo cobre apenas **{int(dias_arquivo)} dia(s)** de registros. Ele parece ser um **Relatório de Plantão Diário**, e não um Fechamento Mensal.\n\n👉 Para extrair seu plantão, use a aba **'🌙 Extrator de Plantões Diário'**.")
                    
                    liberar = st.checkbox("Eu confirmo que este é um arquivo MENSAL válido (ex: fechamento gerado no início do mês). Desbloquear importação.")
                    if not liberar:
                        bloqueio_plantao = True
            
            if not bloqueio_plantao:
                st.success(f"✅ Arquivo Mensal do **{tipo_identificado}** processado com sucesso!")
                with st.container(border=True):
                    st.markdown("### 🔍 Pré-visualização dos Dados")
                    st.dataframe(df_processado.head(5), use_container_width=True)
                
                with st.container(border=True):
                    st.markdown("#### 📊 Resumo do Arquivo Mensal")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("Total de Registros lidos", len(df_processado))
                    if tipo_identificado == "GOTO":
                        col_m2.metric("Data Inicial", df_processado['data_chamada'].min().strftime('%d/%m/%Y'))
                        col_m3.metric("Data Final", df_processado['data_chamada'].max().strftime('%d/%m/%Y'))
                    else:
                        col_m2.metric("Data Inicial", df_processado['data_inicio'].min().strftime('%d/%m/%Y'))
                        col_m3.metric("Data Final", df_processado['data_inicio'].max().strftime('%d/%m/%Y'))
                
                if st.button("💾 Confirmar e Salvar Mensal no Banco", type="primary", use_container_width=True):
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
    st.caption("Associe números de telefone a um CNPJ para unificar o histórico do cliente.")
    col_crm1, col_crm2 = st.columns(2)
    
    with col_crm1:
        with st.container(border=True):
            with st.form("form_crm"):
                cnpj_limpo = apenas_numeros(st.text_input("CNPJ do Cliente:", placeholder="Ex: 00.000.000/0000-00"))
                telefone_limpo = apenas_numeros(st.text_input("Telefone ou WhatsApp:", placeholder="Ex: (48) 99999-9999"))
                btn_vincular = st.form_submit_button("🔗 Vincular", type="primary", use_container_width=True)
                
                if btn_vincular:
                    if cnpj_limpo and telefone_limpo:
                        st.success(f"✅ Sucesso! Telefone vinculado.")
                        registrar_log_auditoria(usuario_id, "VINCULO_CRM", f"Vinculou {telefone_limpo} ao {cnpj_limpo}")
                        with st.spinner("🕸️ Sincronizando dados..."):
                            try:
                                linhas_afetadas = oraculo.sincronizar_vinculos_goto()
                                if linhas_afetadas > 0: st.info(f"🚀 {linhas_afetadas} registros sincronizados.")
                                else: st.info("Nenhum registro novo encontrado.")
                            except Exception as e: st.error(f"Erro ao sincronizar: {e}")
                    else: st.warning("⚠️ Preencha CNPJ e Telefone.")

    with col_crm2:
        with st.container(border=True):
            st.markdown("#### 📊 Status da Normalização")
            if cnpj_limpo: st.success(f"🏢 **CNPJ Lido:** {cnpj_limpo}")
            if telefone_limpo: st.success(f"📞 **Telefone Lido:** {telefone_limpo}")

# ------------------------------------------
# ABA 3: ANÁLISE DE PLANTÕES (GOTO)
# ------------------------------------------
with aba3:
    st.subheader("🌙 Extrator Inteligente de Plantões")
    
    st.info("🤖 **PSY:** Olá! Envie o arquivo do plantão. Eu vou ignorar ligações de sistema (URA/Perdidas), agrupar os atendimentos por analista, preparar os relatórios e **salvar automaticamente cada atendimento** no banco de dados!")
    
    if 'up_plantao_key' not in st.session_state:
        st.session_state['up_plantao_key'] = "up_plantao_1"

    with st.container(border=True):
        arquivo_plantao = st.file_uploader("📂 Envie o CSV Diário/Semanal do GoTo:", type=['csv', 'xlsx'], key=st.session_state['up_plantao_key'])
    
    if arquivo_plantao:
        df_preview_p = ler_arquivo_dinamico(arquivo_plantao)
        if 'Conversation space id' not in df_preview_p.columns:
            st.error("❌ Por favor, envie um relatório válido de Telefonia (GoTo).")
        else:
            arquivo_plantao.seek(0)
            with st.spinner("Limpando e formatando dados da Telefonia..."):
                df_goto_bruto = processar_csv_goto(arquivo_plantao)
                
            # 🛡️ TRAVA ABSOLUTA: Bloqueia se for longo demais (Mensal)
            if pd.api.types.is_datetime64_any_dtype(df_goto_bruto['data_chamada']):
                dias_arquivo_plantao = (df_goto_bruto['data_chamada'].max() - df_goto_bruto['data_chamada'].min()).days
            else:
                dt_temp = pd.to_datetime(df_goto_bruto['data_chamada'], errors='coerce')
                dias_arquivo_plantao = (dt_temp.max() - dt_temp.min()).days
            
            if pd.isna(dias_arquivo_plantao): dias_arquivo_plantao = 0
            
            if dias_arquivo_plantao > 5:
                st.error(f"🤖 **PSY bloqueou a extração:** \n\nEste arquivo abrange **{int(dias_arquivo_plantao)} dias** de registros. Ele foi identificado como um **Relatório Mensal**.\n\n👉 A Aba 3 é destinada apenas para plantões de curto prazo. Para o mês todo, use a aba '📥 Importar Mensal'.")
            else:
                # 🚫 FILTRO ANTIMANCHAS 1: Remove chamadas com Duração 0
                df_goto = df_goto_bruto[df_goto_bruto['duracao_ms'].fillna(0) > 0].copy()
                
                if df_goto.empty:
                    st.warning("⚠️ **PSY informa:** Todas as chamadas deste arquivo eram perdidas ou abandonadas (Duração 0). Não há atendimentos para extrair.")
                else:
                    st.divider()
                    st.markdown("#### ⚙️ Configuração do Regime do Plantão")
                    
                    regime = st.radio("Selecione o regime operado neste arquivo:", 
                                      ["Normal (Seg-Sex e Fim de Semana Padrão)", "Especial (Feriados Nacionais/Locais ou Escalas Customizadas)"])
                    
                    df_plantao_filtrado = pd.DataFrame()
                    inicio_selecionado = None
                    fim_selecionado = None
                    
                    if regime == "Normal (Seg-Sex e Fim de Semana Padrão)":
                        st.caption("Regra automática: Seg-Qui (18:00 às 07:30) | Sex (A partir das 18:30) | Sáb e Dom (24h).")
                        mascara = df_goto['data_chamada'].apply(is_plantao_normal)
                        df_plantao_filtrado = df_goto[mascara].sort_values('data_chamada')
                        if not df_plantao_filtrado.empty:
                            inicio_selecionado = df_plantao_filtrado['data_chamada'].min()
                            fim_selecionado = df_plantao_filtrado['data_chamada'].max()
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
                            st.error("A Data de Término não pode ser menor que a Data de Início.")
                        else:
                            mascara = (df_goto['data_chamada'] >= inicio_selecionado) & (df_goto['data_chamada'] <= fim_selecionado)
                            df_plantao_filtrado = df_goto[mascara].sort_values('data_chamada')

                    if st.button("🔍 Extrair Atendimentos", type="primary"):
                        st.session_state['df_plantao_filtrado'] = df_plantao_filtrado
                        st.session_state['inicio_plantao'] = inicio_selecionado
                        st.session_state['fim_plantao'] = fim_selecionado
                        
                    df_exibicao = st.session_state.get('df_plantao_filtrado', pd.DataFrame())
                    
                    if not df_exibicao.empty:
                        # --- PREPARAÇÃO DOS DADOS E MAPA DE RAMAIS ---
                        df_temp = pd.DataFrame()
                        df_temp['Data_Real'] = df_exibicao['data_chamada'] 
                        df_temp['Data_Fim_Real'] = df_exibicao['data_chamada'] + pd.to_timedelta(df_exibicao['duracao_ms'].fillna(0), unit='ms')
                        df_temp['Data'] = df_temp['Data_Real'].dt.strftime('%d/%m/%Y')
                        df_temp['Horário inicio atendimento'] = df_temp['Data_Real'].dt.strftime('%H:%M:%S')
                        df_temp['Horário fim do atendimento'] = df_temp['Data_Fim_Real'].dt.strftime('%H:%M:%S')
                        
                        mapa_ramais = {
                            "5335": "RENATO", "5333": "AGNALDO", "5331": "BRUNO", "5340": "EMIL",
                            "5332": "DANIEL", "5344": "MARCELO", "5336": "ADILTON", "5339": "LUIS",
                            "5343": "JOAO", "5341": "GABRIEL", "5338": "RAFAEL NASCIMENTO", "5337": "RAFAEL FREITAS"
                        }

                        if 'participantes' in df_exibicao.columns:
                            ramais_extraidos = df_exibicao['participantes'].astype(str).str.extract(r'(?<!\d)(\d{4}):')[0]
                            def nomear_atendente(ramal):
                                if pd.isna(ramal) or str(ramal).strip() == "": return "Sistema / Sem Ramal"
                                if ramal in mapa_ramais: return mapa_ramais[ramal]
                                return f"Ramal {ramal} (Não Cadastrado)"
                            df_temp['Atendente'] = ramais_extraidos.apply(nomear_atendente)
                        else:
                            df_temp['Atendente'] = "Sistema / Sem Ramal"
                        
                        df_temp['Total (Minutos)'] = (df_exibicao['duracao_ms'].fillna(0) / 60000).round(2)
                        
                        # 🚫 FILTRO ANTIMANCHAS 2: Ignorar completamente "Sistema / Sem Ramal"
                        mascara_validas = ~df_temp['Atendente'].isin(["Sistema / Sem Ramal"])
                        df_limpo = df_temp[mascara_validas].copy()
                        
                        if df_limpo.empty:
                            st.warning("⚠️ **PSY informa:** Analisei o período, mas todos os registros eram chamadas não atendidas por humanos (URA/Sistema).")
                        else:
                            st.success(f"🎯 **PSY diz:** Temos **{len(df_limpo)} atendimentos reais**! Organizando relatórios e salvando no banco...")
                            
                            # Ordenação e Agrupamento por Analista
                            df_limpo = df_limpo.sort_values(by=['Atendente', 'Data_Real'])
                            
                            # --- 💾 AUTO-SALVAMENTO NO BANCO DE DADOS LINHA A LINHA ---
                            engine = get_connection()
                            try:
                                # Busca usuários ativos ignorando maiúsculas e minúsculas
                                df_usuarios = pd.read_sql(text("SELECT id, nome FROM usuarios WHERE ativo = TRUE"), engine)
                                mapa_ids_bd = {row['nome'].strip().upper(): (row['id'], row['nome']) for _, row in df_usuarios.iterrows()}
                                
                                inseridos, ignorados = 0, 0
                                
                                with engine.begin() as conn_pl:
                                    for _, row in df_limpo.iterrows():
                                        analista_arquivo = row['Atendente'].strip().upper()
                                        
                                        # Se o atendente existir no banco de dados
                                        if analista_arquivo in mapa_ids_bd:
                                            id_an, nome_banco = mapa_ids_bd[analista_arquivo]
                                            dt_in = row['Data_Real']
                                            dt_out = row['Data_Fim_Real']
                                            
                                            # Guardião Linha a Linha: Barrar duplicação da MESMA chamada
                                            query_check = text("SELECT id_plantao FROM plantoes_epsy WHERE id_analista_epsy = :id_an AND data_hora_entrada = :dt_in")
                                            existe = conn_pl.execute(query_check, {"id_an": id_an, "dt_in": dt_in}).fetchone()
                                            
                                            if not existe:
                                                query_pl = text("INSERT INTO plantoes_epsy (nome_analista_epsy, id_analista_epsy, data_hora_entrada, data_hora_saida) VALUES (:nome, :id_an, :dt_in, :dt_out)")
                                                conn_pl.execute(query_pl, {"nome": nome_banco, "id_an": id_an, "dt_in": dt_in, "dt_out": dt_out})
                                                inseridos += 1
                                            else:
                                                ignorados += 1
                                                
                                if inseridos > 0:
                                    st.success(f"✅ **{inseridos}** novas ligações individuais foram registradas com sucesso na tabela de Plantões!")
                                    registrar_log_auditoria(usuario_id, "REGISTRO_PLANTAO_AUTO", f"Registrou {inseridos} chamadas automáticas.")
                                if ignorados > 0:
                                    st.caption(f"🛡️ **{ignorados} ligações** já constavam no banco e foram ignoradas para evitar duplicidade.")
                                    
                            except Exception as e:
                                st.error(f"❌ Erro ao salvar atendimentos automaticamente: {e}")

                            # --- GERAÇÃO DOS ARQUIVOS DE EXPORTAÇÃO ---
                            txt_content = "Relatório Oficial de Atendimentos - Plantão\n"
                            txt_content += "="*60 + "\n\n"
                            
                            lista_dfs_export = []
                            analistas_unicos = df_limpo['Atendente'].unique()
                            
                            for analista in analistas_unicos:
                                df_grupo = df_limpo[df_limpo['Atendente'] == analista].drop(columns=['Data_Real', 'Data_Fim_Real'])
                                
                                txt_content += f"👤 ATENDENTE: {analista}\n"
                                txt_content += "-"*60 + "\n"
                                for _, row in df_grupo.iterrows():
                                    txt_content += f"Data: {row['Data']}   Início: {row['Horário inicio atendimento']}   Fim: {row['Horário fim do atendimento']}   Total (Min): {row['Total (Minutos)']}\n"
                                txt_content += f"\n-> TOTAL DE ATENDIMENTOS ({analista}): {len(df_grupo)}\n"
                                txt_content += "="*60 + "\n\n"
                                
                                lista_dfs_export.append(df_grupo)
                                linha_subtotal = pd.DataFrame([{
                                    'Data': '', 'Horário inicio atendimento': '', 'Horário fim do atendimento': '',
                                    'Atendente': f'TOTAL {analista}', 'Total (Minutos)': f'{len(df_grupo)} atendimentos'
                                }])
                                lista_dfs_export.append(linha_subtotal)
                                lista_dfs_export.append(pd.DataFrame([{'Data': '', 'Horário inicio atendimento': '', 'Horário fim do atendimento': '', 'Atendente': '', 'Total (Minutos)': ''}]))

                            df_final_export = pd.concat(lista_dfs_export, ignore_index=True).iloc[:-1]
                            
                            # 1. Exibir na Tela
                            with st.container(border=True):
                                st.dataframe(df_final_export, use_container_width=True, hide_index=True)
                            
                            # 2. Geradores Finais
                            csv_content = df_final_export.to_csv(index=False, sep=';', decimal=',')
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer: 
                                df_final_export.to_excel(writer, index=False, sheet_name='Plantao_Separado')
                            excel_content = output.getvalue()
                            
                            st.markdown("#### 📥 Baixar Relatórios")
                            c_txt, c_xls, c_csv = st.columns(3)
                            nome_arq = f"Plantao_Oficial_{datetime.datetime.now().strftime('%d%m%Y')}"
                            
                            c_txt.download_button("📄 Exportar TXT Formatado", txt_content, f"{nome_arq}.txt", "text/plain", use_container_width=True)
                            c_xls.download_button("📊 Exportar Excel (.xlsx)", excel_content, f"{nome_arq}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                            c_csv.download_button("📑 Exportar CSV", csv_content, f"{nome_arq}.csv", "text/csv", use_container_width=True)

                            st.divider()
                            # Botão Simples para resetar a tela
                            if st.button("🧹 Limpar Tela e Enviar Novo Arquivo", use_container_width=True):
                                st.session_state['up_plantao_key'] = f"up_plantao_{datetime.datetime.now().timestamp()}"
                                if 'df_plantao_filtrado' in st.session_state: del st.session_state['df_plantao_filtrado']
                                if 'inicio_plantao' in st.session_state: del st.session_state['inicio_plantao']
                                if 'fim_plantao' in st.session_state: del st.session_state['fim_plantao']
                                st.rerun()
                    
                    elif st.session_state.get('df_plantao_filtrado') is not None and st.session_state['df_plantao_filtrado'].empty:
                        st.info("🤖 **PSY:** O arquivo é válido, mas não ocorreram atendimentos nesse horário de plantão específico.")