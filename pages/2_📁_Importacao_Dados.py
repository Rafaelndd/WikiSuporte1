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
if not st.session_state.get('autenticado'):
    st.switch_page("app.py")

usuario_id = st.session_state.get('usuario_id')
perfil_usuario = str(st.session_state.get('perfil', '')).lower()

# Apenas Desenvolvedores e Coordenação podem importar dados em massa
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

# --- Função de Horários do Plantão Normal ---
def is_plantao_normal(dt):
    if pd.isnull(dt): return False
    wd = dt.weekday() # 0 = Segunda, 4 = Sexta, 5 = Sábado, 6 = Domingo
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
st.title("📁 Central de Importação e Operações")
st.markdown("Importe relatórios, vincule dados no CRM e extraia análises avançadas de horários de Plantão.")

aba1, aba2, aba3 = st.tabs(["📥 Importar Relatórios", "🔗 Cadastrar Clientes", "🌙 Extrator de Plantões (GoTo)"])

# ------------------------------------------
# ABA 1: IMPORTAÇÃO DE ARQUIVOS
# ------------------------------------------
with aba1:
    st.info("💡 **Dica:** O sistema identifica automaticamente se o arquivo é do GoTo ou do Multi360.")
    with st.container(border=True):
        arquivo_upload = st.file_uploader("📂 Selecione o seu arquivo de atendimento:", type=['csv', 'xlsx'], key="up_import")
    
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
                
        if erro_processamento: st.error(f"❌ Erro no processamento: {erro_processamento}")
        elif df_processado is not None and not df_processado.empty:
            st.success(f"✅ Arquivo do **{tipo_identificado}** processado com sucesso!")
            with st.container(border=True):
                st.markdown("### 🔍 Pré-visualização dos Dados")
                st.dataframe(df_processado.head(5), use_container_width=True)
            
            with st.container(border=True):
                st.markdown("#### 📊 Resumo do Arquivo")
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Total de Registros lidos", len(df_processado))
                if tipo_identificado == "GOTO":
                    col_m2.metric("Data Inicial", df_processado['data_chamada'].min().strftime('%d/%m/%Y'))
                    col_m3.metric("Data Final", df_processado['data_chamada'].max().strftime('%d/%m/%Y'))
                else:
                    col_m2.metric("Data Inicial", df_processado['data_inicio'].min().strftime('%d/%m/%Y'))
                    col_m3.metric("Data Final", df_processado['data_inicio'].max().strftime('%d/%m/%Y'))
            
            if st.button("💾 Confirmar e Salvar no Banco de Dados", type="primary", use_container_width=True):
                with st.spinner("Gravando dados no WikiSuporte..."):
                    sucesso, msg = salvar_no_banco(df_processado, nome_tabela_bd, tipo_identificado)
                    if sucesso:
                        st.success(f"🎉 Fantástico! {len(df_processado)} registros foram salvos.")
                        registrar_log_auditoria(usuario_id, "IMPORT_CSV", f"Importou arquivo {arquivo_upload.name}")
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
    
    # 🤖 Interação com o Mascote PSY
    st.info("🤖 **PSY:** Olá! Faça o upload do arquivo do GoTo com as ligações do plantão anterior. Eu vou fatiar os horários e preparar os relatórios exatos para você exportar em TXT, Excel ou CSV!")
    
    with st.container(border=True):
        arquivo_plantao = st.file_uploader("📂 Envie o CSV do GoTo para análise de horários:", type=['csv', 'xlsx'], key="up_plantao")
    
    if arquivo_plantao:
        df_preview_p = ler_arquivo_dinamico(arquivo_plantao)
        if 'Conversation space id' not in df_preview_p.columns:
            st.error("❌ Por favor, envie um relatório válido de Telefonia (GoTo).")
        else:
            arquivo_plantao.seek(0)
            with st.spinner("Limpando e formatando dados da Telefonia..."):
                df_goto = processar_csv_goto(arquivo_plantao)
                
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

            if st.button("🔍 Extrair e Gerar Relatórios", type="primary"):
                st.session_state['df_plantao_filtrado'] = df_plantao_filtrado
                st.session_state['inicio_plantao'] = inicio_selecionado
                st.session_state['fim_plantao'] = fim_selecionado
                
            df_exibicao = st.session_state.get('df_plantao_filtrado', pd.DataFrame())
            
            if not df_exibicao.empty:
                st.success(f"🎯 **PSY diz:** Extração concluída com sucesso! Encontrei **{len(df_exibicao)} atendimentos** nesse plantão. Aqui estão os dados formatados:")
                
                # --- PREPARAÇÃO DO DATAFRAME FORMATADO ---
                df_export = pd.DataFrame()
                df_export['Data'] = df_exibicao['data_chamada'].dt.strftime('%d/%m/%Y')
                df_export['Horário inicio atendimento'] = df_exibicao['data_chamada'].dt.strftime('%H:%M:%S')
                
                # Calcula o fim da chamada = Início + Duração
                tempos_fim = df_exibicao['data_chamada'] + pd.to_timedelta(df_exibicao['duracao_ms'].fillna(0), unit='ms')
                df_export['Horário fim do atendimento'] = tempos_fim.dt.strftime('%H:%M:%S')
                
                df_export['Atendente'] = df_exibicao['nome_analista_epsy'].fillna("Desconhecido")
                
                # Duração em Minutos (arredondado para 2 casas decimais)
                df_export['Total (Minutos)'] = (df_exibicao['duracao_ms'].fillna(0) / 60000).round(2)
                
                # 1. Exibir na Tela
                with st.container(border=True):
                    st.dataframe(df_export, use_container_width=True, hide_index=True)
                
                # --- GERADORES DE EXPORTAÇÃO ---
                
                # Gerador TXT Customizado
                txt_content = "Atendimentos Plantão:\n\n"
                for _, row in df_export.iterrows():
                    txt_content += f"Data: {row['Data']}   Horário inicio atendimento: {row['Horário inicio atendimento']}   Horário fim do atendimento: {row['Horário fim do atendimento']}   Atendente: {row['Atendente']}   Total (Minutos): {row['Total (Minutos)']}\n"
                
                # Gerador CSV
                csv_content = df_export.to_csv(index=False, sep=';', decimal=',')
                
                # Gerador Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Plantao')
                excel_content = output.getvalue()
                
                st.markdown("#### 📥 Escolha o formato para Exportação")
                c_txt, c_xls, c_csv = st.columns(3)
                
                nome_arq = f"Plantao_{datetime.datetime.now().strftime('%d%m%Y')}"
                
                c_txt.download_button("📄 Exportar TXT Formatado", txt_content, f"{nome_arq}.txt", "text/plain", use_container_width=True)
                c_xls.download_button("📊 Exportar Excel (.xlsx)", excel_content, f"{nome_arq}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                c_csv.download_button("📑 Exportar CSV", csv_content, f"{nome_arq}.csv", "text/csv", use_container_width=True)

                st.divider()
                
                # --- SALVAMENTO NA TABELA plantoes_epsy ---
                st.markdown("#### 💾 Registrar Escala Oficial de Plantão")
                st.caption("Salve o turno do analista no banco de dados para contabilizar as métricas de RH e Home Page.")
                
                with st.form("form_salvar_plantao"):
                    engine = get_connection()
                    try:
                        df_usuarios = pd.read_sql(text("SELECT id, nome FROM usuarios WHERE ativo = TRUE ORDER BY nome"), engine)
                        opcoes_analistas = {row['nome']: row['id'] for _, row in df_usuarios.iterrows()}
                    except Exception as e:
                        st.error(f"Erro ao buscar usuários: {e}")
                        opcoes_analistas = {}
                    
                    analista_selecionado = st.selectbox("Analista Responsável pelo Plantão:", options=list(opcoes_analistas.keys()))
                    
                    col_dt1, col_dt2 = st.columns(2)
                    with col_dt1:
                        st.text_input("Data/Hora de Entrada (Identificada):", value=st.session_state.get('inicio_plantao', ''), disabled=True)
                    with col_dt2:
                        st.text_input("Data/Hora de Saída (Identificada):", value=st.session_state.get('fim_plantao', ''), disabled=True)
                        
                    btn_salvar_escala = st.form_submit_button("Registrar Escala no Banco", type="primary")
                    
                    if btn_salvar_escala:
                        try:
                            id_analista = opcoes_analistas[analista_selecionado]
                            with engine.begin() as conn_pl:
                                query_pl = text("""
                                    INSERT INTO plantoes_epsy (nome_analista_epsy, id_analista_epsy, data_hora_entrada, data_hora_saida)
                                    VALUES (:nome, :id_an, :dt_in, :dt_out)
                                """)
                                conn_pl.execute(query_pl, {
                                    "nome": analista_selecionado, 
                                    "id_an": id_analista, 
                                    "dt_in": st.session_state['inicio_plantao'], 
                                    "dt_out": st.session_state['fim_plantao']
                                })
                            st.success(f"✅ O turno de **{analista_selecionado}** foi salvo com sucesso na tabela de Plantões!")
                            registrar_log_auditoria(usuario_id, "REGISTRO_PLANTAO", f"Escala de {analista_selecionado} criada.")
                        except Exception as e:
                            st.error(f"❌ Erro de banco de dados ao salvar plantão: {e}")
            
            elif st.session_state.get('df_plantao_filtrado') is not None and st.session_state['df_plantao_filtrado'].empty:
                st.info("🤖 **PSY:** Poxa, eu não encontrei nenhuma chamada do GoTo dentro do horário e regime que você definiu.")