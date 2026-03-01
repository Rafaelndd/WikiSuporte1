import streamlit as st
import pandas as pd
import re
from datetime import datetime
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
    """Executa a lógica de Upsert inteligente para evitar duplicidade de dados."""
    engine = get_connection()
    try:
        with engine.begin() as conn:
            if tipo_arquivo == "GOTO":
                # Proteção: Deleta o intervalo de datas exato antes de inserir
                data_min = df['data_chamada'].min()
                data_max = df['data_chamada'].max()
                query_delete = text("DELETE FROM atendimentos_goto WHERE data_chamada >= :dmin AND data_chamada <= :dmax")
                conn.execute(query_delete, {"dmin": data_min, "dmax": data_max})
                
            elif tipo_arquivo == "MULTI360":
                # Proteção: Deleta os protocolos exatos antes de inserir
                lista_protocolos = df['protocolo'].dropna().tolist()
                if lista_protocolos:
                    query_delete = text("DELETE FROM atendimentos_multi360 WHERE protocolo = ANY(:ids)")
                    conn.execute(query_delete, {"ids": lista_protocolos})
            
            # Insere os dados limpos e com LGPD aplicada
            df.to_sql(nome_tabela, conn, if_exists='append', index=False)
            
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

def apenas_numeros(texto):
    return re.sub(r'\D', '', str(texto))

# ==========================================
# 3. INTERFACE DE USUÁRIO (UX) - ABAS
# ==========================================
st.title("📁 Importação de Dados Operacionais")
st.markdown("Importe os relatórios do **GoTo (Telefonia)** e do **Multi360 (WhatsApp)** para o WikiSuporte. O sistema processará, aplicará regras de anonimização e salvará tudo de forma inteligente.")

aba1, aba2 = st.tabs(["📥 Importar Relatórios (CSV/Excel)", "🔗 Cadastrar Clientes (CRM)"])

# ------------------------------------------
# ABA 1: IMPORTAÇÃO DE ARQUIVOS
# ------------------------------------------
with aba1:
    st.info("💡 **Dica:** O sistema identifica automaticamente se o arquivo é do GoTo ou do Multi360. Antes de salvar, os dados sensíveis são anonimizados automaticamente (LGPD).")
    
    with st.container(border=True):
        arquivo_upload = st.file_uploader("📂 Selecione ou arraste o seu arquivo de atendimento:", type=['csv', 'xlsx'])
    
    if arquivo_upload:
        # Verifica cabeçalhos rapidamente para rotear para o processador correto
        df_preview = ler_arquivo_dinamico(arquivo_upload)
        
        tipo_identificado = None
        df_processado = None
        erro_processamento = None
        
        if 'Conversation space id' in df_preview.columns:
            tipo_identificado = "GOTO"
        elif 'PROTOCOLO' in df_preview.columns:
            tipo_identificado = "MULTI360"
        else:
            st.error("❌ Arquivo não reconhecido. Certifique-se de que é um relatório válido do GoTo ou Multi360.")
            st.stop()
            
        # Tenta processar e aplicar LGPD
        with st.spinner(f"🔍 Processando arquivo do {tipo_identificado}..."):
            try:
                # Retorna o ponteiro do arquivo para o início após o preview
                arquivo_upload.seek(0) 
                
                if tipo_identificado == "GOTO":
                    df_processado = processar_csv_goto(arquivo_upload)
                    nome_tabela_bd = "atendimentos_goto"
                else:
                    df_processado = processar_csv_multi360(arquivo_upload)
                    nome_tabela_bd = "atendimentos_multi360"
                    
            except Exception as e:
                erro_processamento = str(e)
                
        if erro_processamento:
            st.error(f"❌ Ocorreu um erro durante o processamento do arquivo: {erro_processamento}")
        elif df_processado is not None and not df_processado.empty:
            
            st.success(f"✅ Arquivo do **{tipo_identificado}** processado com sucesso!")
            
            with st.container(border=True):
                st.markdown("### 🔍 Pré-visualização dos Dados")
                st.caption("Abaixo está uma amostra do arquivo já tratado e com dados sensíveis anonimizados.")
                st.dataframe(df_processado.head(5), use_container_width=True)
            
            # Métricas agrupadas visualmente
            st.markdown("#### 📊 Resumo do Arquivo")
            with st.container(border=True):
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Total de Registros lidos", len(df_processado))
                
                if tipo_identificado == "GOTO":
                    col_m2.metric("Data Inicial", df_processado['data_chamada'].min().strftime('%d/%m/%Y'))
                    col_m3.metric("Data Final", df_processado['data_chamada'].max().strftime('%d/%m/%Y'))
                else:
                    col_m2.metric("Data Inicial", df_processado['data_inicio'].min().strftime('%d/%m/%Y'))
                    col_m3.metric("Data Final", df_processado['data_inicio'].max().strftime('%d/%m/%Y'))
            
            st.warning("⚠️ **Atenção:** O WikiSuporte evita registros duplicados automaticamente. Ao importar, o sistema compara os dados com o banco e atualiza apenas o necessário.")
            
            if st.button("💾 Confirmar e Salvar no Banco de Dados", type="primary", use_container_width=True):
                with st.spinner("Gravando dados no WikiSuporte..."):
                    sucesso, msg = salvar_no_banco(df_processado, nome_tabela_bd, tipo_identificado)
                    
                    if sucesso:
                        st.success(f"🎉 Fantástico! {len(df_processado)} registros do {tipo_identificado} foram salvos no banco de dados com sucesso.")
                        registrar_log_auditoria(usuario_id, "IMPORT_CSV", f"Importou arquivo {arquivo_upload.name} ({tipo_identificado})")
                    else:
                        st.error(f"❌ Ocorreu um erro ao salvar o arquivo: {msg}")

# ------------------------------------------
# ABA 2: VÍNCULO DE CLIENTES (CRM)
# ------------------------------------------
with aba2:
    st.markdown("### 🔗 Cadastro de Clientes (CRM)")
    st.caption("Associe vários números de telefone a um mesmo CNPJ para organizar e unificar o histórico do cliente nas análises.")
    
    col_crm1, col_crm2 = st.columns(2)
    
    with col_crm1:
        with st.container(border=True):
            st.markdown("#### Novo Vínculo")
            with st.form("form_crm"):
                cnpj_input = st.text_input("CNPJ do Cliente:", placeholder="Ex: 00.000.000/0000-00")
                cnpj_limpo = apenas_numeros(cnpj_input)
                
                telefone_input = st.text_input("Telefone ou WhatsApp:", placeholder="Ex: (48) 99999-9999")
                telefone_limpo = apenas_numeros(telefone_input)
                
                st.markdown("<br>", unsafe_allow_html=True) # Espaçamento extra
                btn_vincular = st.form_submit_button("🔗 Vincular Telefone ao CNPJ", type="primary", use_container_width=True)
                
                if btn_vincular:
                    if cnpj_limpo and telefone_limpo:
                        
                        # =====================================================================
                        st.success(f"✅ Sucesso! Telefone **{telefone_limpo}** vinculado ao CNPJ **{cnpj_limpo}**.")
                        registrar_log_auditoria(usuario_id, "VINCULO_CRM", f"Vinculou  {telefone_limpo} ao CNPJ {cnpj_limpo}")
                        
                        # =====================================================================
                        # 2. A MÁGICA AUTOMÁTICA DA TEIA DE ARANHA (LGPD)
                        # =====================================================================
                        with st.spinner("🕸️ Sincronizando dados..."):
                            try:
                                # MANTIDO EXATAMENTE COMO NO SEU CÓDIGO ORIGINAL
                                linhas_afetadas = oraculo.sincronizar_vinculos_goto()
                                
                                if linhas_afetadas > 0:
                                    st.info(f"🚀 WikiSuporte sincronizou **{linhas_afetadas}** registros com sucesso.")
                                else:
                                    st.info("Nenhum registro novo foi encontrado para sincronizar. Todos os dados já estão atualizados.")
                            except Exception as e:
                                st.error(f"Erro ao sincronizar. Certifique-se de que a variável 'oraculo' está definida no ambiente. Detalhe: {e}")
                        # =====================================================================
                    else:
                        st.warning("⚠️ Por favor, preencha tanto o CNPJ quanto o Telefone antes de enviar.")

    with col_crm2:
        with st.container(border=True):
            st.markdown("#### 📊 Status da Normalização")
            if not cnpj_limpo and not telefone_limpo:
                st.info("Aguardando preenchimento dos dados ao lado...")
            
            if cnpj_limpo:
                st.success(f"🏢 **CNPJ Lido:** {cnpj_limpo}")
            if telefone_limpo:
                st.success(f"📞 **Telefone Lido:** {telefone_limpo}")
            
            st.divider()
            st.caption("O WikiSuporte remove automaticamente pontos e traços para garantir que o banco de dados fique limpo e padronizado.")